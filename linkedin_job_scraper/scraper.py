"""
scraper.py — Finds LinkedIn hiring posts via DuckDuckGo search.

Why search-based?
  LinkedIn blocks all automated access from cloud/datacenter IPs
  (GitHub Actions, AWS, GCP, etc.) at the network level — regardless
  of cookies, browser type, or stealth techniques.

  DuckDuckGo indexes public LinkedIn posts and lets us search them
  without any authentication, API keys, or IP restrictions.
  Posts are public by default on LinkedIn, so we don't miss much.
"""

import hashlib
import logging
import re
import time
import random
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

from duckduckgo_search import DDGS

from config import (
    HIRING_KEYWORDS,
    LOOKBACK_HOURS,
    MAX_SEARCH_RESULTS,
    SEARCH_QUERIES,
    SEARCH_PAUSE_SECONDS,
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
    source:     str = "search"
    matched_keywords: list[str] = field(default_factory=list)

    def short_preview(self, max_chars: int = 280) -> str:
        cleaned = re.sub(r"\s+", " ", self.text).strip()
        return cleaned[:max_chars] + ("…" if len(cleaned) > max_chars else "")


# ── Keyword matching ──────────────────────────────────────────────────────────

def _extract_keywords(text: str) -> list[str]:
    lower = text.lower()
    return [kw for kw in HIRING_KEYWORDS if kw.lower() in lower]


# ── Result parsing ────────────────────────────────────────────────────────────

def _parse_author(title: str, url: str) -> tuple[str, str]:
    """
    DuckDuckGo titles for LinkedIn posts look like:
      'Arnab Bose on LinkedIn: We are hiring…'
      'Mitul Goyal on LinkedIn: Hiring: Program Manager…'
    Extract the name and build a profile URL from the post URL.
    """
    m = re.match(r"^(.+?)\s+on LinkedIn", title or "", re.IGNORECASE)
    author_name = m.group(1).strip() if m else "LinkedIn User"

    # Profile URL: linkedin.com/posts/username_... → linkedin.com/in/username
    pub_id = ""
    m2 = re.search(r"linkedin\.com/posts/([^_/]+)", url or "")
    if m2:
        pub_id = m2.group(1)
    author_url = f"https://www.linkedin.com/in/{pub_id}/" if pub_id else ""

    return author_name, author_url


def _make_post_id(url: str, text: str) -> str:
    # Prefer the activity ID from the URL
    m = re.search(r"activity-(\d+)", url or "")
    if m:
        return m.group(1)
    return hashlib.md5((url + text[:100]).encode()).hexdigest()


def _result_to_post(result: dict) -> Optional[HiringPost]:
    """Convert a DuckDuckGo search result dict into a HiringPost."""
    try:
        url   = result.get("href", "")
        title = result.get("title", "")
        body  = result.get("body", "")

        # Combine title + body for keyword matching
        full_text = f"{title}\n{body}".strip()
        keywords  = _extract_keywords(full_text)
        if not keywords:
            return None

        # Only keep actual LinkedIn post/activity URLs
        if not re.search(r"linkedin\.com/(posts|feed/update)", url):
            logger.debug("Skipped non-post URL: %s", url[:120])
            return None

        author, author_url = _parse_author(title, url)
        post_id = _make_post_id(url, full_text)

        return HiringPost(
            post_id=post_id,
            author=author,
            author_url=author_url,
            text=full_text,
            post_url=url,
            posted_at=datetime.now(tz=timezone.utc),  # DDG rarely gives exact timestamp
            matched_keywords=keywords,
        )
    except Exception:
        logger.debug("Parse error:\n%s", traceback.format_exc())
        return None


# ── Search ────────────────────────────────────────────────────────────────────

def _ddg_search(query: str, max_results: int, timelimit: str = "w") -> list[dict]:
    """Run one DuckDuckGo search, return raw results."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(
                query,
                timelimit=timelimit,    # "w" = last 7 days; SQLite dedup handles "new only"
                max_results=max_results,
            ))
        logger.info("  Query %r [timelimit=%s] → %d raw results", query[:60], timelimit, len(results))
        return results
    except Exception:
        logger.warning("DDG search failed (timelimit=%s): %s", timelimit, traceback.format_exc())
        return []


# ── Public entry point ────────────────────────────────────────────────────────

def fetch_hiring_posts() -> list[HiringPost]:
    """
    Run each configured search query against DuckDuckGo and return
    deduplicated HiringPost objects.

    Strategy:
      1. Try timelimit="w" (last 7 days) — wide enough for DDG's indexing lag.
      2. If every query returns 0 raw results, fall back to timelimit=None
         so we can verify DDG is reachable at all (dedup DB prevents re-sends).
    """
    results_map: dict[str, HiringPost] = {}   # post_id → HiringPost
    total_raw = 0

    logger.info("Running %d search queries …", len(SEARCH_QUERIES))

    for i, query in enumerate(SEARCH_QUERIES):
        raw = _ddg_search(query, MAX_SEARCH_RESULTS, timelimit="w")
        total_raw += len(raw)

        for r in raw:
            post = _result_to_post(r)
            if post and post.post_id not in results_map:
                results_map[post.post_id] = post

        if i < len(SEARCH_QUERIES) - 1:
            pause = SEARCH_PAUSE_SECONDS + random.uniform(0, 1)
            time.sleep(pause)

    # ── Fallback: if DDG returned nothing at all, retry without timelimit ──────
    if total_raw == 0:
        logger.warning(
            "All %d queries returned 0 raw results with timelimit='w'. "
            "Retrying without time limit (DDG may be slow to index LinkedIn).",
            len(SEARCH_QUERIES),
        )
        for i, query in enumerate(SEARCH_QUERIES):
            raw = _ddg_search(query, MAX_SEARCH_RESULTS, timelimit=None)
            total_raw += len(raw)

            for r in raw:
                post = _result_to_post(r)
                if post and post.post_id not in results_map:
                    results_map[post.post_id] = post

            if i < len(SEARCH_QUERIES) - 1:
                pause = SEARCH_PAUSE_SECONDS + random.uniform(0, 1)
                time.sleep(pause)

    if total_raw == 0:
        logger.error(
            "DDG returned 0 raw results even without a time filter. "
            "This suggests DuckDuckGo may be rate-limiting this IP."
        )

    results = list(results_map.values())
    logger.info(
        "Total raw DDG results: %d  |  Unique hiring posts after filtering: %d",
        total_raw, len(results),
    )
    return results
