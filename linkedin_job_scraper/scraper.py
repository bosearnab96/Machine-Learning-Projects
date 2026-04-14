"""
scraper.py — Finds LinkedIn hiring posts via python-jobspy.

Why JobSpy?
  LinkedIn blocks direct scraping from datacenter IPs.
  DuckDuckGo and Bing search APIs also block GitHub Actions IPs.

  python-jobspy (github.com/speedyapply/JobSpy) is the community-standard
  library for scraping LinkedIn Jobs without authentication or API keys.
  It works from GitHub Actions at low frequency (once daily) because it
  mimics normal browser behaviour and stays well within LinkedIn's
  undocumented rate limits.

  Results are LinkedIn job listings — structured hiring announcements
  from companies, which is exactly what we want.
"""

import hashlib
import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone, date as date_type
from typing import Optional

from jobspy import scrape_jobs

from config import (
    HIRING_KEYWORDS,
    HOURS_OLD,
    JOB_LOCATION,
    MAX_RESULTS_PER_TERM,
)

logger = logging.getLogger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class HiringPost:
    post_id:    str
    author:     str           # company name
    author_url: str           # company LinkedIn URL
    text:       str           # job title + location + description snippet
    post_url:   str           # direct link to the job listing
    posted_at:  datetime
    is_remote:  bool = False
    source:     str = "linkedin_jobs"
    matched_keywords: list[str] = field(default_factory=list)

    def short_preview(self, max_chars: int = 280) -> str:
        import re
        cleaned = re.sub(r"\s+", " ", self.text).strip()
        return cleaned[:max_chars] + ("…" if len(cleaned) > max_chars else "")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_datetime(d) -> datetime:
    """Convert a date, datetime, or None to a timezone-aware datetime."""
    if d is None:
        return datetime.now(tz=timezone.utc)
    if isinstance(d, datetime):
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    if isinstance(d, date_type):
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return datetime.now(tz=timezone.utc)


def _make_post_id(job_id, url: str) -> str:
    if job_id and str(job_id).strip():
        return str(job_id).strip()
    return hashlib.md5((url or "").encode()).hexdigest()


def _extract_keywords(title: str, description: str) -> list[str]:
    """Return matched HIRING_KEYWORDS from title + description, else role labels."""
    combined = f"{title} {description}".lower()
    matched = [kw for kw in HIRING_KEYWORDS if kw.lower() in combined]
    if not matched:
        fallbacks = ["senior", "lead", "staff", "principal", "junior", "mid",
                     "engineer", "manager", "analyst", "designer", "developer",
                     "scientist", "architect", "consultant", "director"]
        matched = [w for w in fallbacks if w in title.lower()]
    return matched[:6] if matched else ["hiring"]


def _is_relevant_location(row) -> bool:
    """Keep only jobs in Bangalore/Bengaluru or fully remote."""
    location = str(row.get("location") or "").lower()
    is_remote = bool(row.get("is_remote") or False)
    return (
        "bangalore" in location
        or "bengaluru" in location
        or "remote" in location
        or is_remote
    )


def _row_to_post(row) -> Optional[HiringPost]:
    try:
        job_id    = row.get("id", "")
        url       = str(row.get("job_url") or "")
        title     = str(row.get("title") or "Unknown Role")
        company   = str(row.get("company") or "Unknown Company")
        location  = str(row.get("location") or "")
        desc      = str(row.get("description") or "")
        co_url    = str(row.get("company_url") or "")
        posted    = _to_datetime(row.get("date_posted"))
        is_remote = bool(row.get("is_remote") or False)

        # Build a readable text block: title + location header + description
        text = f"{title} at {company}"
        if location:
            text += f"\n📍 {location}"
        if is_remote:
            text += "  🌐 Remote"
        if desc:
            text += f"\n\n{desc[:600]}"

        post_id  = _make_post_id(job_id, url)
        keywords = _extract_keywords(title, desc[:300])

        return HiringPost(
            post_id=post_id,
            author=company,
            author_url=co_url,
            text=text,
            post_url=url,
            posted_at=posted,
            is_remote=is_remote,
            matched_keywords=keywords,
        )
    except Exception:
        logger.debug("Row parse error:\n%s", traceback.format_exc())
        return None


# ── Public entry point ────────────────────────────────────────────────────────

def fetch_hiring_posts(search_terms: list[str]) -> list[HiringPost]:
    """
    Scrape LinkedIn Jobs for the given search terms and return
    deduplicated HiringPost objects.

    Only jobs located in Bangalore/Bengaluru or marked as remote are kept.

    JobSpy keeps requests low-volume and mimics real browser behaviour,
    so it works reliably from GitHub Actions at once-daily frequency.
    """
    results_map: dict[str, HiringPost] = {}

    logger.info(
        "Scraping LinkedIn Jobs via JobSpy — %d search terms, location=%r, hours_old=%d",
        len(search_terms), JOB_LOCATION, HOURS_OLD,
    )

    for term in search_terms:
        logger.info("  Searching: %r …", term)
        try:
            df = scrape_jobs(
                site_name=["linkedin"],
                search_term=term,
                location=JOB_LOCATION,
                results_wanted=MAX_RESULTS_PER_TERM,
                hours_old=HOURS_OLD,
                linkedin_fetch_description=True,
                verbose=0,
            )
        except Exception:
            logger.warning("JobSpy failed for term %r:\n%s", term, traceback.format_exc())
            continue

        if df is None or df.empty:
            logger.info("    No results for %r", term)
            continue

        logger.info("    %d listings returned", len(df))

        kept = 0
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            if not _is_relevant_location(row_dict):
                continue
            post = _row_to_post(row_dict)
            if post and post.post_id not in results_map:
                results_map[post.post_id] = post
                kept += 1

        logger.info("    %d kept after Bangalore/remote filter", kept)

    total = len(results_map)
    logger.info("Unique hiring listings found: %d", total)

    if total == 0:
        logger.warning(
            "No listings returned. This can happen if LinkedIn throttled the "
            "request. The daily scheduled run (not manual trigger) is less "
            "likely to be throttled."
        )

    return list(results_map.values())
