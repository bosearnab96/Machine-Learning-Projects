"""
config.py — All settings loaded from environment variables / .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── LinkedIn Jobs search ───────────────────────────────────────────────────────
# JobSpy searches LinkedIn Jobs for each term below.
# Add or remove roles you care about. Keep the list short (3-6 terms) to stay
# well within LinkedIn's undocumented rate limits.
JOB_SEARCH_TERMS = [
    "software engineer",
    "product manager",
    "data scientist",
    "engineering manager",
    "machine learning engineer",
]

# Geographic filter — "India", "Mumbai", "Bangalore", etc.
JOB_LOCATION = os.environ.get("JOB_LOCATION", "India")

# Only include jobs posted within this many hours (24 = today's postings only)
HOURS_OLD = int(os.environ.get("HOURS_OLD", "24"))

# Max listings fetched per search term
MAX_RESULTS_PER_TERM = int(os.environ.get("MAX_RESULTS_PER_TERM", "25"))

# ── Keyword filter ────────────────────────────────────────────────────────────
# Used to extract badge labels shown in the email. All JobSpy results are
# hiring listings by definition, so this is display-only.
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

# ── Gmail / SMTP ──────────────────────────────────────────────────────────────
GMAIL_SENDER    = os.environ["GMAIL_SENDER"]
GMAIL_PASSWORD  = os.environ["GMAIL_PASSWORD"]
ALERT_RECIPIENT = os.environ.get("ALERT_RECIPIENT", GMAIL_SENDER)

# ── Storage ───────────────────────────────────────────────────────────────────
DB_PATH = os.environ.get("DB_PATH", "seen_posts.db")

# ── Scheduler ─────────────────────────────────────────────────────────────────
DIGEST_HOUR   = int(os.environ.get("DIGEST_HOUR", "2"))    # 2:30 AM UTC = 8 AM IST
DIGEST_MINUTE = int(os.environ.get("DIGEST_MINUTE", "30"))
