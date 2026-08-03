"""Email — the surface most people will actually use.

Nobody opens a dashboard every morning. They do read their inbox, so the daily
digest is the product for most users and the dashboard is where they go when a
job is worth acting on.

Sending is stdlib SMTP, which every provider speaks (SES, Mailgun, Postmark,
Resend, or a Gmail app password). With no SMTP configured, mail is written to
data/saas/outbox/ as .eml files so the whole path is testable offline.

    SMTP_HOST=smtp.eu.mailgun.org SMTP_PORT=587 SMTP_USER=… SMTP_PASSWORD=…
    MAIL_FROM="Job Radar <hello@yourdomain>" APP_URL=https://yourdomain
"""

from __future__ import annotations

import html
import os
import smtplib
import ssl
from datetime import date
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

from . import db, security

APP_URL = os.environ.get("APP_URL", "http://127.0.0.1:8000").rstrip("/")
MAIL_FROM = os.environ.get("MAIL_FROM", "Job Radar <no-reply@localhost>")
OUTBOX = Path(os.environ.get("SAAS_OUTBOX", db.ROOT / "data" / "saas" / "outbox"))

INK = "#11141a"
INK_2 = "#48515e"
INK_3 = "#78828f"
RULE = "#cdd5de"
PAPER = "#eef1f5"
SURFACE = "#ffffff"
RADAR = "#0c7c77"
FORGE = "#b0521c"


def configured() -> bool:
    return bool(os.environ.get("SMTP_HOST"))


def e(value) -> str:
    return html.escape(str(value if value is not None else ""))


# ---------------------------------------------------------------- sending

def send(to: str, subject: str, html_body: str, text_body: str,
         list_unsubscribe: str | None = None) -> str:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = MAIL_FROM
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    if list_unsubscribe:
        # One-click unsubscribe: required by Gmail and Yahoo for bulk senders.
        msg["List-Unsubscribe"] = f"<{list_unsubscribe}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    if not configured():
        OUTBOX.mkdir(parents=True, exist_ok=True)
        path = OUTBOX / f"{date.today().isoformat()}-{to.replace('@', '_at_')}.eml"
        path.write_bytes(bytes(msg))
        return f"written to {path}"

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", 587))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
            if user:
                server.login(user, password or "")
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls(context=context)
            if user:
                server.login(user, password or "")
            server.send_message(msg)
    return f"sent to {to}"


# ---------------------------------------------------------------- the digest

def _score_chip(score: int) -> str:
    colour = RADAR if score >= 80 else FORGE
    return (f'<span style="display:inline-block;background:{colour};color:#fff;font-weight:700;'
            f'font-size:12px;padding:3px 8px;border-radius:4px">{score}</span>')


def digest_html(user_email: str, jobs: list, followups: int, unsubscribe_url: str) -> str:
    today = date.today().strftime("%A %-d %B")
    cards = ""
    for job in jobs:
        analysis = job.get("analysis") or {}
        gaps = ", ".join(analysis.get("missing_skills", [])[:3])
        cards += f"""
      <tr><td style="padding:0 0 14px">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="background:{SURFACE};border:1px solid {RULE};border-radius:8px">
          <tr><td style="padding:15px 17px">
            <div style="margin-bottom:7px">{_score_chip(int(job.get('score') or 0))}</div>
            <div style="font:700 16px/1.25 Helvetica,Arial,sans-serif;color:{INK};padding-bottom:3px">
              <a href="{e(job['app_url'])}" style="color:{INK};text-decoration:none">{e(job['title'])}</a>
            </div>
            <div style="font:14px/1.4 Helvetica,Arial,sans-serif;color:{INK_2};padding-bottom:9px">
              {e(job['company'])} &middot; {e(job.get('location') or '—')}{
                ' &middot; ' + e(job['salary_raw']) if job.get('salary_raw') else ''}
            </div>
            <div style="font:14px/1.5 Helvetica,Arial,sans-serif;color:{INK_2};padding-bottom:10px">
              {e(analysis.get('verdict', ''))}
            </div>
            {f'<div style="font:13px/1.4 Helvetica,Arial,sans-serif;color:{INK_3};padding-bottom:12px">'
             f'Gaps: {e(gaps)}</div>' if gaps else ''}
            <a href="{e(job['app_url'])}"
               style="display:inline-block;background:{RADAR};color:#fff;text-decoration:none;
                      font:700 14px Helvetica,Arial,sans-serif;padding:9px 15px;border-radius:6px">
              Review it</a>
          </td></tr>
        </table>
      </td></tr>"""

    if not cards:
        cards = f"""<tr><td style="padding:0 0 14px;font:15px/1.5 Helvetica,Arial,sans-serif;color:{INK_2}">
          Nothing cleared your score threshold today. That is usually the filters doing their job —
          if it happens all week, widen your titles or lower the threshold in
          <a href="{APP_URL}/settings" style="color:{RADAR}">settings</a>.
        </td></tr>"""

    followup_note = ""
    if followups:
        followup_note = f"""<tr><td style="padding:6px 0 18px;font:14px/1.5 Helvetica,Arial,sans-serif;color:{INK_2}">
          <strong>{followups}</strong> follow-up{'s' if followups != 1 else ''} due — drafts are
          waiting in <a href="{APP_URL}/dashboard" style="color:{RADAR}">your dashboard</a>.
        </td></tr>"""

    return f"""<!doctype html><html><body style="margin:0;padding:0;background:{PAPER}">
<div style="display:none;max-height:0;overflow:hidden">
  {len(jobs)} role{'s' if len(jobs) != 1 else ''} worth your time this morning.
</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAPER}">
<tr><td align="center" style="padding:26px 14px 40px">
  <table role="presentation" width="600" cellpadding="0" cellspacing="0"
         style="width:100%;max-width:600px">
    <tr><td style="padding-bottom:6px;font:700 17px Helvetica,Arial,sans-serif;color:{INK}">
      job<span style="color:{RADAR}">&middot;</span>radar</td></tr>
    <tr><td style="padding-bottom:4px;font:700 24px/1.15 Helvetica,Arial,sans-serif;color:{INK}">
      {len(jobs)} for you this morning</td></tr>
    <tr><td style="padding-bottom:20px;font:14px Helvetica,Arial,sans-serif;color:{INK_3}">
      {today}</td></tr>
    {followup_note}
    {cards}
    <tr><td style="padding:14px 0 0;border-top:1px solid {RULE};
                   font:12px/1.6 Helvetica,Arial,sans-serif;color:{INK_3}">
      Scored against your resume. Nothing has been applied for and nothing has been sent —
      you approve every application and every message.<br>
      You get this because you turned on the daily search for {e(user_email)}.
      <a href="{e(unsubscribe_url)}" style="color:{INK_3}">Stop these emails</a> &middot;
      <a href="{APP_URL}/settings" style="color:{INK_3}">Settings</a>
    </td></tr>
  </table>
</td></tr></table></body></html>"""


def digest_text(user_email: str, jobs: list, followups: int, unsubscribe_url: str) -> str:
    lines = [f"{len(jobs)} for you this morning — {date.today().strftime('%A %-d %B')}", ""]
    if followups:
        lines += [f"{followups} follow-up(s) due: {APP_URL}/dashboard", ""]
    for job in jobs:
        analysis = job.get("analysis") or {}
        lines += [
            f"[{int(job.get('score') or 0)}] {job['title']} — {job['company']}"
            f" ({job.get('location') or '—'})",
            f"    {analysis.get('verdict', '')}".rstrip(),
            f"    {job['app_url']}",
            "",
        ]
    if not jobs:
        lines += ["Nothing cleared your score threshold today.", ""]
    lines += [
        "Scored against your resume. Nothing was applied for and nothing was sent.",
        f"You get this because you turned on the daily search for {user_email}.",
        f"Stop these emails: {unsubscribe_url}",
    ]
    return "\n".join(lines)


def collect_digest(user, limit: int = 8) -> tuple[list, int]:
    """What is worth telling this user this morning, read from their own tracker."""
    import json

    from agent.jobsearch import store
    from agent.jobsearch.workspace import workspace

    with workspace(db.workspace_for(user["id"])):
        with store.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = 'scored' ORDER BY score DESC LIMIT ?",
                (limit,),
            ).fetchall()
            followups = conn.execute(
                "SELECT COUNT(*) n FROM applications WHERE status = 'submitted'"
            ).fetchone()["n"]

    jobs = [{
        "title": r["title"], "company": r["company"], "location": r["location"],
        "salary_raw": r["salary_raw"], "score": r["score"],
        "analysis": json.loads(r["analysis"] or "{}"),
        "app_url": f"{APP_URL}/jobs/{r['id']}",
    } for r in rows]
    return jobs, followups


def send_digest(user, jobs: list, followups: int = 0) -> str:
    token = security.email_token(user["id"])
    unsubscribe = f"{APP_URL}/email/unsubscribe?token={token}"
    subject = (f"{len(jobs)} role{'s' if len(jobs) != 1 else ''} worth your time today"
               if jobs else "No matches today")
    return send(
        user["email"], subject,
        digest_html(user["email"], jobs, followups, unsubscribe),
        digest_text(user["email"], jobs, followups, unsubscribe),
        list_unsubscribe=unsubscribe,
    )
