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


# ── Day-level grouping helpers ─────────────────────────────────────────────────

def _day_label(days_ago: int) -> str:
    if days_ago == 0:
        return "Today"
    if days_ago == 1:
        return "Yesterday"
    return f"{days_ago} days ago"


def _group_by_day(posts: list[HiringPost]) -> dict[int, list[HiringPost]]:
    """
    Group posts by how many calendar days ago they were posted (UTC).
    Returns a dict keyed 0–7+ (0 = today, 7 = 7+ days ago), sorted oldest first.
    """
    today = datetime.now(tz=timezone.utc).date()
    groups: dict[int, list[HiringPost]] = {}
    for p in posts:
        days_ago = (today - p.posted_at.astimezone(timezone.utc).date()).days
        bucket = min(max(days_ago, 0), 7)
        groups.setdefault(bucket, []).append(p)
    # Sort each bucket newest-within-day first
    for bucket in groups:
        groups[bucket].sort(key=lambda p: p.posted_at, reverse=True)
    return groups


# ── HTML email template ────────────────────────────────────────────────────────

def _render_post_card(p: HiringPost) -> str:
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
    remote_badge = (
        '<span style="background:#057642;color:#fff;padding:2px 6px;'
        'border-radius:4px;font-size:11px;margin-left:6px">Remote</span>'
        if p.is_remote else ""
    )
    posted_time = p.posted_at.strftime("%b %d, %Y %H:%M UTC")
    preview = p.short_preview(400).replace("\n", "<br>")

    return f"""
    <div style="border:1px solid #e0e0e0;border-radius:8px;padding:16px;
                margin-bottom:12px;font-family:Arial,sans-serif;background:#fff">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <strong>{author_link}{remote_badge}</strong>
        <small style="color:#666">{posted_time}</small>
      </div>
      <p style="margin:10px 0;color:#333;font-size:14px">{preview}</p>
      <div style="margin-top:8px">{keywords_badge}</div>
      <div style="margin-top:8px">{post_link}</div>
    </div>
    """


def _render_html(posts: list[HiringPost], digest_title: str, run_date: str) -> str:
    groups = _group_by_day(posts)

    sections_html = ""
    # Render oldest-first: 7, 6, 5, 4, 3, 2, 1, 0
    for days_ago in range(7, -1, -1):
        day_posts = groups.get(days_ago, [])
        if not day_posts:
            continue
        label = _day_label(days_ago)
        cards = "".join(_render_post_card(p) for p in day_posts)
        sections_html += f"""
        <div style="margin-bottom:24px">
          <h2 style="font-size:16px;color:#333;border-bottom:2px solid #0a66c2;
                     padding-bottom:6px;margin-bottom:12px">{label}
            <span style="font-size:13px;color:#666;font-weight:normal">
              &nbsp;— {len(day_posts)} posting{"s" if len(day_posts) != 1 else ""}
            </span>
          </h2>
          {cards}
        </div>
        """

    if not posts:
        sections_html = '<p style="color:#666">No new hiring posts found this week.</p>'

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="background:#f3f2ef;padding:24px;font-family:Arial,sans-serif">
      <div style="max-width:680px;margin:0 auto">
        <div style="background:#0a66c2;border-radius:8px 8px 0 0;
                    padding:20px 24px;color:#fff">
          <h1 style="margin:0;font-size:22px">{digest_title}</h1>
          <p style="margin:4px 0 0;opacity:.85">{run_date} &nbsp;·&nbsp;
             {len(posts)} new post{"s" if len(posts) != 1 else ""} found this week</p>
        </div>
        <div style="background:#f8f8f8;border-radius:0 0 8px 8px;
                    padding:24px;border:1px solid #e0e0e0;border-top:none">
          {sections_html}
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


def _render_plain(posts: list[HiringPost], digest_title: str, run_date: str) -> str:
    lines = [
        f"{digest_title} — {run_date}",
        f"{len(posts)} new post(s) found this week",
        "=" * 60,
    ]

    groups = _group_by_day(posts)
    for days_ago in range(7, -1, -1):
        day_posts = groups.get(days_ago, [])
        if not day_posts:
            continue
        lines.append(f"\n── {_day_label(days_ago)} ({'remote' if all(p.is_remote for p in day_posts) else f'{len(day_posts)} posting(s)'}) ──")
        for p in day_posts:
            remote_tag = " [REMOTE]" if p.is_remote else ""
            lines += [
                f"\nAuthor : {p.author}{remote_tag}",
                f"URL    : {p.post_url or 'n/a'}",
                f"Posted : {p.posted_at.strftime('%b %d, %Y %H:%M UTC')}",
                f"Tags   : {', '.join(p.matched_keywords)}",
                f"\n{p.short_preview(400)}",
                "-" * 60,
            ]

    if not posts:
        lines.append("\nNo new hiring posts found this week.")
    return "\n".join(lines)


# ── Public send function ───────────────────────────────────────────────────────

def send_digest(posts: list[HiringPost], digest_title: str,
                recipients: list[str] | None = None) -> None:
    """
    Send the digest email for a specific category (tech or generalist).
    Posts are grouped by day within the email (oldest section first).
    If *posts* is empty, still sends a "no results this week" email.

    *recipients* is a list of To: addresses. Defaults to [ALERT_RECIPIENT].
    """
    if not recipients:
        recipients = [ALERT_RECIPIENT]

    run_date = datetime.now(tz=timezone.utc).strftime("%A, %b %d %Y")
    subject  = f"[{digest_title}] {len(posts)} new post(s) this week — {run_date}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = ", ".join(recipients)

    msg.attach(MIMEText(_render_plain(posts, digest_title, run_date), "plain"))
    msg.attach(MIMEText(_render_html(posts, digest_title, run_date),  "html"))

    logger.info(
        "Sending '%s' digest (%d posts) to %s via %s:%s …",
        digest_title, len(posts), recipients, _SMTP_HOST, _SMTP_PORT,
    )

    with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(GMAIL_SENDER, GMAIL_PASSWORD)
        server.sendmail(GMAIL_SENDER, recipients, msg.as_string())

    logger.info("'%s' digest email sent successfully to %d recipient(s).", digest_title, len(recipients))
