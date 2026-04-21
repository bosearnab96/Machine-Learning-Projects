"""Option C: send an InMail to a D2C head.

Requires an active Premium / Sales Nav / Recruiter subscription on the
logged-in account — otherwise the "Message" button on a non-connection
profile won't open an InMail compose panel.

Per-profile flow:
    1. goto(profile url)
    2. dwell
    3. click "Message" (on a non-connected profile this opens InMail)
    4. fill subject + body (typed humanly)
    5. send
    6. mark inmail_sent
"""

import logging

from playwright.async_api import Page, TimeoutError as PWTimeout

import config
import human
import storage
from browser import launch_context, bail_if_checkpoint
from message_templates import render_inmail


logger = logging.getLogger(__name__)


async def _open_inmail_compose(page: Page) -> bool:
    # On non-1st-degree profiles with Premium, the primary "Message" button
    # opens an InMail dialog. If the person is 1st degree, it opens a DM.
    btn = page.locator("main button:has-text('Message')").first
    if not await btn.count():
        return False
    await human.click_humanly(page, "main button:has-text('Message')")
    try:
        await page.locator(
            "div[role='dialog']:has-text('InMail'), div.msg-form__contenteditable"
        ).first.wait_for(timeout=8000)
    except PWTimeout:
        return False
    return True


async def _fill_and_send_inmail(page: Page, subject: str, body: str) -> bool:
    subject_input = page.locator(
        "input[placeholder*='Subject'], input[name='subject']"
    ).first
    if await subject_input.count():
        await human.type_humanly(
            page, "input[placeholder*='Subject'], input[name='subject']", subject)

    editor = "div.msg-form__contenteditable, div[contenteditable='true'][role='textbox']"
    try:
        await page.locator(editor).first.wait_for(timeout=5000)
    except PWTimeout:
        return False

    await human.type_humanly(page, editor, body)
    await human.jitter_sleep(1.8, 3.5)  # final review

    send = page.locator(
        "button:has-text('Send'):not([disabled]), "
        "button.msg-form__send-button:not([disabled])"
    ).first
    if not await send.count():
        return False
    await human.click_humanly(
        page,
        "button:has-text('Send'):not([disabled]), "
        "button.msg-form__send-button:not([disabled])",
    )
    await human.jitter_sleep(1.5, 3.0)
    return True


async def run_inmail_loop(max_actions: int | None = None) -> None:
    if not human.in_working_hours():
        logger.info("Outside working hours — exiting.")
        return

    async with launch_context() as ctx:
        page = await ctx.new_page()
        await human.warmup_feed(page)
        await human.jitter_sleep(4, 9)

        action_index = 0
        while True:
            if max_actions is not None and action_index >= max_actions:
                break
            if not human.in_working_hours():
                break

            batch = storage.next_queued(bucket="d2c_head", limit=1)
            if not batch:
                logger.info("No queued d2c_head profiles remaining.")
                break
            profile = batch[0]
            url = profile["url"]
            first_name = profile.get("first_name") or "there"
            logger.info("→ InMail to %s (%s)", first_name, url)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            except PWTimeout:
                storage.mark_status(url, "failed", error="goto_timeout")
                continue

            if await bail_if_checkpoint(page, "inmail"):
                storage.mark_status(url, "checkpoint")
                break

            await human.dwell_on_profile(page)

            if not await _open_inmail_compose(page):
                storage.mark_status(
                    url, "failed",
                    error="no_inmail_compose (Premium active?)")
                continue

            subject, body = render_inmail(first_name)
            ok = await _fill_and_send_inmail(page, subject, body)
            if ok:
                storage.mark_status(url, "inmail_sent", inmail_at=None)
                storage.log_rate("inmail")
                action_index += 1
                logger.info("   ✓ InMail sent")
            else:
                storage.mark_status(url, "failed", error="send_inmail_failed")

            await human.post_action_cooldown(action_index)

        await page.close()
