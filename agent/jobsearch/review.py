"""The human gate.

Prints everything the agent produced for one application, side by side with the
apply link, and asks for an explicit yes. There is no flag that skips this and
there will not be one — a person applies for the job, the agent just does the
typing.
"""

from __future__ import annotations

import argparse
import difflib
import webbrowser
from pathlib import Path

from . import store
from .config import load_resume


def resume_diff(tailored: Path) -> str:
    if not tailored.exists():
        return "(no tailored resume yet)"
    diff = difflib.unified_diff(
        load_resume().splitlines(),
        tailored.read_text().splitlines(),
        fromfile="master resume",
        tofile="tailored",
        lineterm="",
        n=1,
    )
    return "\n".join(diff) or "(identical to master)"


def show(job_ref: str, open_url: bool = False) -> bool:
    with store.connect() as conn:
        job = store.get_job(conn, job_ref)
        if not job:
            raise SystemExit(f"No job matching {job_ref}")
        app = conn.execute(
            "SELECT * FROM applications WHERE job_id = ?", (job["id"],)
        ).fetchone()
        if not app or not app["folder"]:
            raise SystemExit("Nothing prepared for this job yet — run tailor first")
        folder = Path(app["folder"])

        print(f"\n{'=' * 72}\n{job['title']} — {job['company']}  (score {job['score']})\n{'=' * 72}")
        print(f"\n--- resume changes vs master ---\n{resume_diff(folder / 'resume.md')}")
        for name, label in (("letter.md", "cover letter"), ("evidence.md", "evidence map"),
                            ("answers.md", "screening answers"), ("outreach.md", "outreach drafts")):
            path = folder / name
            if path.exists():
                print(f"\n--- {label} ---\n{path.read_text().strip()}")
        print(f"\n--- apply at ---\n{job['url']}\n")

        answer = input("Approved to send? [y/N] ").strip().lower()
        if answer != "y":
            print("  held back — nothing sent")
            return False

        import getpass

        store.upsert_application(
            conn, job["id"], status="approved_to_send",
            approved_by=getpass.getuser(), approved_at=store.now(),
        )
    if open_url and job["url"]:
        webbrowser.open(job["url"])
    print("  approved — you submit it; then run: queue submit <id>")
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Review one prepared application")
    ap.add_argument("job_id")
    ap.add_argument("--open", action="store_true", help="open the apply URL after approval")
    args = ap.parse_args()
    show(args.job_id, open_url=args.open)
