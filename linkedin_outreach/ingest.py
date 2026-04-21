"""Load reviewed CSVs into the DB as queued profiles.

Two input files, two buckets:
    profiles_growth.csv    → bucket='growth'    → bare connect + DM flow
    profiles_d2c_heads.csv → bucket='d2c_head'  → InMail flow

Each CSV must have at minimum: url, first_name, company
(optional: title)
"""

import csv
import logging
from pathlib import Path

import config
import storage


logger = logging.getLogger(__name__)


def _load(path: Path, bucket: str) -> tuple[int, int]:
    if not path.exists():
        logger.info("No file at %s — skipping.", path)
        return 0, 0
    new, dup = 0, 0
    with path.open() as f:
        for row in csv.DictReader(f):
            url = (row.get("url") or "").strip()
            if not url:
                continue
            added = storage.upsert_profile(
                url=url,
                first_name=(row.get("first_name") or "").strip(),
                company=(row.get("company") or "").strip(),
                bucket=bucket,
                title=(row.get("title") or "").strip(),
            )
            if added:
                new += 1
            else:
                dup += 1
    return new, dup


def ingest_all() -> None:
    g_new, g_dup = _load(config.PROFILES_GROWTH_CSV, "growth")
    d_new, d_dup = _load(config.PROFILES_DHEADS_CSV, "d2c_head")
    logger.info(
        "Ingest complete. growth: +%d new (%d duplicates), d2c_head: +%d new (%d duplicates)",
        g_new, g_dup, d_new, d_dup,
    )
