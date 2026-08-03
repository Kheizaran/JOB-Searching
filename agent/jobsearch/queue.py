"""The application queue — one CLI over the tracker.

States move one way:  approved → prepared → approved_to_send → submitted → replied
`prepare` runs the tailoring pass; nothing reaches 'submitted' without a human
approval recorded by review.py.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import llm, render, review, store, tailor


def prepare(job_ref: str) -> str:
    """Tailor the documents, then render the PDF. A missing PDF engine is a
    warning, not a failure — the Markdown is still reviewable."""
    folder = tailor.prepare(job_ref)
    try:
        render.render(job_ref)
    except SystemExit as exc:
        print(f"  ! pdf skipped — {exc}")
    return folder


def show_queue() -> None:
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT j.id, j.title, j.company, j.score, j.status AS job_status, "
            "a.status AS app_status, a.folder FROM jobs j "
            "LEFT JOIN applications a ON a.job_id = j.id "
            "WHERE j.status IN ('approved','prepared','submitted') "
            "ORDER BY j.score DESC"
        ).fetchall()
        if not rows:
            print("  queue empty — approve something from today's digest first")
            return
        print(f"  {'id':<10}{'score':>6}  {'state':<18}{'role':<38}company")
        for r in rows:
            state = r["app_status"] or r["job_status"]
            missing = ""
            if r["folder"]:
                folder = Path(r["folder"])
                missing = " ".join(
                    f"!{n}" for n in ("resume.md", "letter.md") if not (folder / n).exists()
                )
            print(f"  {r['id'][:8]:<10}{r['score'] or 0:>6}  {state:<18}"
                  f"{(r['title'] or '')[:36]:<38}{r['company']} {missing}")
        print(f"\n{store.status_report(conn)}")


def submit(job_ref: str, portal: str = "", confirmation: str = "") -> None:
    with store.connect() as conn:
        job = store.get_job(conn, job_ref)
        if not job:
            raise SystemExit(f"No job matching {job_ref}")
        app = conn.execute(
            "SELECT * FROM applications WHERE job_id = ?", (job["id"],)
        ).fetchone()
        if not app or app["status"] != "approved_to_send":
            raise SystemExit("Not approved yet — run `review` and approve it first")
        store.set_status(conn, job["id"], "submitted")
        store.upsert_application(
            conn, job["id"], status="submitted", submitted_at=store.now(),
            portal=portal, confirmation=confirmation,
        )
        print(f"  submitted: {job['title']} — {job['company']}")
        print(f"\n{store.status_report(conn)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Application queue")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p = sub.add_parser("prepare"); p.add_argument("job_id"); p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("review"); p.add_argument("job_id"); p.add_argument("--open", action="store_true")
    p = sub.add_parser("submit"); p.add_argument("job_id")
    p.add_argument("--portal", default=""); p.add_argument("--confirmation", default="")
    p = sub.add_parser("replied"); p.add_argument("job_id")
    args = ap.parse_args()

    if args.cmd == "list":
        show_queue()
    elif args.cmd == "prepare":
        llm.set_offline(args.dry_run)
        prepare(args.job_id)
    elif args.cmd == "review":
        review.show(args.job_id, open_url=args.open)
    elif args.cmd == "replied":
        with store.connect() as conn:
            job = store.get_job(conn, args.job_id)
            if not job:
                raise SystemExit(f"No job matching {args.job_id}")
            store.upsert_application(conn, job["id"], status="replied")
            store.set_status(conn, job["id"], "replied")
            print(f"  replied: {job['title']} — {job['company']} (follow-ups stop here)")
    else:
        submit(args.job_id, args.portal, args.confirmation)
