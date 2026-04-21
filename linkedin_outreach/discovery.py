"""Paced people-search → candidates.csv.

Run this ONE company at a time (e.g. `python -m linkedin_outreach.cli discover --company Blissclub`).
The bot opens LinkedIn search with the company filter applied, runs 3-5
relevance searches ("growth", "product", "conversion", "founder", "CRO"),
reads visible result cards, classifies by title, and appends to
`candidates_<company>.csv`.

It does NOT queue anything for outreach. You review the CSV, delete false
positives, rename the approved rows into `profiles_growth.csv` or
`profiles_d2c_heads.csv`, then run `ingest`.

Why so conservative? People-search is LinkedIn's most-watched surface.
Hammering it is the fastest way to a checkpoint.
"""

import asyncio
import csv
import logging
import random
import urllib.parse
from pathlib import Path

from playwright.async_api import Page

import config
import human
from browser import launch_context, bail_if_checkpoint
from classifier import classify


logger = logging.getLogger(__name__)


SEARCH_QUERIES = ["growth", "product", "CRO", "conversion", "founder"]


def _search_url(query: str, company: str) -> str:
    q = urllib.parse.quote(query)
    # LinkedIn's people search expects a currentCompany filter as a JSON array
    # of company IDs, but querying by the company name in the keyword is
    # nearly as effective and doesn't require a company-id lookup.
    combined = urllib.parse.quote(f'"{company}" {query}')
    return (
        f"https://www.linkedin.com/search/results/people/"
        f"?keywords={combined}&origin=GLOBAL_SEARCH_HEADER"
    )


async def _scrape_results_page(page: Page, company: str) -> list[dict]:
    """Read visible result cards from the current search page."""
    cards = page.locator(
        "ul[role='list'] li:has(a[href*='/in/']), "
        "li.reusable-search__result-container"
    )
    count = await cards.count()
    results = []
    for i in range(count):
        card = cards.nth(i)
        try:
            link = card.locator("a[href*='/in/']").first
            href = await link.get_attribute("href")
            if not href:
                continue
            url = href.split("?")[0]
            # Name is in the visible text of the anchor or a span inside it.
            name_text = (await link.inner_text()).strip().split("\n")[0]
            # Title sits in a sibling div — we grab the full card text and split.
            card_text = (await card.inner_text()).strip()
            lines = [ln.strip() for ln in card_text.split("\n") if ln.strip()]
            title = lines[1] if len(lines) > 1 else ""
            first_name = name_text.split()[0] if name_text else ""
            bucket = classify(title)
            if not bucket:
                continue
            results.append({
                "url": url,
                "first_name": first_name,
                "company": company,
                "title": title,
                "bucket": bucket,
            })
        except Exception:
            continue
    return results


async def discover_for_company(company: str) -> Path:
    """Run discovery for ONE company. Appends to a per-company candidates CSV."""
    out_path = config.ROOT / f"candidates_{company.replace(' ', '_')}.csv"
    found: dict[str, dict] = {}

    async with launch_context() as ctx:
        page = await ctx.new_page()
        # Warm up with a feed scroll — we don't want the first action in the
        # session to be a search query.
        await human.warmup_feed(page)

        queries = SEARCH_QUERIES.copy()
        random.shuffle(queries)
        # Only do 3-5 searches per session.
        queries = queries[: random.randint(3, 5)]

        for idx, query in enumerate(queries):
            if not human.in_working_hours():
                logger.info("Outside working hours — stopping discovery.")
                break

            url = _search_url(query, company)
            logger.info("Search: %r at %r", query, company)
            await page.goto(url, wait_until="domcontentloaded")
            await human.jitter_sleep(2.0, 4.5)

            if await bail_if_checkpoint(page, f"discover_{company}_{query}"):
                logger.warning("Checkpoint hit during discovery — aborting.")
                break

            # Scroll result list the way a human skims: top → bottom → pause.
            await human.human_scroll(page, random.uniform(10, 22))

            rows = await _scrape_results_page(page, company)
            for r in rows:
                found[r["url"]] = r

            # Optionally page 2, but only ~40% of the time.
            if random.random() < 0.4:
                try:
                    next_btn = page.locator("button[aria-label='Next']").first
                    if await next_btn.count() and await next_btn.is_enabled():
                        await human.click_humanly(page, "button[aria-label='Next']")
                        await human.jitter_sleep(2.5, 5.0)
                        await human.human_scroll(page, random.uniform(8, 16))
                        rows2 = await _scrape_results_page(page, company)
                        for r in rows2:
                            found[r["url"]] = r
                except Exception:
                    pass

            # Long pause between queries — no rapid-fire searching.
            await human.jitter_sleep(45, 120)

        await page.close()

    # Append (don't overwrite) so re-runs accumulate.
    existing_urls = set()
    if out_path.exists():
        with out_path.open() as f:
            for row in csv.DictReader(f):
                existing_urls.add(row["url"])

    new_rows = [r for r in found.values() if r["url"] not in existing_urls]
    write_header = not out_path.exists()
    with out_path.open("a", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["url", "first_name", "company", "title", "bucket"])
        if write_header:
            writer.writeheader()
        writer.writerows(new_rows)

    logger.info("Discovery done: %d new, %d already seen, total in file: %d",
                len(new_rows), len(found) - len(new_rows), len(found))
    return out_path
