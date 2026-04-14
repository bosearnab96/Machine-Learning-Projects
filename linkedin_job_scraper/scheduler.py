"""
scheduler.py — Wires everything together and runs on a daily schedule.

Modes:
  python scheduler.py          → starts the persistent background scheduler
  python scheduler.py --now    → run one scrape+email cycle immediately
  python scheduler.py --catchup-to EMAIL
                               → send full 7-day Tech/SDE history to EMAIL,
                                 bypassing dedup (use once for new recipients)

Two digests are sent on each run:
  1. Tech/SDE Digest    — software engineering, data, infra, ML roles
  2. Generalist Digest  — strategy, growth, ops, creator economy, revenue roles

Both digests are filtered to Bangalore/Bengaluru + remote openings from the
last 7 days, with posts grouped by day within each email.
"""

import argparse
import logging
import sys

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

def run_catchup(email: str) -> None:
    """
    Fetch the full 7-day Tech/SDE window and send it to *email* without
    touching seen_posts.db.  Use once when adding a new recipient who has
    never received the digest before.
    """
    logger.info("━━━  Catchup send to %s  ━━━", email)
    posts = fetch_hiring_posts(TECH_SEARCH_TERMS)
    logger.info("Fetched %d posts for catchup (no dedup applied).", len(posts))
    send_digest(posts, "LinkedIn Tech / SDE Digest", [email])
    logger.info("━━━  Catchup complete  ━━━\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="LinkedIn Hiring Post Scraper")
    parser.add_argument(
        "--now",
        action="store_true",
        help="Run one scrape+email cycle immediately and exit.",
    )
    parser.add_argument(
        "--catchup-to",
        metavar="EMAIL",
        help=(
            "Send full 7-day Tech/SDE history to EMAIL, bypassing dedup. "
            "Use once when adding a new recipient."
        ),
    )
    args = parser.parse_args()

    if args.catchup_to:
        logger.info("Running catchup mode for %s.", args.catchup_to)
        run_catchup(args.catchup_to)
        return

    # Always initialise the DB first for normal runs.
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
