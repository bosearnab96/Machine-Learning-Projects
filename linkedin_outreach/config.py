"""All tunables for the outreach bot. Loaded from .env with sane defaults."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent

# ── Target companies (Arnab's D2C outreach list) ─────────────────────────────
TARGET_COMPANIES = [
    "Blissclub", "The Souled Store", "DaMENSCH", "Bombay Shirt Company",
    "Foxtale", "82E", "The Whole Truth Foods", "Mokobara",
    "Assembly", "Wakefit", "Atomberg", "Sleep Company",
]

# ── Pacing ───────────────────────────────────────────────────────────────────
# A real person doesn't send at fixed intervals. We draw each delay from a
# uniform range so the hourly rate naturally jitters.
MAX_REQUESTS_PER_HOUR = int(os.environ.get("MAX_REQUESTS_PER_HOUR", "4"))
MIN_REQUESTS_PER_HOUR = int(os.environ.get("MIN_REQUESTS_PER_HOUR", "2"))

# Hard weekly ceiling — LinkedIn's own limit is ~100/week for free accounts.
# Staying well under avoids the "You've reached the weekly invitation limit" page.
MAX_REQUESTS_PER_WEEK = int(os.environ.get("MAX_REQUESTS_PER_WEEK", "40"))
MAX_REQUESTS_PER_DAY  = int(os.environ.get("MAX_REQUESTS_PER_DAY",  "12"))

# ── Working hours ────────────────────────────────────────────────────────────
LOCAL_TZ        = os.environ.get("LOCAL_TZ", "Asia/Kolkata")
WORK_START_HOUR = int(os.environ.get("WORK_START_HOUR", "10"))
WORK_END_HOUR   = int(os.environ.get("WORK_END_HOUR",   "19"))
WORK_DAYS       = [int(d) for d in os.environ.get("WORK_DAYS", "0,1,2,3,4").split(",")]

# ── Browser ──────────────────────────────────────────────────────────────────
CHROME_PROFILE_DIR = Path(os.environ.get("CHROME_PROFILE_DIR", ROOT / "chrome_profile"))
HEADLESS           = os.environ.get("HEADLESS", "false").lower() == "true"
VIEWPORT           = {"width": 1440, "height": 900}
USER_AGENT         = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

# ── Paths ────────────────────────────────────────────────────────────────────
DB_PATH              = ROOT / "outreach.db"
SCREENSHOTS_DIR      = ROOT / "screenshots"
LOGS_DIR             = ROOT / "logs"
PROFILES_GROWTH_CSV  = ROOT / "profiles_growth.csv"
PROFILES_DHEADS_CSV  = ROOT / "profiles_d2c_heads.csv"

SCREENSHOTS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ── Human-behavior knobs ─────────────────────────────────────────────────────
# Seconds to dwell on a profile before clicking Connect/Message.
PROFILE_DWELL_MIN = 12
PROFILE_DWELL_MAX = 35

# Seconds between discrete scroll bursts inside a profile.
SCROLL_PAUSE_MIN = 0.8
SCROLL_PAUSE_MAX = 2.6

# Per-keystroke delay (ms) for typing into InMail/DM.
TYPE_DELAY_MIN_MS = 60
TYPE_DELAY_MAX_MS = 180

# Probability of a "typo → backspace → retype" blip while typing.
TYPO_RATE = 0.04

# Warm-up actions before the first outreach of a session.
WARMUP_FEED_SCROLLS = 2

# Cooldown between outreach actions (seconds). Overrides the rate math if larger.
COOLDOWN_MIN = 60 * 9
COOLDOWN_MAX = 60 * 22

# Longer "coffee break" every N actions.
COFFEE_BREAK_EVERY_N = 3
COFFEE_BREAK_MIN_SEC = 60 * 15
COFFEE_BREAK_MAX_SEC = 60 * 35
