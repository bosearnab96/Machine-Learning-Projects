"""Option A, step 2: DM the full template to profiles that accepted.

Run after `watch_accepts` has moved profiles from invite_sent → accepted.

Per-profile flow:
    1. goto(profile url) — verify still connected (defensive)
    2. click "Message"
    3. wait for compose panel
    4. type the rendered DM (humanly), occasional typo+backspace
    5. send (Cmd/Ctrl+Enter or click the send icon)
    6. mark dm_sent
"""

import logging

from playwright.async_api import Page, TimeoutError as PWTimeout

import config
import human
import storage
from browser import launch_context, bail_if_checkpoint
from message_templates import render_dm


logger = logging.getLogger(__name__)


async def _open_message_compose(page: Page) -> bool:
    msg_btn = page.locator("main button:has-text('Message')").first
    if not await msg_btn.count():
        return False
    await human.click_humanly(page, "main button:has-text('Message')")
    try:
        await page.locator(
            "div[aria-label*='messaging'], div.msg-form__contenteditable"
        ).first.wait_for(timeout=6000)
    except PWTimeout:
        return False
    return True


async def _send_dm(page: Page, text: str) -> bool:
    editor = "div.msg-form__contenteditable"
    try:
        await page.locator(editor).first.wait_for(timeout=5000)
    except PWTimeout:
        return False

    await human.type_humanly(page, editor, text)
    await human.jitter_sleep(1.2, 3.0)

    # Prefer clicking the Send button; Cmd+Enter is fallback.
    send = page.locator("button.msg-form__send-button:not([disabled])").first
    if await send.count():
        await human.click_humanly(page, "button.msg-form__send-button:not([disabled])")
    else:
        await page.keyboard.press("Meta+Enter")
    await human.jitter_sleep(1.2, 2.5)
    return True


async def run_dm_loop(max_actions: int | None = None) -> None:
    if not human.in_working_hours():
        logger.info("Outside working hours — exiting.")
        return

    async with launch_context() as ctx:
        page = await ctx.new_page()
        await human.warmup_feed(page)
        await human.jitter_sleep(3, 7)

        action_index = 0
        while True:
            if max_actions is not None and action_index >= max_actions:
                break
            if not human.in_working_hours():
                break

            batch = storage.accepted_awaiting_dm(limit=1)
            if not batch:
                logger.info("No accepted profiles awaiting DM.")
                break
            profile = batch[0]
            url = profile["url"]
            first_name = profile.get("first_name") or "there"
            logger.info("→ DM to %s (%s)", first_name, url)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            except PWTimeout:
                storage.mark_status(url, "failed", error="goto_timeout")
                continue

            if await bail_if_checkpoint(page, "dm"):
                storage.mark_status(url, "checkpoint")
                break

            await human.dwell_on_profile(page)

            if not await _open_message_compose(page):
                storage.mark_status(url, "failed", error="no_message_button")
                continue

            text = render_dm(first_name)
            ok = await _send_dm(page, text)
            if ok:
                storage.mark_status(url, "dm_sent", dm_sent_at=None)
                storage.log_rate("dm")
                action_index += 1
                logger.info("   ✓ DM sent")
            else:
                storage.mark_status(url, "failed", error="send_dm_failed")

            await human.post_action_cooldown(action_index)

        await page.close()
