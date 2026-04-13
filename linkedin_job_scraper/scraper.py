"""
scraper.py — Fetches LinkedIn posts and filters for hiring signals.

Sources (in order):
  1. Home feed  — posts + reactions/comments from 1st/2nd connections & follows
  2. Connection posts — direct profile posts from each of your 1st connections
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

from linkedin_api import Linkedin

from config import (
    HIRING_KEYWORDS,
    LINKEDIN_EMAIL,
    LINKEDIN_JSESSIONID,
    LINKEDIN_LI_AT,
    LINKEDIN_PASSWORD,
    LOOKBACK_HOURS,
    MAX_FEED_POSTS,
    MAX_POSTS_PER_PROFILE,
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
    source:     str = ""                        # "feed" | "connection:<name>"
    matched_keywords: list[str] = field(default_factory=list)

    def short_preview(self, max_chars: int = 280) -> str:
        cleaned = re.sub(r"\s+", " ", self.text).strip()
        return cleaned[:max_chars] + ("…" if len(cleaned) > max_chars else "")


# ── Keyword matching ──────────────────────────────────────────────────────────

def _extract_keywords(text: str) -> list[str]:
    lower = text.lower()
    return [kw for kw in HIRING_KEYWORDS if kw.lower() in lower]

def _is_hiring_post(text: str) -> bool:
    return bool(_extract_keywords(text))


# ── Auth ──────────────────────────────────────────────────────────────────────

def _build_client() -> Linkedin:
    if LINKEDIN_LI_AT:
        logger.info("Authenticating via li_at + JSESSIONID cookies …")
        return Linkedin("", "", cookies={
            "li_at": LINKEDIN_LI_AT,
            "JSESSIONID": LINKEDIN_JSESSIONID,
        })
    logger.info("Authenticating as %s …", LINKEDIN_EMAIL)
    return Linkedin(LINKEDIN_EMAIL, LINKEDIN_PASSWORD)


# ── Post text extraction ──────────────────────────────────────────────────────

def _extract_text(post: dict) -> str:
    """
    Pull the human-readable text out of a voyager post dict.
    LinkedIn returns text in several different shapes depending on
    post type (original, reshare, article, reaction surface).
    We try each known location in priority order.
    """
    # Shape 1 — direct feed update / ugcPost
    # commentary.text.text
    commentary = post.get("commentary") or {}
    if isinstance(commentary, dict):
        txt = (commentary.get("text") or {}).get("text", "")
        if txt:
            return txt

    # Shape 2 — reshared post with original content
    reshared = post.get("resharedUpdate") or {}
    if reshared:
        txt = _extract_text(reshared)
        if txt:
            return txt

    # Shape 3 — some feed elements wrap the real update inside "value"
    value = post.get("value") or {}
    if value:
        txt = _extract_text(value)
        if txt:
            return txt

    # Shape 4 — article / rich media posts store text under "description"
    description = post.get("description") or {}
    if isinstance(description, dict):
        txt = description.get("text", "")
        if txt:
            return txt

    # Shape 5 — get_profile_posts returns slightly different structure
    header = post.get("header") or {}
    txt = (header.get("text") or {}).get("text", "")
    if txt:
        return txt

    return ""


def _extract_author(post: dict) -> tuple[str, str]:
    """Return (display_name, profile_url)."""
    actor = post.get("actor") or {}

    # name.text is the display string
    name_text = (actor.get("name") or {}).get("text", "")

    # miniProfile nested in name.attributes gives public ID for URL
    attrs = (actor.get("name") or {}).get("attributes") or []
    pub_id = ""
    if attrs:
        mini = (attrs[0] or {}).get("miniProfile") or {}
        pub_id = mini.get("publicIdentifier", "")
        if not name_text:
            first = mini.get("firstName", "")
            last  = mini.get("lastName", "")
            name_text = f"{first} {last}".strip()

    # fallback: some profile-post responses put it under "authorProfileId"
    if not name_text:
        name_text = post.get("authorProfileId", "Unknown")

    url = f"https://www.linkedin.com/in/{pub_id}/" if pub_id else ""
    return name_text or "Unknown", url


def _extract_post_id(post: dict) -> str:
    urn = (
        post.get("dashEntityUrn")
        or post.get("entityUrn")
        or post.get("updateMetadata", {}).get("urn", "")
    )
    return urn.split(":")[-1] if urn else ""


def _extract_timestamp(post: dict) -> datetime:
    ms = (
        post.get("createdAt")
        or post.get("publishedAt")
        or post.get("actor", {}).get("subDescription", {}).get("accessibilityText", None)
    )
    if isinstance(ms, (int, float)) and ms > 0:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return datetime.now(tz=timezone.utc)


# ── Core parser ───────────────────────────────────────────────────────────────

def _parse(post: dict, source: str = "feed") -> Optional[HiringPost]:
    try:
        text = _extract_text(post)
        if not text:
            return None
        keywords = _extract_keywords(text)
        if not keywords:
            return None

        post_id = _extract_post_id(post)
        if not post_id:
            return None

        author, author_url = _extract_author(post)
        posted_at = _extract_timestamp(post)
        entity_urn = post.get("dashEntityUrn") or post.get("entityUrn", "")
        post_url = (
            f"https://www.linkedin.com/feed/update/{entity_urn}/"
            if entity_urn else ""
        )

        return HiringPost(
            post_id=post_id,
            author=author,
            author_url=author_url,
            text=text,
            post_url=post_url,
            posted_at=posted_at,
            source=source,
            matched_keywords=keywords,
        )
    except Exception as exc:
        logger.debug("Parse error: %s", exc)
        return None


# ── Dedup helper ──────────────────────────────────────────────────────────────

def _add(results: list[HiringPost], post: Optional[HiringPost]) -> None:
    if post and not any(p.post_id == post.post_id for p in results):
        results.append(post)


# ── Public interface ──────────────────────────────────────────────────────────

def fetch_hiring_posts() -> list[HiringPost]:
    """
    Returns HiringPost objects from:
      • Your home feed (includes posts your connections reacted/commented on)
      • Direct posts from each of your 1st-degree connections
    Only posts newer than LOOKBACK_HOURS are returned.
    """
    client = _build_client()
    results: list[HiringPost] = []
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=LOOKBACK_HOURS)

    # ── 1. Home feed (1st + 2nd connections, follows, reactions, comments) ─────
    logger.info(
        "Fetching home feed (limit=%d, lookback=%dh) …",
        MAX_FEED_POSTS, LOOKBACK_HOURS,
    )
    try:
        feed = client.get_feed_posts(limit=MAX_FEED_POSTS, exclude_promoted_posts=True)
        logger.info("Feed returned %d raw items", len(feed))
        for raw in feed:
            p = _parse(raw, source="feed")
            if p:
                if p.posted_at >= cutoff:
                    _add(results, p)
                # also check the reshared original if present
                reshared = raw.get("resharedUpdate") or {}
                if reshared:
                    p2 = _parse(reshared, source="feed/reshare")
                    if p2 and p2.posted_at >= cutoff:
                        _add(results, p2)
    except Exception as exc:
        logger.warning("Feed fetch failed: %s", exc)

    # ── 2. Posts from each 1st-degree connection ──────────────────────────────
    logger.info("Fetching 1st-degree connections …")
    try:
        me = client.get_user_profile()
        my_urn = me.get("plainId") or me.get("miniProfile", {}).get("entityUrn", "").split(":")[-1]
        if my_urn:
            conns = client.get_profile_connections(my_urn)
            logger.info("Found %d connections — scanning their recent posts …", len(conns))
            for conn in conns:
                pub_id = (
                    conn.get("miniProfile", {}).get("publicIdentifier")
                    or conn.get("publicIdentifier", "")
                )
                if not pub_id:
                    continue
                try:
                    conn_posts = client.get_profile_posts(
                        public_id=pub_id,
                        post_count=MAX_POSTS_PER_PROFILE,
                    )
                    conn_name = (
                        conn.get("miniProfile", {}).get("firstName", "")
                        + " "
                        + conn.get("miniProfile", {}).get("lastName", "")
                    ).strip()
                    for raw in conn_posts:
                        p = _parse(raw, source=f"connection:{conn_name}")
                        if p and p.posted_at >= cutoff:
                            _add(results, p)
                except Exception:
                    pass   # skip individual connection failures silently
        else:
            logger.warning("Could not determine own URN — skipping connection scan.")
    except Exception as exc:
        logger.warning("Connection scan failed: %s", exc)

    logger.info(
        "Total hiring posts found (last %dh): %d",
        LOOKBACK_HOURS, len(results),
    )
    return results
