"""Stage 5 — the human bridge.

The agent never touches LinkedIn. It works out *who* to look for, hands you
ready-to-run search URLs, and once you paste a profile back it drafts the
messages. You stay the one who clicks connect.
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
from pathlib import Path

from . import llm, store
from .config import DATA_DIR, application_dir, load_preferences

TITLE_SYSTEM = """Given a job posting, infer who owns the hiring decision.
Return JSON: {"manager_titles": ["2-4 likely titles of the hiring manager"],
"peer_titles": ["2-3 titles of people already on the team"],
"team": "the team or function name"}"""

HOOK_SYSTEM = """Read a public professional profile and extract outreach material.
Return JSON: {"name": "", "title": "", "team": "", "tenure": "",
"hooks": [{"hook": "specific thing to reference", "strength": "high|medium|low"}]}
A hook is a post, talk, project, shipped feature, or a genuine overlap with the
candidate's background. Generic facts ("works at X") are not hooks."""

MESSAGE_SYSTEM = """Write outreach from a candidate to a hiring manager.
Rules:
- Open with the specific hook. Never open with "I am writing to apply".
- One line of the single strongest relevant evidence, with its metric.
- Close with one specific question that is easy to answer.
- No resume dump, no flattery, no "I'd love to pick your brain".
Return JSON: {"connection_note": "under 300 characters",
"inmail": "about 120 words", "email_subject": "", "email": "about 150 words"}"""


def search_urls(company: str, titles: list[str]) -> list[str]:
    urls = []
    for title in titles:
        q = urllib.parse.quote(f"{title} {company}")
        urls.append(f"https://www.linkedin.com/search/results/people/?keywords={q}")
    company_q = urllib.parse.quote(f'site:linkedin.com/in "{company}" ({" OR ".join(titles)})')
    urls.append(f"https://www.google.com/search?q={company_q}")
    return urls


def find(job_ref: str) -> dict:
    """Step 1 — who to look for, and the searches that find them."""
    with store.connect() as conn:
        job = store.get_job(conn, job_ref)
        if not job:
            raise SystemExit(f"No job matching {job_ref}")
        roles = llm.json_call(
            TITLE_SYSTEM,
            f"Title: {job['title']}\nCompany: {job['company']}\n\n{(job['description'] or '')[:5000]}",
            mock={
                "manager_titles": ["Engineering Manager", "Head of Engineering"],
                "peer_titles": ["Senior Engineer"],
                "team": "[dry-run] platform",
            },
        )
        titles = roles["manager_titles"] + roles.get("peer_titles", [])
        urls = search_urls(job["company"], titles)
        folder = application_dir(job["id"], job["company"], job["title"])
        (folder / "contacts.md").write_text(
            f"# Who to reach — {job['company']}\n\n"
            f"Team: {roles.get('team', '—')}\n\n"
            f"## Likely titles\n" + "\n".join(f"- {t}" for t in titles) + "\n\n"
            f"## Run these searches yourself\n" + "\n".join(f"- {u}" for u in urls) + "\n\n"
            f"## Then\n`python3 -m agent.jobsearch.outreach verify {job['id'][:8]} --profile profile.txt`\n"
        )
    print(f"  search plan → {folder / 'contacts.md'}")
    for u in urls:
        print(f"    {u}")
    return {"titles": titles, "urls": urls}


def verify(job_ref: str, profile_text: str) -> str:
    """Step 2 — you paste a public profile, Claude finds the hooks."""
    with store.connect() as conn:
        job = store.get_job(conn, job_ref)
        if not job:
            raise SystemExit(f"No job matching {job_ref}")
        parsed = llm.json_call(
            HOOK_SYSTEM,
            f"Company: {job['company']}\n\n## Profile\n{profile_text[:6000]}",
            mock={
                "name": "[dry-run] Contact",
                "title": "Engineering Manager",
                "team": "platform",
                "tenure": "3 years",
                "hooks": [{"hook": "[dry-run] a specific recent post", "strength": "medium"}],
            },
        )
        strong = [h for h in parsed.get("hooks", []) if h.get("strength") in ("high", "medium")]
        cid = store.add_contact(conn, {
            "job_id": job["id"],
            "name": parsed.get("name"),
            "title": parsed.get("title"),
            "company": job["company"],
            "profile_url": None,
            "source": "manual",
            "hooks": parsed.get("hooks", []),
            "status": "ready_to_message" if strong else "needs_hook",
        })
    state = "ready" if strong else "no usable hook yet — find a post, talk or overlap first"
    print(f"  contact {cid[:8]} — {parsed.get('name')} ({parsed.get('title')}): {state}")
    return cid


def draft(contact_id: str) -> str:
    """Step 3 — three variants, saved as drafts. Nothing is sent."""
    with store.connect() as conn:
        contact = conn.execute(
            "SELECT * FROM contacts WHERE id LIKE ?", (contact_id + "%",)
        ).fetchone()
        if not contact:
            raise SystemExit(f"No contact matching {contact_id}")
        cooldown = int(load_preferences().get("outreach", {}).get("cooldown_days_per_contact", 30))
        clash = store.recent_contact_conflict(conn, contact["name"], contact["job_id"], cooldown)
        if clash:
            raise SystemExit(
                f"{contact['name']} was already messaged about {clash} — "
                f"inside the {cooldown}-day cooldown. Reach out about one role at a time."
            )
        job = store.get_job(conn, contact["job_id"])
        analysis = json.loads(job["analysis"] or "{}")
        msgs = llm.json_call(
            MESSAGE_SYSTEM,
            f"## Contact\n{contact['name']} — {contact['title']} at {contact['company']}\n"
            f"Hooks: {contact['hooks']}\n\n"
            f"## Role\n{job['title']}\n\n"
            f"## Candidate's strongest evidence\n{', '.join(analysis.get('matched_skills', []))}",
            mock={
                "connection_note": f"[dry-run] Note about {job['title']} — under 300 chars.",
                "inmail": "[dry-run] 120-word InMail opening with the hook.",
                "email_subject": f"{job['title']} — quick question",
                "email": "[dry-run] 150-word email.",
            },
        )
        folder = application_dir(job["id"], job["company"], job["title"])
        body = "\n\n".join([
            f"# Outreach — {contact['name']} ({contact['title']})",
            f"## LinkedIn connection note ({len(msgs['connection_note'])} chars, limit 300)",
            msgs["connection_note"],
            "## InMail",
            msgs["inmail"],
            f"## Email — subject: {msgs['email_subject']}",
            msgs["email"],
            "_Drafts only. Send them yourself, from your own account._",
        ])
        (folder / "outreach.md").write_text(body)
        for channel in ("connection_note", "inmail", "email"):
            store.add_message(conn, contact["id"], job["id"], channel, msgs[channel])
    print(f"  drafts → {folder / 'outreach.md'}")
    return str(folder / "outreach.md")


REFERRAL_SYSTEM = """Write a referral request to someone the candidate already knows.
Short, warm, and easy to forward: one line of context on the reconnection, the role
and why it fits, then a single paragraph the person can paste to their colleague
verbatim. Make saying no easy. Return JSON: {"message": "", "forwardable_blurb": ""}"""


def referrals(job_ref: str, csv_path: str | None = None) -> list[dict]:
    """Stop 40.5 — who do you already know at this company?

    Export your LinkedIn connections (Settings → Data privacy → Get a copy of your
    data → Connections) to data/connections.csv. It never leaves your machine and
    it is gitignored.
    """
    import csv

    path = Path(csv_path) if csv_path else DATA_DIR / "connections.csv"
    if not path.exists():
        raise SystemExit(f"No connections export at {path} — see the docstring for how to get it")

    with store.connect() as conn:
        job = store.get_job(conn, job_ref)
        if not job:
            raise SystemExit(f"No job matching {job_ref}")
        target = job["company"].lower().strip()

        rows = []
        with path.open(newline="", encoding="utf-8-sig") as fh:
            # LinkedIn puts three notes lines above the header
            lines = [ln for ln in fh if ln.strip()]
        start = next((i for i, ln in enumerate(lines) if "First Name" in ln), 0)
        for row in csv.DictReader(lines[start:]):
            company = (row.get("Company") or "").lower()
            if target and target in company:
                rows.append({
                    "name": f"{row.get('First Name', '')} {row.get('Last Name', '')}".strip(),
                    "title": row.get("Position", ""),
                    "company": row.get("Company", ""),
                    "connected_on": row.get("Connected On", ""),
                    "url": row.get("URL", ""),
                })

        if not rows:
            print(f"  no connections at {job['company']} — cold outreach it is")
            return []

        rows.sort(key=lambda r: r["connected_on"])  # longest-standing first
        folder = application_dir(job["id"], job["company"], job["title"])
        out = [f"# Referral paths — {job['company']}", "",
               f"{len(rows)} connection(s) already there. Ask the closest one first.", ""]
        for person in rows[:5]:
            drafted = llm.json_call(
                REFERRAL_SYSTEM,
                f"## Person\n{person['name']} — {person['title']} at {person['company']} "
                f"(connected {person['connected_on']})\n\n"
                f"## Role\n{job['title']} — {job['url']}\n\n"
                f"## Why it fits\n{job['analysis'] or ''}",
                mock={
                    "message": f"[dry-run] Referral ask to {person['name']}.",
                    "forwardable_blurb": "[dry-run] One paragraph they can paste to the hiring manager.",
                },
                max_tokens=900,
            )
            cid = store.add_contact(conn, {
                "job_id": job["id"], "name": person["name"], "title": person["title"],
                "company": person["company"], "profile_url": person["url"],
                "source": "connections.csv", "hooks": [{"hook": "existing connection", "strength": "high"}],
                "status": "referral_candidate",
            })
            store.add_message(conn, cid, job["id"], "referral", drafted["message"])
            out += [
                f"## {person['name']} — {person['title']}  ·  connected {person['connected_on']}",
                "", drafted["message"].strip(), "",
                "**Blurb they can forward:**", "", drafted["forwardable_blurb"].strip(),
                "", f"{person['url']}", "",
            ]
        (folder / "referrals.md").write_text("\n".join(out))
        store.upsert_application(conn, job["id"], referral_source=rows[0]["name"])

    print(f"  {len(rows)} referral path(s) → {folder / 'referrals.md'}")
    return rows


def stats() -> None:
    """Referred versus cold — the number that decides where your hours go."""
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT CASE WHEN referral_source IS NULL THEN 'cold' ELSE 'referred' END AS kind, "
            "COUNT(*) AS n, SUM(CASE WHEN status IN ('replied','interview') THEN 1 ELSE 0 END) AS replies "
            "FROM applications GROUP BY kind"
        ).fetchall()
    print(f"  {'route':<10}{'sent':>6}{'replies':>9}{'rate':>8}")
    for r in rows:
        rate = f"{(r['replies'] or 0) / r['n'] * 100:.0f}%" if r["n"] else "—"
        print(f"  {r['kind']:<10}{r['n']:>6}{r['replies'] or 0:>9}{rate:>8}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Find people and draft outreach")
    ap.add_argument("command",
                    choices=["find", "verify", "draft", "referrals", "sent", "replied", "stats"])
    ap.add_argument("ref", nargs="?", default="", help="job id, or contact id for draft/sent/replied")
    ap.add_argument("--profile", help="path to a pasted public profile (verify)")
    ap.add_argument("--csv", help="path to your LinkedIn connections export (referrals)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    llm.set_offline(args.dry_run)

    if args.command == "find":
        find(args.ref)
    elif args.command == "verify":
        text = open(args.profile).read() if args.profile else input("Paste the profile text: ")
        verify(args.ref, text)
    elif args.command == "draft":
        draft(args.ref)
    elif args.command == "referrals":
        referrals(args.ref, args.csv)
    elif args.command == "stats":
        stats()
    else:  # sent / replied — you tell the tracker what you did
        with store.connect() as conn:
            state = "messaged" if args.command == "sent" else "replied"
            contact = store.set_contact_status(conn, args.ref, state)
            print(f"  {contact['name'] if contact else args.ref} → {state}")
