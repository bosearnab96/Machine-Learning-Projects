# Project Instructions

## Debugging & Error Methodology

Whenever an error or unexpected behavior occurs, follow this RCA process before touching any code:

### Step 1 — MECE Cause Tree
List every possible root cause in a mutually-exclusive, collectively-exhaustive tree. Group causes into distinct buckets (e.g. code issue / environment issue / external service issue / data issue). No cause should overlap another; together they should cover the full possibility space.

### Step 2 — Confidence Factors with Rationale
For each leaf cause, assign a confidence percentage (must sum to ~100% within each branch). Rationale must be grounded in evidence — search Reddit (r/learnpython, r/devops, r/github, etc.) and GitHub Issues for similar reports before assigning confidence. State the source inline.

Example format:
```
A. Wrong branch deployed — 80%
   Rationale: GitHub Actions always runs from the default branch (master).
   git log confirms master ≠ feature branch. Consistent with GitHub docs
   and multiple GH Issues (e.g. actions/checkout#20).

B. Dedup cache hiding results — 60%
   Rationale: SQLite seen_posts.db persists across runs via Actions cache.
   Common pattern documented in python-jobspy GitHub issues and Reddit
   threads about scraper dedup logic.
```

### Step 3 — Validate Highest Confidence First
Debug in descending confidence order. For each candidate:
1. State the validation method (log line to check, file to read, query to run)
2. Execute the validation
3. Confirm or rule out, then move to next

Do not write any fix code until the root cause is confirmed.
