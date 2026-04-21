"""Option A: send a BARE connection request (no note).

Per-profile flow:
    1. goto(profile url) — wait for load
    2. dwell_on_profile  — scroll, pause on Experience, maybe back up
    3. find the primary action button
       — if "Connect" → click → click "Send without a note"
       — if "Message" → already connected (rare if CSV is clean) → skip
       — if "Pending" → already invited → skip
       — if "More" menu hides Connect → open menu, then click Connect
    4. mark invite_sent

Abort conditions:
    • weekly/day cap reached        → stop before next profile
    • checkpoint URL / CAPTCHA      → mark profile, exit run
    • "You've reached the weekly invitation limit" overlay → stop
"""

import asyncio
import logging
import random

from playwright.async_api import Page, TimeoutError as PWTimeout

import config
import human
import storage
from browser import launch_context, bail_if_checkpoint


logger = logging.getLogger(__name__)


async def _find_and_click_connect(page: Page) -> str:
    """Try every known path to 'Connect'. Returns a status string."""
    # Path 1 — primary button says "Connect"
    primary = page.locator("main button:has-text('Connect')").first
    if await primary.count() and await primary.is_visible():
        await human.click_humanly(page, "main button:has-text('Connect')")
        return "clicked_primary"

    # Path 2 — "Message" is primary → already 1st-degree connection.
    msg = page.locator("main button:has-text('Message')").first
    if await msg.count() and await msg.is_visible():
        return "already_connected"

    # Path 3 — "Pending" → invite already sent.
    pending = page.locator("main button:has-text('Pending')").first
    if await pending.count() and await pending.is_visible():
        return "invite_pending"

    # Path 4 — Connect hidden under "More" dropdown.
    more = page.locator("main button:has-text('More')").first
    if await more.count():
        await human.click_humanly(page, "main button:has-text('More')")
        await human.jitter_sleep(0.6, 1.4)
        dropdown_connect = page.locator(
            "div[role='menu'] div:has-text('Connect'), "
            "div.artdeco-dropdown__content div[aria-label*='Invite']"
        ).first
        if await dropdown_connect.count():
            await human.click_humanly(
                page,
                "div[role='menu'] div:has-text('Connect'), "
                "div.artdeco-dropdown__content div[aria-label*='Invite']",
            )
            return "clicked_in_more"

    return "no_connect_button"


async def _send_without_note(page: Page) -> bool:
    """After the Connect modal opens, click 'Send' (no note)."""
    # Modal is a dialog with a "Send" button. If LinkedIn prompts "Add a note"
    # first, we explicitly pick "Send without a note".
    try:
        await page.locator("div[role='dialog']").first.wait_for(timeout=5000)
    except PWTimeout:
        return False

    # Sometimes the dialog asks for the person's email ("Are you sure you know
    # this person?") — we bail instead of supplying an email.
    email_field = page.locator("div[role='dialog'] input[name='email']")
    if await email_field.count():
        logger.info("Dialog asks for email — skipping profile.")
        await page.keyboard.press("Escape")
        return False

    send_btn = page.locator(
        "div[role='dialog'] button[aria-label*='Send']"
    ).first
    if not await send_btn.count():
        # Newer UI sometimes says "Send without a note".
        send_btn = page.locator(
            "div[role='dialog'] button:has-text('Send without a note'), "
            "div[role='dialog'] button:has-text('Send now'), "
            "div[role='dialog'] button:has-text('Send')"
        ).first

    if not await send_btn.count():
        return False

    await human.jitter_sleep(0.8, 2.1)  # pause as if reviewing
    await human.click_humanly(
        page,
        "div[role='dialog'] button[aria-label*='Send'], "
        "div[role='dialog'] button:has-text('Send without a note'), "
        "div[role='dialog'] button:has-text('Send now'), "
        "div[role='dialog'] button:has-text('Send')",
    )
    await human.jitter_sleep(1.5, 3.2)
    return True


def _caps_ok() -> tuple[bool, str]:
    if storage.invites_today() >= config.MAX_REQUESTS_PER_DAY:
        return False, "daily cap reached"
    if storage.invites_this_week() >= config.MAX_REQUESTS_PER_WEEK:
        return False, "weekly cap reached"
    return True, ""


async def run_connect_loop(max_actions: int | None = None) -> None:
    """Pull queued growth profiles and send bare connection requests."""
    if not human.in_working_hours():
        logger.info("Outside working hours — exiting.")
        return

    async with launch_context() as ctx:
        page = await ctx.new_page()

        # Warm up before the first request.
        await human.warmup_feed(page)
        await human.jitter_sleep(4, 9)

        action_index = 0
        while True:
            if max_actions is not None and action_index >= max_actions:
                break
            if not human.in_working_hours():
                logger.info("Left working hours — stopping.")
                break
            ok, reason = _caps_ok()
            if not ok:
                logger.info("Cap hit (%s) — stopping.", reason)
                break

            batch = storage.next_queued(bucket="growth", limit=1)
            if not batch:
                logger.info("No queued growth profiles remaining.")
                break
            profile = batch[0]
            url = profile["url"]
            logger.info("→ %s (%s)", profile.get("first_name"), url)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            except PWTimeout:
                storage.mark_status(url, "failed", error="goto_timeout")
                continue

            if await bail_if_checkpoint(page, "connect"):
                storage.mark_status(url, "checkpoint")
                logger.warning("Checkpoint hit — exiting loop.")
                break

            await human.dwell_on_profile(page)

            result = await _find_and_click_connect(page)
            if result == "already_connected":
                storage.mark_status(url, "already_connect")
                continue
            if result == "invite_pending":
                storage.mark_status(url, "invite_sent", invited_at=None)
                continue
            if result == "no_connect_button":
                storage.mark_status(url, "skipped", error="no_connect_button")
                continue

            sent = await _send_without_note(page)
            if sent:
                storage.mark_status(url, "invite_sent", invited_at=None)
                storage.log_rate("invite")
                action_index += 1
                logger.info("   ✓ invite sent (#%d this session)", action_index)
            else:
                storage.mark_status(url, "skipped", error="send_dialog_failed")

            await human.post_action_cooldown(action_index)

        await page.close()
