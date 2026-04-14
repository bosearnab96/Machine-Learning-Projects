"""
config.py — All settings loaded from environment variables / .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── LinkedIn Jobs search ───────────────────────────────────────────────────────
# Tech / SDE digest — roles involving coding, infrastructure, data engineering
TECH_SEARCH_TERMS = [
    "software engineer",
    "SDE",
    "software developer",
    "backend engineer",
    "frontend engineer",
    "full stack engineer",
    "data engineer",
    "machine learning engineer",
    "platform engineer",
    "devops engineer",
]

# Generalist digest — strategy, growth, ops, creator economy, revenue roles
GENERALIST_SEARCH_TERMS = [
    "strategy operations",
    "growth",
    "chief of staff",
    "entrepreneur in residence",
    "revenue lead",
    "monetization",
    "creator economy",
    "business operations",
]

# Geographic filter — searches LinkedIn Jobs for this location.
# Remote jobs are always included via post-filter regardless of this value.
JOB_LOCATION = os.environ.get("JOB_LOCATION", "Bangalore, India")

# Only include jobs posted within this many hours (168 = last 7 days)
HOURS_OLD = int(os.environ.get("HOURS_OLD", "168"))

# Max listings fetched per search term
MAX_RESULTS_PER_TERM = int(os.environ.get("MAX_RESULTS_PER_TERM", "25"))

# ── Keyword filter ────────────────────────────────────────────────────────────
# Used to extract badge labels shown in the email.
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
