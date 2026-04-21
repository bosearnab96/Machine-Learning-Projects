"""Title-based bucketing.

bucket('growth')   → bare connect + DM-on-accept
bucket('d2c_head') → InMail (requires Premium)
bucket(None)       → drop (not a relevant target)

The rule order matters: check C-level first so "Head of Growth" at a small
D2C brand (often the founder-level hire) goes into d2c_head, not growth.
"""

import re


C_LEVEL_PATTERNS = [
    r"\bfounder\b", r"\bco[- ]?founder\b",
    r"\bceo\b", r"\bcto\b", r"\bcmo\b", r"\bcpo\b", r"\bcbo\b", r"\bcoo\b",
    r"\bchief\s+\w+\s+officer\b",
    r"\bhead of (?:d2c|digital|ecommerce|e-commerce|consumer)\b",
    r"\bvp(?: of)?\s+(?:growth|product|marketing|brand)\b",
    r"\bsvp\b", r"\bpresident\b",
    r"\bmanaging director\b",
    r"\bbusiness head\b",
]

GROWTH_PATTERNS = [
    r"\bgrowth\b",
    r"\buser (?:growth|acquisition|activation|retention)\b",
    r"\bproduct (?:manager|lead|analyst|owner)\b|\bpm\b",
    r"\bproduct marketing\b",
    r"\bconversion\b", r"\bcro\b",
    r"\blifecycle\b", r"\bcrm\b",
    r"\bperformance marketing\b",
    r"\bretention\b", r"\bactivation\b",
    r"\bmarketing manager\b", r"\bmarketing lead\b",
]

# Roles we explicitly never want to contact.
EXCLUDE_PATTERNS = [
    r"\bintern\b",
    r"\b(?:hr|human resources|talent|recruit)\b",
    r"\bfinance\b", r"\baccounts?\b",
    r"\blegal\b",
    r"\bexecutive assistant\b",
]


def _match_any(patterns, text: str) -> bool:
    return any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)


def classify(title: str) -> str | None:
    """Return 'd2c_head', 'growth', or None."""
    if not title:
        return None
    t = title.strip()
    if _match_any(EXCLUDE_PATTERNS, t):
        return None
    if _match_any(C_LEVEL_PATTERNS, t):
        return "d2c_head"
    if _match_any(GROWTH_PATTERNS, t):
        return "growth"
    return None
