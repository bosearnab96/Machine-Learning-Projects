"""
scraper.py — Fetches LinkedIn hiring posts via a headless Chromium browser.

Why Playwright instead of linkedin-api / raw requests:
  LinkedIn's voyager API actively redirects direct HTTP requests from
  datacenter IPs (e.g. GitHub Actions) to the login page regardless
  of cookies.  A real browser (Chromium) carries the correct TLS
  fingerprint and browser headers that LinkedIn accepts.  We load the
  user's session cookies into the browser, navigate to the feed, and
  intercept the voyager API JSON responses the browser receives.
"""

import asyncio
import json
import logging
import re
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Response
from playwright_stealth import stealth_async

from config import (
    HIRING_KEYWORDS,
    LINKEDIN_COOKIES,
    LINKEDIN_LI_AT,
    LOOKBACK_HOURS,
    MAX_FEED_POSTS,
)

logger = logging.getLogger(__name__)
RAW_DUMP = Path("raw_feed_dump.json")


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class HiringPost:
    post_id:    str
    author:     str
    author_url: str
    text:       str
    post_url:   str
    posted_at:  datetime
    source:     str = "feed"
    matched_keywords: list[str] = field(default_factory=list)

    def short_preview(self, max_chars: int = 280) -> str:
        cleaned = re.sub(r"\s+", " ", self.text).strip()
        return cleaned[:max_chars] + ("…" if len(cleaned) > max_chars else "")


# ── Keyword matching ──────────────────────────────────────────────────────────

def _extract_keywords(text: str) -> list[str]:
    lower = text.lower()
    return [kw for kw in HIRING_KEYWORDS if kw.lower() in lower]


# ── Cookie helpers ────────────────────────────────────────────────────────────

def _build_playwright_cookies() -> list[dict]:
    """
    Build a list of Playwright-format cookie dicts from the secrets.
    document.cookie misses HttpOnly cookies; li_at is injected separately.
    """
    cookies: list[dict] = []
    seen: set[str] = set()

    for part in (LINKEDIN_COOKIES or "").split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        name, _, value = part.partition("=")
        name = name.strip()
        value = value.strip()
        if name in seen:
            continue
        seen.add(name)
        cookies.append({"name": name, "value": value,
                        "domain": ".linkedin.com", "path": "/"})

    # li_at is HttpOnly → not in document.cookie → inject from secret
    li_at_cookie = {"name": "li_at", "value": LINKEDIN_LI_AT,
                    "domain": ".linkedin.com", "path": "/",
                    "httpOnly": True, "secure": True}
    if "li_at" in seen:
        # replace with secret value (more reliable)
        cookies = [c if c["name"] != "li_at" else li_at_cookie for c in cookies]
    elif LINKEDIN_LI_AT:
        cookies.append(li_at_cookie)

    return cookies


# ── Text / field extraction ───────────────────────────────────────────────────

def _walk_text(obj, depth: int = 0) -> str:
    """Recursively find the longest string stored under a 'text' key."""
    if depth > 8:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        parts = [_walk_text(x, depth + 1) for x in obj]
        return max(parts, key=len) if parts else ""
    if isinstance(obj, dict):
        if "text" in obj and isinstance(obj["text"], str):
            return obj["text"]
        priority = ["commentary", "description", "content"]
        results = []
        seen_keys: set[str] = set()
        for k in priority + [k for k in obj if k not in priority]:
            if k not in seen_keys:
                seen_keys.add(k)
                t = _walk_text(obj[k], depth + 1)
                if t:
                    results.append(t)
        return max(results, key=len) if results else ""
    return ""


def _extract_text(post: dict) -> str:
    commentary = post.get("commentary") or {}
    if isinstance(commentary, dict):
        inner = commentary.get("text") or {}
        if isinstance(inner, dict):
            t = inner.get("text", "")
            if t:
                return t
        elif isinstance(inner, str) and inner:
            return inner
    return _walk_text(post)


def _extract_author(post: dict) -> tuple[str, str]:
    actor = post.get("actor") or {}
    name_node = actor.get("name") or {}
    name_text = name_node.get("text", "") if isinstance(name_node, dict) else ""
    attrs = name_node.get("attributes", []) if isinstance(name_node, dict) else []
    pub_id = ""
    if attrs:
        mini = (attrs[0] or {}).get("miniProfile") or {}
        pub_id = mini.get("publicIdentifier", "")
        if not name_text:
            name_text = f"{mini.get('firstName','')} {mini.get('lastName','')}".strip()
    url = f"https://www.linkedin.com/in/{pub_id}/" if pub_id else ""
    return name_text or "Unknown", url


def _extract_post_id(post: dict) -> str:
    urn = (post.get("dashEntityUrn") or post.get("entityUrn")
           or (post.get("updateMetadata") or {}).get("urn", ""))
    return urn.split(":")[-1] if urn else ""


def _extract_timestamp(post: dict) -> datetime:
    ms = post.get("createdAt") or post.get("publishedAt") or 0
    if isinstance(ms, (int, float)) and ms > 1_000_000_000:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return datetime.now(tz=timezone.utc)


# ── Parser ────────────────────────────────────────────────────────────────────

def _parse(post: dict) -> Optional[HiringPost]:
    try:
        text = _extract_text(post)
        if not text:
            return None
        keywords = _extract_keywords(text)
        if not keywords:
            return None
        post_id = _extract_post_id(post)
        if not post_id:
            import hashlib
            post_id = hashlib.md5(text[:200].encode()).hexdigest()
        author, author_url = _extract_author(post)
        posted_at = _extract_timestamp(post)
        entity_urn = post.get("dashEntityUrn") or post.get("entityUrn", "")
        post_url = (f"https://www.linkedin.com/feed/update/{entity_urn}/"
                    if entity_urn else "")
        return HiringPost(
            post_id=post_id, author=author, author_url=author_url,
            text=text, post_url=post_url, posted_at=posted_at,
            matched_keywords=keywords,
        )
    except Exception:
        logger.debug("Parse error:\n%s", traceback.format_exc())
        return None


# ── Playwright feed fetcher ───────────────────────────────────────────────────

async def _fetch_with_browser() -> list[dict]:
    """
    Launch headless Chromium, load session cookies, navigate to the
    LinkedIn feed, intercept voyager API JSON responses, and return
    the raw post elements.
    """
    captured: list[dict] = []
    raw_samples: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,   # non-headless via Xvfb — harder to detect
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1280,800",
            ],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )

        pw_cookies = _build_playwright_cookies()
        logger.info("Loading %d cookies into browser …", len(pw_cookies))
        await ctx.add_cookies(pw_cookies)

        page = await ctx.new_page()
        await stealth_async(page)   # mask headless fingerprint

        # Log ALL JSON responses so we can see what LinkedIn actually calls
        all_urls_seen: list[str] = []

        async def on_response(resp: Response) -> None:
            try:
                url   = resp.url
                ct    = resp.headers.get("content-type", "")
                status = resp.status
                if status == 200 and "json" in ct:
                    short = url.split("?")[0]
                    all_urls_seen.append(short)
                    body = await resp.json()
                    if isinstance(body, dict):
                        elems = body.get("elements", [])
                        if elems:
                            captured.extend(elems)
                            if len(raw_samples) < 3:
                                raw_samples.extend(elems[:2])
                            logger.info("Captured %d elements from %s",
                                        len(elems), short[-80:])
            except Exception:
                pass

        page.on("response", on_response)

        logger.info("Navigating to linkedin.com/feed …")
        await page.goto("https://www.linkedin.com/feed/",
                        wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(8)   # give SPA time to fire API calls

        final_url = page.url
        logger.info("Final URL: %s", final_url)

        # Screenshot for debugging (uploaded as artifact)
        try:
            await page.screenshot(path="feed_screenshot.png", full_page=False)
            logger.info("Screenshot saved.")
        except Exception:
            pass

        if "login" in final_url or "checkpoint" in final_url or "authwall" in final_url:
            logger.error("Redirected to %s — cookies invalid/expired.", final_url)
            await browser.close()
            return []

        # Log what JSON URLs were seen
        logger.info("JSON URLs seen so far (%d): %s",
                    len(all_urls_seen), all_urls_seen[:20])

        # Also try DOM extraction as fallback
        try:
            dom_posts = await page.evaluate("""() => {
                const out = [];
                // Try multiple selectors LinkedIn has used over the years
                const containers = document.querySelectorAll(
                    '[data-urn*="activity"], .feed-shared-update-v2, [data-id*="urn:li"]'
                );
                containers.forEach(c => {
                    const textEl = c.querySelector(
                        '.update-components-text span, .feed-shared-update-v2__description, ' +
                        '.break-words span[dir], .attributed-text-segment-list__content'
                    );
                    const authorEl = c.querySelector(
                        '.update-components-actor__name span, .feed-shared-actor__name span'
                    );
                    const text   = textEl   ? textEl.innerText.trim()   : '';
                    const author = authorEl ? authorEl.innerText.trim() : 'Unknown';
                    const urn    = c.getAttribute('data-urn') || c.getAttribute('data-id') || '';
                    if (text.length > 40) out.push({text, author, urn});
                });
                return out;
            }""")
            logger.info("DOM extraction found %d post candidates", len(dom_posts))
            for dp in dom_posts:
                keywords = _extract_keywords(dp["text"])
                if keywords:
                    urn = dp["urn"]
                    import hashlib
                    pid = urn.split(":")[-1] if urn else hashlib.md5(dp["text"][:200].encode()).hexdigest()
                    captured.append({
                        "__dom__": True,
                        "entityUrn": urn,
                        "commentary": {"text": {"text": dp["text"]}},
                        "actor": {"name": {"text": dp["author"]}},
                        "createdAt": int(datetime.now(tz=timezone.utc).timestamp() * 1000),
                    })
        except Exception:
            logger.warning("DOM extraction failed:\n%s", traceback.format_exc())

        # Scroll to load more
        for i in range(5):
            await page.evaluate("window.scrollBy(0, 2500)")
            await asyncio.sleep(3)
            logger.info("Scroll %d/5 — captured %d so far", i + 1, len(captured))
            if len(captured) >= MAX_FEED_POSTS:
                break

        logger.info("All JSON URLs seen: %s", all_urls_seen)
        await browser.close()

    # Save raw samples for artifact inspection
    try:
        RAW_DUMP.write_text(json.dumps(raw_samples, indent=2, default=str))
        logger.info("Raw dump: %d sample elements written to %s",
                    len(raw_samples), RAW_DUMP)
    except Exception:
        pass

    return captured


# ── Public entry point ────────────────────────────────────────────────────────

def fetch_hiring_posts() -> list[HiringPost]:
    cutoff  = datetime.now(tz=timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    results: list[HiringPost] = []
    seen_ids: set[str] = set()

    logger.info("Starting headless browser scrape (lookback=%dh) …", LOOKBACK_HOURS)
    try:
        raw_elements = asyncio.run(_fetch_with_browser())
    except Exception:
        logger.error("Browser scrape failed:\n%s", traceback.format_exc())
        raw_elements = []

    logger.info("Total raw elements intercepted: %d", len(raw_elements))

    for raw in raw_elements:
        for candidate in [raw, raw.get("resharedUpdate") or {}]:
            if not candidate:
                continue
            p = _parse(candidate)
            if p and p.post_id not in seen_ids and p.posted_at >= cutoff:
                seen_ids.add(p.post_id)
                results.append(p)

    logger.info("Hiring posts found (last %dh): %d", LOOKBACK_HOURS, len(results))
    return results
