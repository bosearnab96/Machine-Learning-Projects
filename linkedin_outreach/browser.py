"""Playwright persistent-context helper.

Using a persistent profile means you log in once (manually, in a real Chromium
window), and every subsequent script run reuses the cookies / 2FA state / UA
fingerprint. LinkedIn sees one consistent "device" across runs instead of a
fresh session every time — which is the #1 checkpoint trigger.
"""

from contextlib import asynccontextmanager

from playwright.async_api import async_playwright, BrowserContext
from playwright_stealth import stealth_async

import config


CHECKPOINT_MARKERS = [
    "checkpoint/challenge",
    "uas/login",           # kicked back to login
    "captcha",
    "/authwall",
]


@asynccontextmanager
async def launch_context():
    """Yield a ready BrowserContext. Caller is responsible for closing pages."""
    config.CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        ctx: BrowserContext = await p.chromium.launch_persistent_context(
            user_data_dir=str(config.CHROME_PROFILE_DIR),
            headless=config.HEADLESS,
            viewport=config.VIEWPORT,
            user_agent=config.USER_AGENT,
            locale="en-IN",
            timezone_id=config.LOCAL_TZ,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )

        # Apply stealth patches to every new page in this context.
        async def _on_page(page):
            try:
                await stealth_async(page)
            except Exception:
                pass

        ctx.on("page", _on_page)
        for page in ctx.pages:
            await _on_page(page)

        try:
            yield ctx
        finally:
            await ctx.close()


def is_checkpoint_url(url: str) -> bool:
    return any(marker in url for marker in CHECKPOINT_MARKERS)


async def bail_if_checkpoint(page, label: str) -> bool:
    """Return True (and screenshot) if the page looks like a LinkedIn checkpoint."""
    url = page.url
    if is_checkpoint_url(url):
        ts = page.url.split("?")[0].split("/")[-1] or "checkpoint"
        path = config.SCREENSHOTS_DIR / f"{label}_{ts}.png"
        try:
            await page.screenshot(path=str(path), full_page=True)
        except Exception:
            pass
        return True
    # Also detect the "weekly invitation limit" interstitial by text.
    try:
        body = await page.locator("body").inner_text(timeout=1500)
        if "weekly invitation limit" in body.lower() or "you've reached the limit" in body.lower():
            await page.screenshot(path=str(config.SCREENSHOTS_DIR / f"{label}_weekly_limit.png"))
            return True
    except Exception:
        pass
    return False
