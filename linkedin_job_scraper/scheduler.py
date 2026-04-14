"""
scheduler.py — Wires everything together and runs on a daily schedule.

Two modes:
  python scheduler.py          → starts the persistent background scheduler
  python scheduler.py --now    → run one scrape+email cycle immediately (good for testing)

Two digests are sent on each run:
  1. Tech/SDE Digest    — software engineering, data, infra, ML roles
  2. Generalist Digest  — strategy, growth, ops, creator economy, revenue roles

Both digests are filtered to Bangalore/Bengaluru + remote openings from the
last 7 days, with posts grouped by day within each email.
"""

import argparse
import logging
import sys
import time

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import (
    DIGEST_HOUR,
    DIGEST_MINUTE,
    GENERALIST_DIGEST_RECIPIENTS,
    GENERALIST_SEARCH_TERMS,
    TECH_DIGEST_RECIPIENTS,
    TECH_SEARCH_TERMS,
)
from emailer import send_digest
from scraper import fetch_hiring_posts
from storage import filter_new_posts, init_db

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scraper.log"),
    ],
)
logger = logging.getLogger(__name__)


# ── Core pipeline ──────────────────────────────────────────────────────────────

def run_pipeline(search_terms: list[str], digest_title: str,
                 recipients: list[str]) -> None:
    """
    Full pipeline for one digest category:
      1. Scrape LinkedIn for hiring posts matching the given search terms
      2. Filter to Bangalore / remote (done inside fetch_hiring_posts)
      3. Deduplicate against SQLite store
      4. Send email digest with new posts, grouped by day
    """
    logger.info("━━━  Pipeline starting: %s  ━━━", digest_title)
    try:
        # Step 1 — scrape
        posts = fetch_hiring_posts(search_terms)

        # Step 2 — deduplicate
        new_posts = filter_new_posts(posts)
        logger.info("New posts after deduplication: %d", len(new_posts))

        # Step 3 — send email
        send_digest(new_posts, digest_title, recipients)

        logger.info("━━━  Pipeline complete: %s  ━━━\n", digest_title)

    except Exception as exc:
        logger.exception("Pipeline failed (%s): %s", digest_title, exc)
        raise


def run_all_pipelines() -> None:
    """Run both the Tech and Generalist digest pipelines in sequence."""
    run_pipeline(TECH_SEARCH_TERMS,       "LinkedIn Tech / SDE Digest",   TECH_DIGEST_RECIPIENTS)
    run_pipeline(GENERALIST_SEARCH_TERMS, "LinkedIn Generalist Digest",    GENERALIST_DIGEST_RECIPIENTS)


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
        run_all_pipelines()
        return

    # ── Persistent scheduler ──────────────────────────────────────────────────
    scheduler = BlockingScheduler(timezone="UTC")

    trigger = CronTrigger(hour=DIGEST_HOUR, minute=DIGEST_MINUTE)
    scheduler.add_job(
        run_all_pipelines,
        trigger=trigger,
        id="daily_digest",
        name="LinkedIn Hiring Digest (Tech + Generalist)",
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
