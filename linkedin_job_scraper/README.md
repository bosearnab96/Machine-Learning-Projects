# LinkedIn Hiring Post Scraper + Daily Email Digest

Automatically monitors LinkedIn for hiring posts and sends a formatted
digest to your Gmail inbox every day at your chosen time.

---

## How it works

```
LinkedIn (unofficial API)
    ↓  search posts + home feed
Keyword filter (hiring / open role / #hiring / …)
    ↓  new posts only
SQLite deduplication store
    ↓  unseen posts
Gmail SMTP digest email  →  your inbox (daily EOD)
```

---

## Quick-start (step by step)

### 1. Install Python dependencies

```bash
cd linkedin_job_scraper
pip install -r requirements.txt
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Open `.env` and fill in:

| Variable | What to put |
|---|---|
| `LINKEDIN_EMAIL` | Your LinkedIn login email |
| `LINKEDIN_PASSWORD` | Your LinkedIn password |
| `GMAIL_SENDER` | Gmail address that sends the digest |
| `GMAIL_PASSWORD` | **App Password** (see below) — NOT your regular password |
| `ALERT_RECIPIENT` | Where you want to receive emails (can be same as sender) |
| `DIGEST_HOUR` | UTC hour for daily email (e.g. `18` = 6 PM UTC) |
| `DIGEST_MINUTE` | Minute offset (default `0`) |

### 3. Create a Gmail App Password

1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Make sure **2-Step Verification** is enabled on your Google account
3. Click **Add new app password** → name it "LinkedIn Scraper"
4. Copy the 16-character password into `GMAIL_PASSWORD` in `.env`

### 4. Test everything immediately

```bash
python scheduler.py --now
```

This runs one full cycle (scrape → filter → email) and exits.
Check your inbox in ~1 minute.

### 5. Start the persistent daily scheduler

```bash
python scheduler.py
```

The process stays alive and fires at the time you set in `.env`.
To keep it running after you close your terminal, use one of:

```bash
# Option A — nohup (simplest)
nohup python scheduler.py &

# Option B — screen
screen -S linkedin-scraper
python scheduler.py
# Ctrl+A then D to detach

# Option C — systemd service (recommended for servers)
# See systemd section below.
```

---

## File layout

```
linkedin_job_scraper/
├── config.py        — all settings (reads from .env)
├── scraper.py       — LinkedIn fetching + keyword detection
├── storage.py       — SQLite deduplication layer
├── emailer.py       — Gmail digest builder + sender
├── scheduler.py     — entry point / APScheduler wiring
├── requirements.txt
├── .env.example     — copy → .env and fill in
└── .gitignore       — keeps .env and *.db out of git
```

---

## Customising hiring keywords

Open `config.py` and edit `HIRING_KEYWORDS`:

```python
HIRING_KEYWORDS = [
    "we are hiring",
    "#hiring",
    "open role",
    # add your own ...
]
```

---

## Running as a systemd service (Linux servers)

Create `/etc/systemd/system/linkedin-scraper.service`:

```ini
[Unit]
Description=LinkedIn Hiring Scraper
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/linkedin_job_scraper
ExecStart=/usr/bin/python3 scheduler.py
Restart=on-failure
EnvironmentFile=/path/to/linkedin_job_scraper/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable linkedin-scraper
sudo systemctl start linkedin-scraper
sudo systemctl status linkedin-scraper
```

---

## Important notes / limitations

- This tool uses the **unofficial** `linkedin-api` library which interacts
  with LinkedIn's internal mobile API using your credentials.  This is against
  LinkedIn's Terms of Service.  Use it for **personal automation only** and
  at your own risk.
- LinkedIn may throttle or temporarily block accounts that make too many
  requests.  `MAX_POSTS_PER_RUN = 50` is conservative; don't raise it too high.
- The `seen_posts.db` SQLite file grows over time; it's safe to delete it
  if you want to re-process all posts (you'll get a large catch-up email).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `CHALLENGE` error on login | LinkedIn is asking for a CAPTCHA/OTP; log in manually in a browser first, then retry |
| Email not received | Check spam; verify App Password is correct; make sure 2-Step Verification is on |
| No posts found | Try `python scheduler.py --now` and check `scraper.log`; LinkedIn may have changed API shape |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` inside the project folder |
