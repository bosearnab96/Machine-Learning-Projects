"""Entrypoint.

Usage:
    python -m linkedin_outreach.cli login                    # one-time manual login
    python -m linkedin_outreach.cli discover --company Blissclub
    python -m linkedin_outreach.cli ingest                   # load reviewed CSVs
    python -m linkedin_outreach.cli connect [--max 4]        # send bare invites
    python -m linkedin_outreach.cli inmail  [--max 2]        # send InMails
    python -m linkedin_outreach.cli watch                    # detect accepts
    python -m linkedin_outreach.cli dm      [--max 4]        # follow-up DMs
    python -m linkedin_outreach.cli status                   # summary counts

Typical daily rhythm:
    morning:  watch, then dm
    midday:   connect
    evening:  inmail (only 2-3/day to avoid burning credits)
    one-off:  discover (1 company per run)
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Make sibling modules importable when run as a script.
sys.path.insert(0, str(Path(__file__).parent))

import config
import storage
from browser import launch_context


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


async def cmd_login() -> None:
    """Open a Chromium window pointed at LinkedIn so you can log in once.

    On subsequent runs the persistent profile at config.CHROME_PROFILE_DIR
    keeps your session alive — no more password prompts or OTPs.
    """
    async with launch_context() as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://www.linkedin.com/login")
        print("→ Log in manually in the browser window. Close it when done.")
        # Wait until the user closes the page.
        try:
            while not page.is_closed():
                await asyncio.sleep(1.0)
        except Exception:
            pass


async def cmd_discover(company: str) -> None:
    from discovery import discover_for_company
    out = await discover_for_company(company)
    print(f"Wrote → {out}")


def cmd_ingest() -> None:
    from ingest import ingest_all
    ingest_all()


async def cmd_connect(max_actions: int | None) -> None:
    from sender_connect import run_connect_loop
    await run_connect_loop(max_actions=max_actions)


async def cmd_inmail(max_actions: int | None) -> None:
    from sender_inmail import run_inmail_loop
    await run_inmail_loop(max_actions=max_actions)


async def cmd_watch() -> None:
    from accept_watcher import run_watcher
    await run_watcher()


async def cmd_dm(max_actions: int | None) -> None:
    from sender_dm import run_dm_loop
    await run_dm_loop(max_actions=max_actions)


def cmd_status() -> None:
    with storage.connect() as conn:
        rows = conn.execute(
            "SELECT bucket, status, COUNT(*) AS n FROM profiles "
            "GROUP BY bucket, status ORDER BY bucket, status"
        ).fetchall()
        week = storage.invites_this_week()
        today = storage.invites_today()
    print(f"Invites: today={today}, this week={week} "
          f"(caps: {config.MAX_REQUESTS_PER_DAY}/day, "
          f"{config.MAX_REQUESTS_PER_WEEK}/week)")
    print()
    print(f"{'bucket':<12} {'status':<18} count")
    print("-" * 40)
    for r in rows:
        print(f"{r['bucket']:<12} {r['status']:<18} {r['n']}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="linkedin_outreach")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login", help="Open browser for one-time manual login.")

    disc = sub.add_parser("discover", help="People-search one company → CSV.")
    disc.add_argument("--company", required=True)

    sub.add_parser("ingest", help="Load reviewed CSVs into DB as queued.")

    con = sub.add_parser("connect", help="Send bare connection requests.")
    con.add_argument("--max", type=int, default=None)

    im = sub.add_parser("inmail", help="Send InMails to d2c_head bucket.")
    im.add_argument("--max", type=int, default=None)

    sub.add_parser("watch", help="Check which invites were accepted.")

    dm = sub.add_parser("dm", help="Send full-pitch DM to accepted profiles.")
    dm.add_argument("--max", type=int, default=None)

    sub.add_parser("status", help="Print counts per bucket/status.")
    return p


def main() -> None:
    args = build_parser().parse_args()

    if args.cmd == "login":
        asyncio.run(cmd_login())
    elif args.cmd == "discover":
        asyncio.run(cmd_discover(args.company))
    elif args.cmd == "ingest":
        cmd_ingest()
    elif args.cmd == "connect":
        asyncio.run(cmd_connect(args.max))
    elif args.cmd == "inmail":
        asyncio.run(cmd_inmail(args.max))
    elif args.cmd == "watch":
        asyncio.run(cmd_watch())
    elif args.cmd == "dm":
        asyncio.run(cmd_dm(args.max))
    elif args.cmd == "status":
        cmd_status()


if __name__ == "__main__":
    main()
