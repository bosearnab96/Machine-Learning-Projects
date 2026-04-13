"""
config.py — All settings loaded from environment variables / .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Search queries ────────────────────────────────────────────────────────────
# Each query is sent to DuckDuckGo with timelimit="d" (last 24 h).
# Results are filtered to linkedin.com/posts and linkedin.com/feed URLs only.
# Customise freely — add roles, locations, industries, etc.
SEARCH_QUERIES = [
    'site:linkedin.com "we are hiring" OR "we\'re hiring" OR "now hiring"',
    'site:linkedin.com "open role" OR "open position" OR "open requisition"',
    'site:linkedin.com "#hiring" OR "join our team" OR "job opening"',
    'site:linkedin.com "looking for" AND ("engineer" OR "manager" OR "analyst" OR "designer")',
    'site:linkedin.com "apply now" OR "apply here" OR "dm me" AND "hiring"',
]

# Max results per query (DuckDuckGo caps around 20-25 for time-limited searches)
MAX_SEARCH_RESULTS = int(os.environ.get("MAX_SEARCH_RESULTS", "25"))

# Seconds to wait between queries (avoids DuckDuckGo rate limits)
SEARCH_PAUSE_SECONDS = float(os.environ.get("SEARCH_PAUSE_SECONDS", "2"))

# ── Keyword filter ────────────────────────────────────────────────────────────
# A post must match at least one of these to be included in the digest.
HIRING_KEYWORDS = [
    "we are hiring",
    "we're hiring",
    "now hiring",
    "open role",
    "open position",
    "open requisition",
    "open req",
    "job opening",
    "looking for",
    "join our team",
    "join my team",
    "apply now",
    "apply here",
    "we have an opening",
    "exciting opportunity",
    "referral",
    "dm me",
    "#hiring",
    "#opentowork",
    "#job",
    "#jobs",
    "#careers",
    "#recruitment",
    "hiring",
]

# ── Lookback window ───────────────────────────────────────────────────────────
# DuckDuckGo already limits to last 24 h; this is a secondary safety filter.
LOOKBACK_HOURS = int(os.environ.get("LOOKBACK_HOURS", "48"))

# ── Gmail / SMTP ──────────────────────────────────────────────────────────────
GMAIL_SENDER    = os.environ["GMAIL_SENDER"]
GMAIL_PASSWORD  = os.environ["GMAIL_PASSWORD"]
ALERT_RECIPIENT = os.environ.get("ALERT_RECIPIENT", GMAIL_SENDER)

# ── Storage ───────────────────────────────────────────────────────────────────
DB_PATH = os.environ.get("DB_PATH", "seen_posts.db")

# ── Scheduler ─────────────────────────────────────────────────────────────────
DIGEST_HOUR   = int(os.environ.get("DIGEST_HOUR", "2"))    # 2:30 AM UTC = 8 AM IST
DIGEST_MINUTE = int(os.environ.get("DIGEST_MINUTE", "30"))
