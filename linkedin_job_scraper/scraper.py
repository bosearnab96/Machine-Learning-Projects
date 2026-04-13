"""
scraper.py — Fetches LinkedIn posts and filters for hiring signals.
"""

import json
import logging
import re
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from requests.cookies import RequestsCookieJar
from linkedin_api import Linkedin

from config import (
    HIRING_KEYWORDS,
    LINKEDIN_COOKIES,
    LINKEDIN_EMAIL,
    LINKEDIN_JSESSIONID,
    LINKEDIN_LI_AT,
    LINKEDIN_PASSWORD,
    LOOKBACK_HOURS,
    MAX_FEED_POSTS,
    MAX_POSTS_PER_PROFILE,
)

logger = logging.getLogger(__name__)

# Raw dump file — uploaded as GitHub Actions artifact for debugging
RAW_DUMP = Path("raw_feed_dump.json")


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class HiringPost:
    post_id:    str
    author:     str
    author_url: str
    text:       str
    post_url:   str
    posted_at:  datetime
    source:     str = ""
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

def _parse_cookie_string(cookie_str: str) -> RequestsCookieJar:
    """Parse a browser document.cookie string into a RequestsCookieJar."""
    jar = RequestsCookieJar()
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        name, _, value = part.partition("=")
        name  = name.strip()
        value = value.strip()
        jar.set(name, value, domain=".linkedin.com", path="/")
        jar.set(name, value, domain="www.linkedin.com", path="/")
    return jar


def _build_client() -> Linkedin:
    if LINKEDIN_COOKIES:
        logger.info("Authenticating via full browser cookie string …")
        jar = _parse_cookie_string(LINKEDIN_COOKIES)
        logger.info("Cookies loaded: %s", [c.name for c in jar])
        client = Linkedin("", "", cookies=jar)
    elif LINKEDIN_LI_AT:
        logger.info("Authenticating via li_at + JSESSIONID cookies …")
        jar = RequestsCookieJar()
        jar.set("li_at",      LINKEDIN_LI_AT,      domain=".linkedin.com", path="/")
        jar.set("JSESSIONID", LINKEDIN_JSESSIONID, domain=".linkedin.com", path="/")
        client = Linkedin("", "", cookies=jar)
    else:
        logger.info("Authenticating as %s …", LINKEDIN_EMAIL)
        client = Linkedin(LINKEDIN_EMAIL, LINKEDIN_PASSWORD)
    logger.info("Auth complete.")
    return client


# ── Recursive text walker ─────────────────────────────────────────────────────

def _walk_text(obj, depth=0) -> str:
    """
    Recursively walk any dict/list structure and return the longest
    string found under a key named 'text'. This is resilient to
    LinkedIn silently restructuring their API response.
    """
    if depth > 8:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        candidates = [_walk_text(x, depth+1) for x in obj]
        return max(candidates, key=len) if candidates else ""
    if isinstance(obj, dict):
        # direct hit
        if "text" in obj and isinstance(obj["text"], str):
            return obj["text"]
        # recurse into all values; prefer "commentary" and "description" keys first
        priority = ["commentary", "description", "content", "text"]
        seen = set()
        results = []
        for k in priority + [k for k in obj if k not in priority]:
            if k in obj and k not in seen:
                seen.add(k)
                t = _walk_text(obj[k], depth+1)
                if t:
                    results.append(t)
        return max(results, key=len) if results else ""
    return ""


def _extract_text(post: dict) -> str:
    # Try the known fast path first
    commentary = post.get("commentary") or {}
    if isinstance(commentary, dict):
        inner = commentary.get("text") or {}
        if isinstance(inner, dict):
            t = inner.get("text", "")
            if t:
                return t
        elif isinstance(inner, str) and inner:
            return inner

    # Fall back to recursive walker across the whole post
    return _walk_text(post)


def _extract_author(post: dict) -> tuple[str, str]:
    actor = post.get("actor") or {}
    name_node = actor.get("name") or {}
    name_text = name_node.get("text", "") if isinstance(name_node, dict) else str(name_node)
    attrs = name_node.get("attributes", []) if isinstance(name_node, dict) else []
    pub_id = ""
    if attrs:
        mini = (attrs[0] or {}).get("miniProfile") or {}
        pub_id = mini.get("publicIdentifier", "")
        if not name_text:
            name_text = f"{mini.get('firstName','')} {mini.get('lastName','')}".strip()
    url = f"https://www.linkedin.com/in/{pub_id}/" if pub_id else ""
    return name_text or "Unknown", url


def _extract_post_id(post: dict) -> str:
    urn = (
        post.get("dashEntityUrn")
        or post.get("entityUrn")
        or (post.get("updateMetadata") or {}).get("urn", "")
    )
    return urn.split(":")[-1] if urn else ""


def _extract_timestamp(post: dict) -> datetime:
    ms = post.get("createdAt") or post.get("publishedAt") or 0
    if isinstance(ms, (int, float)) and ms > 1_000_000_000:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return datetime.now(tz=timezone.utc)


# ── Parser ────────────────────────────────────────────────────────────────────

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
            # Still include it but use a hash of the text
            import hashlib
            post_id = hashlib.md5(text[:200].encode()).hexdigest()

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
    except Exception:
        logger.debug("Parse error:\n%s", traceback.format_exc())
        return None


def _add(results: list[HiringPost], post: Optional[HiringPost]) -> None:
    if post and not any(p.post_id == post.post_id for p in results):
        results.append(post)


# ── Public entry point ────────────────────────────────────────────────────────

def fetch_hiring_posts() -> list[HiringPost]:
    client  = _build_client()
    results: list[HiringPost] = []
    cutoff  = datetime.now(tz=timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    all_raw: list[dict] = []

    # ── 1. Home feed ──────────────────────────────────────────────────────────
    logger.info("Fetching home feed (limit=%d) …", MAX_FEED_POSTS)
    try:
        feed = client.get_feed_posts(limit=MAX_FEED_POSTS, exclude_promoted_posts=True)
        logger.info("Feed: %d raw items returned", len(feed))
        all_raw.extend(feed[:5])   # save first 5 for artifact

        for raw in feed:
            for candidate in [raw, raw.get("resharedUpdate") or {}]:
                if not candidate:
                    continue
                text = _extract_text(candidate)
                logger.debug("feed item text[:80]=%r", text[:80])
                p = _parse(candidate, source="feed")
                if p and p.posted_at >= cutoff:
                    _add(results, p)
    except Exception:
        logger.error("Feed fetch FAILED:\n%s", traceback.format_exc())

    # ── 2. 1st-degree connection posts ───────────────────────────────────────
    logger.info("Fetching 1st-degree connection posts …")
    try:
        me     = client.get_user_profile()
        my_urn = me.get("plainId") or (me.get("miniProfile") or {}).get("entityUrn", "").split(":")[-1]
        if my_urn:
            conns = client.get_profile_connections(my_urn)
            logger.info("Connections: %d found", len(conns))
            for conn in conns:
                pub_id = (conn.get("miniProfile") or {}).get("publicIdentifier", "")
                if not pub_id:
                    continue
                try:
                    posts = client.get_profile_posts(public_id=pub_id, post_count=MAX_POSTS_PER_PROFILE)
                    name  = (
                        (conn.get("miniProfile") or {}).get("firstName", "") + " " +
                        (conn.get("miniProfile") or {}).get("lastName", "")
                    ).strip()
                    for raw in posts:
                        p = _parse(raw, source=f"connection:{name}")
                        if p and p.posted_at >= cutoff:
                            _add(results, p)
                except Exception:
                    pass
    except Exception:
        logger.error("Connection scan FAILED:\n%s", traceback.format_exc())

    # ── Save raw dump artifact ────────────────────────────────────────────────
    try:
        RAW_DUMP.write_text(json.dumps(all_raw, indent=2, default=str))
        logger.info("Raw dump written to %s (%d items)", RAW_DUMP, len(all_raw))
    except Exception:
        pass

    logger.info("Hiring posts found (last %dh): %d", LOOKBACK_HOURS, len(results))
    return results
