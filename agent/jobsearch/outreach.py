"""Stage 5 — the human bridge.

The agent never touches LinkedIn. It works out *who* to look for, hands you
ready-to-run search URLs, and once you paste a profile back it drafts the
messages. You stay the one who clicks connect.
"""

from __future__ import annotations

import argparse
import json
import urllib.parse

from . import llm, store
from .config import application_dir

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


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Find people and draft outreach")
    ap.add_argument("command", choices=["find", "verify", "draft"])
    ap.add_argument("ref", help="job id (find/verify) or contact id (draft)")
    ap.add_argument("--profile", help="path to a pasted public profile (verify)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    llm.set_offline(args.dry_run)

    if args.command == "find":
        find(args.ref)
    elif args.command == "verify":
        text = open(args.profile).read() if args.profile else input("Paste the profile text: ")
        verify(args.ref, text)
    else:
        draft(args.ref)
