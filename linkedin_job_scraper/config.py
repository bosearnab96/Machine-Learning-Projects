"""
config.py — Centralised settings loaded from environment variables.
Copy .env.example → .env and fill in your values before running.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── LinkedIn credentials ──────────────────────────────────────────────────────
LINKEDIN_EMAIL    = os.environ["LINKEDIN_EMAIL"]
LINKEDIN_PASSWORD = os.environ["LINKEDIN_PASSWORD"]

# ── Keywords used to detect hiring posts ─────────────────────────────────────
# Extend this list freely — matching is case-insensitive.
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
    "talent acquisition",
    "referral",
    "dm me",
    "reach out",
    "#hiring",
    "#opentowork",
    "#job",
    "#jobs",
    "#careers",
    "#recruitment",
]

# ── LinkedIn search config ────────────────────────────────────────────────────
# URNs of people/companies you want to monitor.
# Leave empty to do a keyword-based feed search instead.
PEOPLE_URNS_TO_MONITOR: list[str] = []

# Keyword query sent to LinkedIn's post-search endpoint.
SEARCH_QUERY = "hiring OR \"open role\" OR \"open position\" OR \"we are hiring\""

# How many posts to fetch per run (LinkedIn paginates in 10s).
MAX_POSTS_PER_RUN = 50

# ── Gmail / SMTP settings ─────────────────────────────────────────────────────
GMAIL_SENDER   = os.environ["GMAIL_SENDER"]    # your Gmail address
GMAIL_PASSWORD = os.environ["GMAIL_PASSWORD"]  # App Password (not account password)
ALERT_RECIPIENT = os.environ.get("ALERT_RECIPIENT", GMAIL_SENDER)

# ── Storage ───────────────────────────────────────────────────────────────────
DB_PATH = os.environ.get("DB_PATH", "seen_posts.db")

# ── Scheduler ─────────────────────────────────────────────────────────────────
# Time-of-day to send the daily digest (24-hour clock, local time).
DIGEST_HOUR   = int(os.environ.get("DIGEST_HOUR", "18"))   # 6 PM
DIGEST_MINUTE = int(os.environ.get("DIGEST_MINUTE", "0"))
