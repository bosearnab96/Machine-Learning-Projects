"""
scraper.py — Finds LinkedIn hiring posts via Bing web search.

Why Bing?
  LinkedIn blocks all automated access from cloud/datacenter IPs.
  DuckDuckGo also blocks GitHub Actions IPs (returns HTTP 202 for every query).

  Bing is operated by Microsoft on Azure — the same infrastructure as
  GitHub Actions — so it does NOT block Azure datacenter IPs.  We scrape
  Bing's HTML results page with requests + BeautifulSoup (no API key needed).
  Public LinkedIn posts are well-indexed by Bing.
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

import requests
from bs4 import BeautifulSoup

from config import (
    HIRING_KEYWORDS,
    MAX_SEARCH_RESULTS,
    SEARCH_QUERIES,
    SEARCH_PAUSE_SECONDS,
)

logger = logging.getLogger(__name__)

# Rotate through a few realistic User-Agent strings so individual queries
# don't all look identical at the HTTP layer.
_USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
]


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
    Bing titles for LinkedIn posts look like:
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
    """Convert a Bing search result dict into a HiringPost."""
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
            posted_at=datetime.now(tz=timezone.utc),
            matched_keywords=keywords,
        )
    except Exception:
        logger.debug("Parse error:\n%s", traceback.format_exc())
        return None


# ── Search ────────────────────────────────────────────────────────────────────

def _bing_search(query: str, max_results: int) -> list[dict]:
    """
    Scrape Bing web search for `query`, returning up to `max_results`
    results as {href, title, body} dicts — the same shape our parser expects.

    Appends `after:YYYY-MM-DD` (7 days ago) so results stay recent.
    Bing paginates in batches of 10; we fetch as many pages as needed.
    """
    week_ago = (datetime.now(tz=timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    dated_query = f"{query} after:{week_ago}"

    session = requests.Session()
    ua = random.choice(_USER_AGENTS)
    session.headers.update({
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    })

    results: list[dict] = []
    offset = 1  # Bing uses 1-based pagination (first=1, 11, 21, …)

    while len(results) < max_results:
        try:
            resp = session.get(
                "https://www.bing.com/search",
                params={
                    "q":       dated_query,
                    "first":   offset,
                    "count":   10,
                    "setlang": "en-US",
                    "cc":      "US",
                },
                timeout=20,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("Bing request failed at offset %d: %s", offset, exc)
            break

        soup  = BeautifulSoup(resp.text, "html.parser")
        items = soup.select("li.b_algo")
        logger.debug("  Bing offset=%d → %d result items in page", offset, len(items))

        if not items:
            logger.debug("  No more Bing results for query %r", query[:60])
            break

        for item in items:
            title_a = item.select_one("h2 a")
            caption = item.select_one(".b_caption p") or item.select_one(".b_algoSlug")
            if not title_a:
                continue
            results.append({
                "href":  title_a.get("href", ""),
                "title": title_a.get_text(strip=True),
                "body":  caption.get_text(strip=True) if caption else "",
            })

        offset += 10
        if len(items) < 10:
            break   # last page reached

    logger.info("  Bing query %r → %d raw results", query[:60], len(results))
    return results[:max_results]


# ── Public entry point ────────────────────────────────────────────────────────

def fetch_hiring_posts() -> list[HiringPost]:
    """
    Run each configured search query against Bing (last 7 days via after:)
    and return deduplicated HiringPost objects.
    SQLite deduplication in storage.py ensures only genuinely new posts
    are emailed each day.
    """
    results_map: dict[str, HiringPost] = {}   # post_id → HiringPost
    total_raw = 0

    logger.info("Running %d Bing search queries …", len(SEARCH_QUERIES))

    for i, query in enumerate(SEARCH_QUERIES):
        raw = _bing_search(query, MAX_SEARCH_RESULTS)
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
            "Bing returned 0 raw results across all %d queries. "
            "Check network connectivity or whether Bing has changed its HTML structure.",
            len(SEARCH_QUERIES),
        )

    results = list(results_map.values())
    logger.info(
        "Total raw Bing results: %d  |  Unique hiring posts after filtering: %d",
        total_raw, len(results),
    )
    return results
