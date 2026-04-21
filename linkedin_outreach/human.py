"""Human-like browser behavior primitives.

Each function takes a Playwright Page and performs an action the way a real
person would: with jitter, eased motion, small mistakes, and pauses for
cognition. None of these return values — they're side-effectful and slow
on purpose.
"""

import asyncio
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from playwright.async_api import Page

import config


# ── Time helpers ─────────────────────────────────────────────────────────────

def in_working_hours() -> bool:
    now = datetime.now(ZoneInfo(config.LOCAL_TZ))
    if now.weekday() not in config.WORK_DAYS:
        return False
    return config.WORK_START_HOUR <= now.hour < config.WORK_END_HOUR


async def jitter_sleep(low: float, high: float) -> None:
    """Sleep a random duration in [low, high]. Always use this, never asyncio.sleep directly."""
    await asyncio.sleep(random.uniform(low, high))


def seconds_until_next_action() -> float:
    """Draw the cooldown between outreach actions.

    Hourly rate math: at MAX 4/hr the mean gap is 900s, at MIN 2/hr it's 1800s.
    We sample uniformly between those and add ±20% jitter.
    """
    max_gap = 3600.0 / config.MIN_REQUESTS_PER_HOUR
    min_gap = 3600.0 / config.MAX_REQUESTS_PER_HOUR
    base = random.uniform(min_gap, max_gap)
    return base * random.uniform(0.8, 1.2)


# ── Bezier mouse motion ──────────────────────────────────────────────────────

def _bezier_points(p0, p1, p2, p3, steps: int):
    """Cubic bezier — returns `steps` (x, y) tuples."""
    pts = []
    for i in range(steps):
        t = i / (steps - 1)
        x = (1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * p1[0] + \
            3 * (1 - t) * t ** 2 * p2[0] + t ** 3 * p3[0]
        y = (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * p1[1] + \
            3 * (1 - t) * t ** 2 * p2[1] + t ** 3 * p3[1]
        pts.append((x, y))
    return pts


async def move_mouse_humanly(page: Page, target_x: float, target_y: float) -> None:
    """Move cursor from current position to target along a curved path."""
    # Playwright doesn't expose current mouse position; we track loosely via viewport.
    start_x = random.uniform(100, config.VIEWPORT["width"] - 100)
    start_y = random.uniform(100, config.VIEWPORT["height"] - 100)

    # Two control points offset perpendicular to the line — gives a natural arc.
    mx, my = (start_x + target_x) / 2, (start_y + target_y) / 2
    dx, dy = target_x - start_x, target_y - start_y
    perp_x, perp_y = -dy, dx
    norm = max(1.0, (perp_x ** 2 + perp_y ** 2) ** 0.5)
    curve = random.uniform(40, 120)
    c1 = (mx + perp_x / norm * curve * random.uniform(-1, 1),
          my + perp_y / norm * curve * random.uniform(-1, 1))
    c2 = (mx + perp_x / norm * curve * random.uniform(-1, 1),
          my + perp_y / norm * curve * random.uniform(-1, 1))

    steps = random.randint(18, 38)
    for x, y in _bezier_points((start_x, start_y), c1, c2, (target_x, target_y), steps):
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.005, 0.025))


async def click_humanly(page: Page, selector: str) -> None:
    """Hover near, pause (reading), then click with micro-offset."""
    locator = page.locator(selector).first
    box = await locator.bounding_box()
    if not box:
        # Element not visible yet — fall back to Playwright's own click.
        await locator.click()
        return
    target_x = box["x"] + box["width"] / 2 + random.uniform(-box["width"] / 4, box["width"] / 4)
    target_y = box["y"] + box["height"] / 2 + random.uniform(-box["height"] / 4, box["height"] / 4)
    await move_mouse_humanly(page, target_x, target_y)
    await jitter_sleep(0.18, 0.55)  # "deciding" pause
    await page.mouse.click(target_x, target_y, delay=random.randint(40, 140))


# ── Scrolling ────────────────────────────────────────────────────────────────

async def human_scroll(page: Page, total_seconds: float) -> None:
    """Scroll the page in bursts for roughly `total_seconds`.

    Each burst uses variable pixel deltas; between bursts we pause as if
    reading. ~20% chance of scrolling back up mid-session.
    """
    elapsed = 0.0
    while elapsed < total_seconds:
        direction = 1 if random.random() > 0.18 else -1
        burst_pixels = random.randint(180, 820) * direction
        # Break burst into mini-wheel events so it doesn't look like a single jump.
        chunks = random.randint(3, 7)
        per_chunk = burst_pixels // chunks
        for _ in range(chunks):
            await page.mouse.wheel(0, per_chunk + random.randint(-30, 30))
            await asyncio.sleep(random.uniform(0.05, 0.18))
        pause = random.uniform(config.SCROLL_PAUSE_MIN, config.SCROLL_PAUSE_MAX)
        await asyncio.sleep(pause)
        elapsed += pause + 0.8


async def dwell_on_profile(page: Page) -> None:
    """Read a profile the way a human would before acting on it.

    Flow: small pause → scroll through body → pause on what looks like
    the Experience section → occasional scroll back up → settle near top.
    """
    await jitter_sleep(1.0, 2.8)  # first-paint gaze
    dwell_total = random.uniform(config.PROFILE_DWELL_MIN, config.PROFILE_DWELL_MAX)

    # Phase 1: scroll down slowly
    await human_scroll(page, dwell_total * 0.55)

    # Phase 2: linger on Experience if visible
    try:
        exp = page.locator("section:has(div#experience), section:has-text('Experience')").first
        if await exp.count():
            await exp.scroll_into_view_if_needed(timeout=2500)
            await jitter_sleep(2.2, 5.5)
    except Exception:
        pass

    # Phase 3: sometimes scroll back toward top
    if random.random() < 0.55:
        await page.mouse.wheel(0, -random.randint(600, 1400))
        await jitter_sleep(0.8, 2.0)

    # Phase 4: small final idle
    await jitter_sleep(1.0, 3.0)


async def warmup_feed(page: Page) -> None:
    """Before the first outreach of a session, scroll the home feed briefly."""
    await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
    await jitter_sleep(2.0, 4.5)
    for _ in range(config.WARMUP_FEED_SCROLLS):
        await human_scroll(page, random.uniform(8, 18))


# ── Typing ───────────────────────────────────────────────────────────────────

async def type_humanly(page: Page, selector: str, text: str) -> None:
    """Type text into a field one key at a time, with realistic timing + typos."""
    await click_humanly(page, selector)
    await jitter_sleep(0.4, 1.1)

    for ch in text:
        if random.random() < config.TYPO_RATE and ch.isalpha():
            # Hit a neighbor key, notice, backspace, then type the right one.
            wrong = random.choice("abcdefghijklmnopqrstuvwxyz")
            await page.keyboard.type(wrong, delay=random.randint(
                config.TYPE_DELAY_MIN_MS, config.TYPE_DELAY_MAX_MS))
            await jitter_sleep(0.15, 0.45)
            await page.keyboard.press("Backspace")
            await jitter_sleep(0.1, 0.3)

        delay = random.randint(config.TYPE_DELAY_MIN_MS, config.TYPE_DELAY_MAX_MS)
        # Slight pause at punctuation and line breaks, like a human gathering thought.
        if ch in ".,;:!?":
            delay += random.randint(120, 350)
        if ch == "\n":
            await page.keyboard.press("Shift+Enter")
            await jitter_sleep(0.25, 0.7)
            continue
        await page.keyboard.type(ch, delay=delay)

    await jitter_sleep(0.8, 2.2)  # re-read pause before sending


# ── Session shaping ──────────────────────────────────────────────────────────

async def post_action_cooldown(action_index: int) -> None:
    """Sleep between outreach actions — longer every COFFEE_BREAK_EVERY_N."""
    if action_index > 0 and action_index % config.COFFEE_BREAK_EVERY_N == 0:
        secs = random.uniform(config.COFFEE_BREAK_MIN_SEC, config.COFFEE_BREAK_MAX_SEC)
    else:
        secs = max(
            seconds_until_next_action(),
            random.uniform(config.COOLDOWN_MIN, config.COOLDOWN_MAX),
        )
    await asyncio.sleep(secs)
