"""SQLite state machine for outreach targets.

States:
    queued           – ingested, not yet contacted
    invite_sent      – bare connection request sent (growth bucket)
    inmail_sent      – InMail sent (d2c_head bucket), terminal
    accepted         – connection accepted, ready for DM follow-up
    dm_sent          – full message delivered via DM, terminal
    already_connect  – we were already 1st-degree before the run; skipped
    skipped          – e.g. no "Connect" button visible, or not-now
    failed           – unexpected error; includes `error` column
    checkpoint       – script hit a LinkedIn checkpoint on this profile
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import config


SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    url           TEXT PRIMARY KEY,
    first_name    TEXT,
    company       TEXT,
    bucket        TEXT NOT NULL,              -- 'growth' | 'd2c_head'
    title         TEXT,
    status        TEXT NOT NULL DEFAULT 'queued',
    error         TEXT,
    invited_at    TEXT,
    accepted_at   TEXT,
    dm_sent_at    TEXT,
    inmail_at     TEXT,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_status  ON profiles(status);
CREATE INDEX IF NOT EXISTS idx_bucket  ON profiles(bucket);

CREATE TABLE IF NOT EXISTS rate_log (
    kind       TEXT NOT NULL,                 -- 'invite' | 'inmail' | 'dm'
    at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rate_at ON rate_log(at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect(db_path: Path = None):
    conn = sqlite3.connect(db_path or config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


# ── Writes ───────────────────────────────────────────────────────────────────

def upsert_profile(url: str, first_name: str, company: str,
                   bucket: str, title: str = "") -> bool:
    """Insert a profile as queued; no-op if it already exists. Returns True if new."""
    with connect() as conn:
        row = conn.execute("SELECT 1 FROM profiles WHERE url = ?", (url,)).fetchone()
        if row:
            return False
        conn.execute(
            "INSERT INTO profiles(url, first_name, company, bucket, title, "
            "status, updated_at) VALUES (?,?,?,?,?, 'queued', ?)",
            (url, first_name, company, bucket, title, _now()),
        )
        return True


def mark_status(url: str, status: str, *, error: str = None, **time_cols) -> None:
    sets = ["status = ?", "updated_at = ?"]
    vals = [status, _now()]
    if error is not None:
        sets.append("error = ?")
        vals.append(error)
    for col, val in time_cols.items():
        sets.append(f"{col} = ?")
        vals.append(val or _now())
    vals.append(url)
    with connect() as conn:
        conn.execute(f"UPDATE profiles SET {', '.join(sets)} WHERE url = ?", vals)


def log_rate(kind: str) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO rate_log(kind, at) VALUES(?, ?)", (kind, _now()))


# ── Reads ────────────────────────────────────────────────────────────────────

def next_queued(bucket: str, limit: int = 1) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM profiles WHERE status='queued' AND bucket=? "
            "ORDER BY updated_at ASC LIMIT ?",
            (bucket, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def accepted_awaiting_dm(limit: int = 1) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM profiles WHERE status='accepted' AND bucket='growth' "
            "ORDER BY accepted_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def count_in_window(kind: str, seconds: int) -> int:
    """Count `kind` actions within the last `seconds`. Used for rate caps."""
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM rate_log WHERE kind = ? "
            "AND at >= datetime('now', ?)",
            (kind, f"-{seconds} seconds"),
        ).fetchone()
        return row["n"]


def invites_this_week() -> int:
    return count_in_window("invite", 7 * 24 * 3600)


def invites_today() -> int:
    return count_in_window("invite", 24 * 3600)


def find_by_url(url: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE url = ?", (url,)).fetchone()
        return dict(row) if row else None
