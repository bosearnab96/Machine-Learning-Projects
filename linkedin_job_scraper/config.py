"""
config.py — Centralised settings loaded from environment variables.
Copy .env.example → .env and fill in your values before running.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── LinkedIn credentials ──────────────────────────────────────────────────────
# Preferred: cookie-based auth (avoids CAPTCHA/challenge blocks on new IPs).
# Set LINKEDIN_LI_AT to your li_at cookie value from your browser session.
# Fallback: username + password (may trigger CHALLENGE on fresh IPs).
# Full cookie string from browser console: copy(document.cookie)
# This is the preferred auth method — paste ALL cookies, not just li_at.
LINKEDIN_COOKIES   = os.environ.get("LINKEDIN_COOKIES", "")
# Legacy individual cookie fields (fallback only)
LINKEDIN_LI_AT     = os.environ.get("LINKEDIN_LI_AT", "")
LINKEDIN_JSESSIONID = os.environ.get("LINKEDIN_JSESSIONID", "")
LINKEDIN_EMAIL     = os.environ.get("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD  = os.environ.get("LINKEDIN_PASSWORD", "")

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

# ── Scraping config ───────────────────────────────────────────────────────────
# How many posts to pull from the home feed per run.
MAX_FEED_POSTS = int(os.environ.get("MAX_FEED_POSTS", "200"))

# How many recent posts to check per 1st-degree connection.
MAX_POSTS_PER_PROFILE = int(os.environ.get("MAX_POSTS_PER_PROFILE", "10"))

# Only surface posts newer than this many hours (default 48h).
# 48h gives a safety buffer in case yesterday's run had an issue.
LOOKBACK_HOURS = int(os.environ.get("LOOKBACK_HOURS", "48"))

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
