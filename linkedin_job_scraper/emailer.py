"""
emailer.py — Sends the daily hiring-post digest via Gmail SMTP.

Authentication uses a Gmail App Password (not your account password).
How to create one:
  Google Account → Security → 2-Step Verification → App Passwords
  → choose "Mail" + "Other (custom name)" → Copy the 16-char password.
"""

import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import ALERT_RECIPIENT, GMAIL_PASSWORD, GMAIL_SENDER
from scraper import HiringPost

logger = logging.getLogger(__name__)

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587


# ── HTML email template ────────────────────────────────────────────────────────

def _render_html(posts: list[HiringPost], run_date: str) -> str:
    rows_html = ""
    for p in posts:
        keywords_badge = " ".join(
            f'<span style="background:#0a66c2;color:#fff;padding:2px 6px;'
            f'border-radius:4px;font-size:11px;margin-right:4px">{kw}</span>'
            for kw in p.matched_keywords[:5]
        )
        author_link = (
            f'<a href="{p.author_url}" style="color:#0a66c2">{p.author}</a>'
            if p.author_url else p.author
        )
        post_link = (
            f'<a href="{p.post_url}" style="color:#0a66c2">View post →</a>'
            if p.post_url else ""
        )
        posted_time = p.posted_at.strftime("%b %d, %Y %H:%M UTC")
        preview = p.short_preview(400).replace("\n", "<br>")

        rows_html += f"""
        <div style="border:1px solid #e0e0e0;border-radius:8px;padding:16px;
                    margin-bottom:16px;font-family:Arial,sans-serif">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <strong>{author_link}</strong>
            <small style="color:#666">{posted_time}</small>
          </div>
          <p style="margin:10px 0;color:#333;font-size:14px">{preview}</p>
          <div style="margin-top:8px">{keywords_badge}</div>
          <div style="margin-top:8px">{post_link}</div>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="background:#f3f2ef;padding:24px;font-family:Arial,sans-serif">
      <div style="max-width:680px;margin:0 auto">
        <div style="background:#0a66c2;border-radius:8px 8px 0 0;
                    padding:20px 24px;color:#fff">
          <h1 style="margin:0;font-size:22px">LinkedIn Hiring Digest</h1>
          <p style="margin:4px 0 0;opacity:.85">{run_date} &nbsp;·&nbsp;
             {len(posts)} new post{"s" if len(posts) != 1 else ""} found</p>
        </div>
        <div style="background:#fff;border-radius:0 0 8px 8px;
                    padding:24px;border:1px solid #e0e0e0;border-top:none">
          {rows_html if posts else
           '<p style="color:#666">No new hiring posts found today.</p>'}
          <hr style="border:none;border-top:1px solid #e0e0e0;margin:24px 0">
          <p style="font-size:12px;color:#999;text-align:center">
            Sent by your LinkedIn Hiring Scraper &nbsp;·&nbsp;
            <a href="https://github.com/bosearnab96/machine-learning-projects"
               style="color:#0a66c2">Source</a>
          </p>
        </div>
      </div>
    </body>
    </html>
    """


def _render_plain(posts: list[HiringPost], run_date: str) -> str:
    lines = [
        f"LinkedIn Hiring Digest — {run_date}",
        f"{len(posts)} new post(s) found",
        "=" * 60,
    ]
    for p in posts:
        lines += [
            f"\nAuthor : {p.author}",
            f"URL    : {p.post_url or 'n/a'}",
            f"Posted : {p.posted_at.strftime('%b %d, %Y %H:%M UTC')}",
            f"Tags   : {', '.join(p.matched_keywords)}",
            f"\n{p.short_preview(400)}",
            "-" * 60,
        ]
    if not posts:
        lines.append("\nNo new hiring posts found today.")
    return "\n".join(lines)


# ── Public send function ───────────────────────────────────────────────────────

def send_digest(posts: list[HiringPost]) -> None:
    """
    Send the daily digest email.
    If *posts* is empty, still sends a "no results today" email so you know
    the tool ran.  Set SEND_EMPTY_DIGEST=false in .env to suppress that.
    """
    run_date = datetime.now(tz=timezone.utc).strftime("%A, %b %d %Y")
    subject  = f"[LinkedIn Hiring] {len(posts)} new post(s) — {run_date}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = ALERT_RECIPIENT

    msg.attach(MIMEText(_render_plain(posts, run_date), "plain"))
    msg.attach(MIMEText(_render_html(posts, run_date),  "html"))

    logger.info(
        "Sending digest to %s via %s:%s …",
        ALERT_RECIPIENT, _SMTP_HOST, _SMTP_PORT,
    )

    with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(GMAIL_SENDER, GMAIL_PASSWORD)
        server.sendmail(GMAIL_SENDER, ALERT_RECIPIENT, msg.as_string())

    logger.info("Digest email sent successfully.")
