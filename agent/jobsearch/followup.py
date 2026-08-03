"""Stops 30.5 and 40.4 — the follow-up ladders.

Two ladders, same discipline: spaced, capped, each rung adds something new, and
every rung stops the moment a reply is logged. Everything here writes drafts.
Nothing is sent.

    python3 -m agent.jobsearch.followup --dry-run
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone

from . import llm, store
from .config import data_dir, load_preferences

APP_SYSTEM = """Write a short follow-up on a job application that has had no reply.
Four sentences maximum. Reference something specific about the role, add one piece
of information the original application did not carry, and make it easy to ignore
without awkwardness. No guilt, no "just bumping this", no re-sending the resume."""

OUTREACH_SYSTEM = """Write the next message to someone who has not replied.
Two to four sentences. It must contribute something new — a relevant piece of work,
a question about the team's direction, a useful link. Never "just following up".
If the previous message already asked a question, do not repeat it."""


def _age_days(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        when = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).days


def application_ladder(conn, max_followups: int = 2, first_after: int = 7, then_after: int = 7) -> list[dict]:
    """Submitted, no reply, quiet for a week — draft a nudge, cap at two, then close."""
    drafts = []
    rows = conn.execute(
        "SELECT a.*, j.title, j.company, j.url, j.description FROM applications a "
        "JOIN jobs j ON j.id = a.job_id WHERE a.status = 'submitted'"
    ).fetchall()
    for app in rows:
        if app["followup_count"] >= max_followups:
            store.upsert_application(conn, app["job_id"], status="closed")
            print(f"  closed (no reply after {max_followups} follow-ups): "
                  f"{app['title']} — {app['company']}")
            continue
        since = _age_days(app["last_followup_at"] or app["submitted_at"])
        if since is None:
            continue
        due = first_after if app["followup_count"] == 0 else then_after
        if since < due:
            continue
        body = llm.text_call(
            APP_SYSTEM,
            f"Role: {app['title']} at {app['company']}\n"
            f"Applied {since} days ago. This is follow-up #{app['followup_count'] + 1}.\n\n"
            f"Posting:\n{(app['description'] or '')[:3000]}",
            mock=f"[dry-run] Follow-up #{app['followup_count'] + 1} on {app['title']} at {app['company']}.",
            max_tokens=600,
        )
        store.upsert_application(
            conn, app["job_id"],
            followup_count=app["followup_count"] + 1, last_followup_at=store.now(),
        )
        drafts.append({
            "kind": "application", "who": app["company"], "what": app["title"],
            "n": app["followup_count"] + 1, "body": body, "link": app["url"],
        })
    return drafts


def outreach_ladder(conn, rungs: list[int], max_followups: int = 2) -> list[dict]:
    """Day 4 and day 11 by default, per contact, stopping on any reply."""
    drafts = []
    contacts = conn.execute(
        "SELECT * FROM contacts WHERE status NOT IN ('replied', 'closed')"
    ).fetchall()
    for contact in contacts:
        msgs = conn.execute(
            "SELECT * FROM messages WHERE contact_id = ? ORDER BY created_at", (contact["id"],)
        ).fetchall()
        sent = [m for m in msgs if m["status"] == "sent"]
        if not sent:
            continue  # nothing has actually gone out yet
        already = sum(1 for m in msgs if m["channel"].startswith("followup"))
        if already >= max_followups:
            conn.execute("UPDATE contacts SET status='closed' WHERE id=?", (contact["id"],))
            conn.commit()
            continue
        since = _age_days(sent[-1]["sent_at"] or sent[-1]["created_at"])
        due = rungs[min(already, len(rungs) - 1)]
        if since is None or since < due:
            continue
        job = store.get_job(conn, contact["job_id"])
        body = llm.text_call(
            OUTREACH_SYSTEM,
            f"Contact: {contact['name']} — {contact['title']} at {contact['company']}\n"
            f"Role discussed: {job['title'] if job else '—'}\n"
            f"Hooks: {contact['hooks']}\n"
            f"Previous message ({since} days ago):\n{sent[-1]['body']}",
            mock=f"[dry-run] Follow-up #{already + 1} to {contact['name']}.",
            max_tokens=600,
        )
        store.add_message(conn, contact["id"], contact["job_id"], f"followup{already + 1}", body)
        drafts.append({
            "kind": "outreach", "who": contact["name"], "what": contact["title"],
            "n": already + 1, "body": body, "link": contact["profile_url"],
        })
    return drafts


def run(**_) -> dict:
    prefs = load_preferences().get("outreach", {})
    with store.connect() as conn:
        drafts = application_ladder(conn, max_followups=int(prefs.get("max_followups", 2)))
        drafts += outreach_ladder(
            conn,
            rungs=list(prefs.get("followup_days", [4, 11])),
            max_followups=int(prefs.get("max_followups", 2)),
        )

    today = date.today().isoformat()
    out_dir = data_dir() / "followups"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{today}.md"
    lines = [f"# Follow-ups to send — {today}", ""]
    if not drafts:
        lines.append("Nothing is due today.")
    for d in drafts:
        lines += [
            f"## {d['who']} — {d['what']}  ·  follow-up #{d['n']}  ({d['kind']})",
            "",
            d["body"].strip(),
            "",
            f"{d['link'] or ''}".strip(),
            "",
        ]
    path.write_text("\n".join(lines))
    print(f"  {len(drafts)} follow-up draft(s) → {path}")
    return {"drafts": len(drafts), "path": str(path)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Draft today's follow-ups")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    llm.set_offline(args.dry_run)
    run()
