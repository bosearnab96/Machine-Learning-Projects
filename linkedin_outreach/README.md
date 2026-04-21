# LinkedIn Outreach Bot

Human-paced outreach to growth / product / CRO folks and D2C founders at a
fixed list of brands. Sends **bare connection requests** followed by a **full
DM after acceptance** for non-CXOs, and **InMails** (Premium) for D2C heads.

> ⚠️  **This is against LinkedIn's Terms of Service.** Use at your own risk
> on your own account only. The conservative pacing in `config.py` exists
> precisely to stay under the radar; don't raise it.

---

## What it does

```
                           ┌────────────────────────────────┐
                           │  discover  (1 company / run)   │
                           └──────────────┬─────────────────┘
                                          ▼
                            candidates_<Company>.csv
                                          │
                       (you review, delete false positives)
                                          │
                     ┌────────────────────┴─────────────────┐
                     ▼                                      ▼
         profiles_growth.csv                   profiles_d2c_heads.csv
                     │                                      │
                     └─────────────┬────────────────────────┘
                                   ▼
                                ingest
                                   │
                                   ▼
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
              connect (bare)                   inmail
                    │                             │
                    ▼                             ▼
              invite_sent                    inmail_sent
                    │
              (recipient accepts)
                    │
                   watch
                    │
                    ▼
                 accepted
                    │
                    ▼
                   dm  ────────►  dm_sent (full pitch landed)
```

## Setup

```bash
cd linkedin_outreach
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# edit .env if you want different pacing / working hours
```

### One-time login

```bash
python cli.py login
```

A Chromium window opens. Log in to LinkedIn manually (including any 2FA).
Close the window when the feed loads. Your session is now saved inside
`chrome_profile/` and reused by every subsequent command.

---

## Daily workflow

### 1. Discover candidates (one company at a time)

```bash
python cli.py discover --company "Blissclub"
# wait at least a few hours before the next one
python cli.py discover --company "The Souled Store"
```

Outputs: `candidates_Blissclub.csv` — columns `url,first_name,company,title,bucket`.

Each run opens a few searches (`growth`, `product`, `CRO`, `conversion`,
`founder`), reads visible result cards, auto-classifies by title, and
appends only new URLs.

**Do one company per session, max a few companies per day.** People-search is
the most-watched surface on LinkedIn — don't race through the list.

### 2. Review & curate

Open each `candidates_<Company>.csv`. Delete rows that are clearly wrong
(intern roles slipped through, wrong company matched, someone you already
know personally, etc.).

Split the approved rows by `bucket` column into two master files:

- `profiles_growth.csv`     ← all `growth`-bucket rows
- `profiles_d2c_heads.csv`  ← all `d2c_head`-bucket rows

Schema (both files): `url,first_name,company[,title]`

### 3. Ingest

```bash
python cli.py ingest
```

Loads both CSVs into `outreach.db` as `status=queued`. Already-known URLs
are skipped.

### 4. Send connection requests (growth bucket)

```bash
python cli.py connect               # runs until caps or queue empty
python cli.py connect --max 3       # or cap per session
```

Behavior per profile:
- Navigate to profile, scroll/dwell 12–35 s (mouse moves along bezier curves)
- Click **Connect** → **Send without a note**
- Logs to `rate_log` so weekly/daily caps are enforced across runs

Caps: 4 invites / hour max, 12 / day, 40 / week, 10am–7pm IST, Mon–Fri.

### 5. Send InMails (d2c_head bucket)

```bash
python cli.py inmail --max 2       # 2-3 / day is plenty
```

Requires an active Premium / Sales Nav / Recruiter subscription.

### 6. Watch for accepts

Run once or twice a day:

```bash
python cli.py watch
```

For every `invite_sent` profile, re-visits the page, checks if the primary
button changed from `Pending` → `Message` (= they accepted). Promotes
matching rows to `status=accepted`.

### 7. Follow up with the full pitch

```bash
python cli.py dm --max 4
```

Types the full ~1,100-char message into the DM compose panel (with a
realistic cadence, occasional typo + backspace), then sends.

### 8. Status check

```bash
python cli.py status
```

Prints invite counts by day/week plus a bucket × status table so you can
see what's queued, sent, accepted, and DM'd.

---

## How "human-like" is encoded

| Behavior | Where |
|---|---|
| Bezier mouse paths, hover-before-click | `human.move_mouse_humanly` |
| Variable-delta scroll bursts, occasional scroll-back-up | `human.human_scroll` |
| Dwell on profile, pause on Experience | `human.dwell_on_profile` |
| Warm-up: 1–2 feed scrolls before first action | `human.warmup_feed` |
| Per-keystroke typing delays + typo-and-backspace blips | `human.type_humanly` |
| Longer pauses at punctuation | same |
| Cooldown between actions drawn from a range | `human.post_action_cooldown` |
| "Coffee break" every 3 actions | same |
| Working-hours gate (Mon–Fri 10–19 IST) | `human.in_working_hours` |
| Persistent Chrome profile (no re-login per run) | `browser.launch_context` |
| Stealth patches (`navigator.webdriver` = false, etc.) | `browser.launch_context` |
| Daily + weekly hard caps before first click | `sender_connect._caps_ok` |
| Checkpoint / CAPTCHA page = hard stop + screenshot | `browser.bail_if_checkpoint` |

## Recommended schedule

| Time (IST) | Command | Budget |
|---|---|---|
| 10:15 | `cli.py watch`            | all `invite_sent` rows |
| 10:30 | `cli.py dm --max 3`       | 3 DMs |
| 13:00 | `cli.py connect --max 3`  | 3 invites |
| 16:00 | `cli.py connect --max 3`  | 3 invites |
| 18:00 | `cli.py inmail --max 2`   | 2 InMails |

Weekly total stays under 30 invites and ~10 InMails — well below LinkedIn's
thresholds.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `no_inmail_compose` in logs | Premium lapsed, or profile has InMail disabled — skip |
| `send_dialog_failed` for Connect | LinkedIn asked for "how do you know this person?" — we bail rather than guess an email |
| `checkpoint` status on a row | LinkedIn served a CAPTCHA — log in manually, clear it, rerun |
| No accepts detected but you see some on LinkedIn | Recipient may have accepted on mobile without triggering our marker; rerun `watch` after another day |
| Script idle during work hours | Check `config.py` `WORK_DAYS` / timezone — IST = `Asia/Kolkata` |
