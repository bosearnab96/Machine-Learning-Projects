"""Poll LinkedIn's 'My Network → Manage invitations → Sent' to detect accepts.

A sent invitation disappears from the Sent list when the recipient either
accepts or withdraws it. We can't tell which from the Sent list alone, so
we additionally check the profile's primary button: if it's 'Message',
the person is now 1st-degree (= accepted). If it still reads 'Pending',
we leave the row as invite_sent.

Run this once or twice a day; no outreach happens here, just state transitions.
"""

import logging

from playwright.async_api import Page, TimeoutError as PWTimeout

import config
import human
import storage
from browser import launch_context, bail_if_checkpoint


logger = logging.getLogger(__name__)


async def _is_connected(page: Page) -> bool:
    """On the current profile page, detect 1st-degree status."""
    # 1st-degree badge e.g. "1st" near the name.
    badge = page.locator("main span:has-text('1st')").first
    if await badge.count():
        return True
    # Or the primary action says Message (not Connect/Pending).
    msg = page.locator("main button:has-text('Message')").first
    if await msg.count() and await msg.is_visible():
        pending = page.locator("main button:has-text('Pending')").first
        if not await pending.count():
            return True
    return False


async def run_watcher() -> None:
    """Sweep invite_sent rows; promote to accepted if 1st-degree now."""
    with storage.connect() as conn:
        rows = conn.execute(
            "SELECT url, first_name FROM profiles "
            "WHERE status='invite_sent' AND bucket='growth' "
            "ORDER BY invited_at ASC LIMIT 40"
        ).fetchall()
    rows = [dict(r) for r in rows]
    if not rows:
        logger.info("No invite_sent rows to check.")
        return

    async with launch_context() as ctx:
        page = await ctx.new_page()
        # Light warm-up — this is a read-only sweep but we still want to
        # look like a user checking their network, not a scraper.
        await page.goto(
            "https://www.linkedin.com/mynetwork/",
            wait_until="domcontentloaded",
        )
        await human.jitter_sleep(2.5, 5.0)
        await human.human_scroll(page, 6)

        for i, row in enumerate(rows):
            url = row["url"]
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            except PWTimeout:
                continue
            if await bail_if_checkpoint(page, "watcher"):
                logger.warning("Checkpoint hit during watcher — stopping.")
                break
            await human.jitter_sleep(2.0, 4.5)
            # Very light scroll — we're just peeking.
            await human.human_scroll(page, 3)

            if await _is_connected(page):
                storage.mark_status(url, "accepted", accepted_at=None)
                logger.info("   ✓ accepted: %s (%s)", row.get("first_name"), url)

            # Modest pause between profile views — this loop moves a bit faster
            # than outreach but still shouldn't rip through 40 profiles in 2 min.
            await human.jitter_sleep(18, 45)

        await page.close()
