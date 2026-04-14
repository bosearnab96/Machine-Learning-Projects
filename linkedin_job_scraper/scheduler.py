"""
scheduler.py — Wires everything together and runs on a daily schedule.

Two modes:
  python scheduler.py          → starts the persistent background scheduler
  python scheduler.py --now    → run one scrape+email cycle immediately (good for testing)
"""

import argparse
import logging
import sys
import time

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import DIGEST_HOUR, DIGEST_MINUTE
from emailer import send_digest
from scraper import fetch_hiring_posts
from storage import filter_new_posts, init_db

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scraper.log"),
    ],
)
logger = logging.getLogger(__name__)


# ── Core pipeline ──────────────────────────────────────────────────────────────

def run_pipeline() -> None:
    """
    Full pipeline:
      1. Scrape LinkedIn for hiring posts
      2. Filter out posts already seen (dedup via SQLite)
      3. Send email digest with new posts
    """
    logger.info("━━━  Pipeline starting  ━━━")
    try:
        # Step 1 — scrape
        posts = fetch_hiring_posts()

        # Step 2 — deduplicate
        new_posts = filter_new_posts(posts)
        logger.info("New posts after deduplication: %d", len(new_posts))

        # Step 3 — send email
        send_digest(new_posts)

        logger.info("━━━  Pipeline complete  ━━━\n")

    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        raise


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="LinkedIn Hiring Post Scraper")
    parser.add_argument(
        "--now",
        action="store_true",
        help="Run one scrape+email cycle immediately and exit.",
    )
    args = parser.parse_args()

    # Always initialise the DB first.
    init_db()

    if args.now:
        logger.info("Running in one-shot mode (--now flag).")
        run_pipeline()
        return

    # ── Persistent scheduler ──────────────────────────────────────────────────
    scheduler = BlockingScheduler(timezone="UTC")

    trigger = CronTrigger(hour=DIGEST_HOUR, minute=DIGEST_MINUTE)
    scheduler.add_job(
        run_pipeline,
        trigger=trigger,
        id="daily_digest",
        name="LinkedIn Hiring Digest",
        max_instances=1,
        replace_existing=True,
    )

    logger.info(
        "Scheduler started. Daily digest will run at %02d:%02d UTC.",
        DIGEST_HOUR,
        DIGEST_MINUTE,
    )
    logger.info("Press Ctrl+C to stop.\n")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
