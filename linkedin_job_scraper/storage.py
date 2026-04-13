"""
storage.py — SQLite-backed deduplication store.

Every post we've already seen is persisted here so daily runs only
surface genuinely new hiring posts.
"""

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

from config import DB_PATH
from scraper import HiringPost

logger = logging.getLogger(__name__)

# ── Schema ─────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS seen_posts (
    post_id          TEXT PRIMARY KEY,
    author           TEXT,
    author_url       TEXT,
    text             TEXT,
    post_url         TEXT,
    posted_at        TEXT,          -- ISO-8601 UTC
    matched_keywords TEXT,          -- comma-separated
    first_seen_at    TEXT           -- ISO-8601 UTC, when WE saw it
);
"""


# ── Connection helper ──────────────────────────────────────────────────────────

@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    """Create tables if they don't exist yet."""
    with _conn() as con:
        con.executescript(_DDL)
    logger.info("Database initialised at %s", DB_PATH)


# ── Public API ─────────────────────────────────────────────────────────────────

def filter_new_posts(posts: list[HiringPost]) -> list[HiringPost]:
    """
    Given a list of HiringPost objects, return only the ones whose
    post_id has never been stored.  The new posts are immediately saved
    so subsequent calls within the same run won't double-count them.
    """
    if not posts:
        return []

    with _conn() as con:
        ids = [p.post_id for p in posts]
        placeholders = ",".join("?" * len(ids))
        existing = {
            row["post_id"]
            for row in con.execute(
                f"SELECT post_id FROM seen_posts WHERE post_id IN ({placeholders})",
                ids,
            )
        }

        new_posts = [p for p in posts if p.post_id not in existing]

        if new_posts:
            now = datetime.now(tz=timezone.utc).isoformat()
            con.executemany(
                """
                INSERT OR IGNORE INTO seen_posts
                    (post_id, author, author_url, text, post_url,
                     posted_at, matched_keywords, first_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        p.post_id,
                        p.author,
                        p.author_url,
                        p.text,
                        p.post_url,
                        p.posted_at.isoformat(),
                        ",".join(p.matched_keywords),
                        now,
                    )
                    for p in new_posts
                ],
            )
            logger.info("Saved %d new posts to DB.", len(new_posts))
        else:
            logger.info("No new posts to save (all already seen).")

    return new_posts


def get_todays_new_posts() -> list[dict]:
    """
    Retrieve all posts first-seen today (UTC), in reverse chronological order.
    Useful for the email digest if you want to re-query instead of passing
    in-memory objects.
    """
    today = datetime.now(tz=timezone.utc).date().isoformat()
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM seen_posts WHERE first_seen_at LIKE ? ORDER BY first_seen_at DESC",
            (f"{today}%",),
        ).fetchall()
    return [dict(r) for r in rows]
