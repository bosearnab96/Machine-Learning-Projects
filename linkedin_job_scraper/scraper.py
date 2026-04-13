"""
scraper.py — Fetches LinkedIn posts and filters for hiring signals.

Uses the unofficial `linkedin-api` library which wraps LinkedIn's
internal mobile/voyager API. No browser automation needed.

Docs: https://github.com/tomquirk/linkedin-api
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from linkedin_api import Linkedin

from config import (
    HIRING_KEYWORDS,
    LINKEDIN_EMAIL,
    LINKEDIN_PASSWORD,
    MAX_POSTS_PER_RUN,
    SEARCH_QUERY,
)

logger = logging.getLogger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class HiringPost:
    post_id:    str
    author:     str
    author_url: str
    text:       str
    post_url:   str
    posted_at:  datetime
    matched_keywords: list[str] = field(default_factory=list)

    def short_preview(self, max_chars: int = 280) -> str:
        cleaned = re.sub(r"\s+", " ", self.text).strip()
        return cleaned[:max_chars] + ("…" if len(cleaned) > max_chars else "")


# ── Keyword matching ──────────────────────────────────────────────────────────

def _extract_keywords(text: str) -> list[str]:
    """Return every HIRING_KEYWORD found (case-insensitive) in *text*."""
    lower = text.lower()
    return [kw for kw in HIRING_KEYWORDS if kw.lower() in lower]


def _is_hiring_post(text: str) -> bool:
    return bool(_extract_keywords(text))


# ── LinkedIn client ───────────────────────────────────────────────────────────

def _build_client() -> Linkedin:
    """Authenticate and return a LinkedIn API client."""
    logger.info("Authenticating with LinkedIn as %s …", LINKEDIN_EMAIL)
    client = Linkedin(LINKEDIN_EMAIL, LINKEDIN_PASSWORD)
    logger.info("Authenticated successfully.")
    return client


# ── Post parsing helpers ──────────────────────────────────────────────────────

def _parse_post(raw: dict) -> Optional[HiringPost]:
    """
    Convert a raw voyager API post dict into a HiringPost.
    Returns None if the post doesn't match any hiring keyword.
    """
    try:
        # The voyager response structure varies; handle both feed and search shapes.
        value = raw.get("value", raw)  # search results wrap in "value"

        # ── text ──
        commentary = value.get("commentary", {})
        if isinstance(commentary, dict):
            text = commentary.get("text", {}).get("text", "")
        else:
            text = str(commentary)

        if not text or not _is_hiring_post(text):
            return None

        # ── post ID / URL ──
        entity_urn = value.get("entityUrn", "")          # urn:li:ugcPost:123…
        post_id    = entity_urn.split(":")[-1] if entity_urn else raw.get("id", "")
        post_url   = (
            f"https://www.linkedin.com/feed/update/{entity_urn}/"
            if entity_urn else ""
        )

        # ── author ──
        actor = value.get("actor", {})
        name_map = (
            actor.get("name", {})
                 .get("attributes", [{}])[0]
                 .get("miniProfile", {})
        ) if actor else {}

        first = name_map.get("firstName", "")
        last  = name_map.get("lastName", "")
        author_name = f"{first} {last}".strip() or actor.get("name", {}).get("text", "Unknown")

        pub_id = name_map.get("publicIdentifier", "")
        author_url = (
            f"https://www.linkedin.com/in/{pub_id}/" if pub_id else ""
        )

        # ── timestamp ──
        created_ms = value.get("createdAt", 0) or value.get("publishedAt", 0)
        posted_at  = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)

        return HiringPost(
            post_id=post_id,
            author=author_name,
            author_url=author_url,
            text=text,
            post_url=post_url,
            posted_at=posted_at,
            matched_keywords=_extract_keywords(text),
        )

    except Exception as exc:
        logger.debug("Could not parse post: %s — %s", raw.get("entityUrn", "?"), exc)
        return None


# ── Public interface ──────────────────────────────────────────────────────────

def fetch_hiring_posts() -> list[HiringPost]:
    """
    Main entry point.  Returns a list of HiringPost objects found on LinkedIn
    that match at least one hiring keyword.
    """
    client = _build_client()
    results: list[HiringPost] = []

    # ── Strategy 1: keyword search across all LinkedIn posts ──────────────────
    try:
        logger.info("Searching LinkedIn posts for query: %r", SEARCH_QUERY)
        raw_posts = client.search_posts(
            keywords=SEARCH_QUERY,
            limit=MAX_POSTS_PER_RUN,
        )
        logger.info("Raw posts returned: %d", len(raw_posts))
        for raw in raw_posts:
            post = _parse_post(raw)
            if post:
                results.append(post)
    except Exception as exc:
        logger.warning("Post search failed: %s", exc)

    # ── Strategy 2: scan feed (catches posts from your network) ───────────────
    try:
        logger.info("Fetching home feed …")
        feed = client.get_feed_posts(limit=MAX_POSTS_PER_RUN)
        for raw in feed:
            post = _parse_post(raw)
            if post and not any(p.post_id == post.post_id for p in results):
                results.append(post)
    except Exception as exc:
        logger.warning("Feed fetch failed: %s", exc)

    logger.info("Hiring posts found this run: %d", len(results))
    return results
