"""Stage 3 — the morning digest.

One Markdown page: today's shortlist ranked, then a card per job. Approve or
reject straight from it by id.
"""

from __future__ import annotations

import argparse
import json
from datetime import date

from . import store
from .config import DIGESTS_DIR, load_preferences


def build(limit: int = 10) -> str:
    prefs = load_preferences()
    threshold = int(prefs.get("score_threshold", 70))
    with store.connect() as conn:
        jobs = [j for j in store.by_status(conn, "scored") if (j["score"] or 0) >= threshold][:limit]

    today = date.today().isoformat()
    out = [f"# Job digest — {today}", ""]
    if not jobs:
        out += ["Nothing above the score threshold today.", ""]
    else:
        out += [
            f"{len(jobs)} roles above {threshold}. Approve with: "
            f"`python3 -m agent.jobsearch.digest --approve <id,id>`",
            "",
            "| # | Score | Role | Company | Location | Salary | id |",
            "|--:|------:|------|---------|----------|--------|----|",
        ]
        for i, j in enumerate(jobs, 1):
            out.append(
                f"| {i} | {j['score']} | {j['title']} | {j['company']} | "
                f"{j['location'] or '—'} | {j['salary_raw'] or '—'} | `{j['id'][:8]}` |"
            )
        out.append("")
        for j in jobs:
            a = json.loads(j["analysis"] or "{}")
            out += [
                f"## {j['title']} — {j['company']}  ·  {j['score']}",
                "",
                f"{a.get('verdict', '')}",
                "",
                f"- **Matches:** {', '.join(a.get('matched_skills', [])) or '—'}",
                f"- **Gaps:** {', '.join(a.get('missing_skills', [])) or '—'}",
                f"- **Tailoring:** {'; '.join(a.get('tailoring_hints', [])) or '—'}",
                f"- **Apply:** {j['url'] or '—'}",
                f"- **id:** `{j['id'][:8]}`",
                "",
            ]

    DIGESTS_DIR.mkdir(parents=True, exist_ok=True)
    path = DIGESTS_DIR / f"{today}.md"
    path.write_text("\n".join(out))
    return str(path)


def set_many(ids: str, status: str) -> None:
    with store.connect() as conn:
        for raw in ids.split(","):
            job = store.get_job(conn, raw.strip())
            if not job:
                print(f"  ! no job matching {raw.strip()}")
                continue
            store.set_status(conn, job["id"], status)
            if status == "approved":
                store.upsert_application(conn, job["id"])
            print(f"  {status}: {job['title']} — {job['company']}")


def run(**_) -> dict:
    path = build()
    print(f"  digest → {path}")
    return {"digest": path}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Render / act on the daily digest")
    ap.add_argument("--approve", help="comma-separated job ids to approve")
    ap.add_argument("--reject", help="comma-separated job ids to reject")
    args = ap.parse_args()
    if args.approve:
        set_many(args.approve, "approved")
    if args.reject:
        set_many(args.reject, "rejected")
    if not (args.approve or args.reject):
        run()
