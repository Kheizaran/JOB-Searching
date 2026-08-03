"""The nightly job: run every active user's search.

    python3 -m saas.worker            # one pass over all enabled users
    python3 -m saas.worker --user <id>

Run it from cron at 06:00. It is deliberately sequential and slow — each user's
pass is a handful of API calls on their own key, and one user's failure must
never stop the next one.
"""

from __future__ import annotations

import argparse
import traceback

from agent.jobsearch import digest, llm, scrape, score
from agent.jobsearch.workspace import workspace

from . import db, security


def run_for(user) -> tuple[str, str]:
    key = security.decrypt_key(user["api_key_enc"])
    if not key:
        return "skipped", "no API key"
    try:
        with workspace(db.workspace_for(user["id"])), llm.use_key(key):
            found = scrape.run()
            scored = score.run()
            path = digest.build()
        return "ok", f"{found['new']} new, {scored['passed']} above threshold → {path}"
    except Exception:
        return "failed", traceback.format_exc(limit=3)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the daily search for every user")
    ap.add_argument("--user", help="one user id instead of all")
    args = ap.parse_args()

    with db.connect() as conn:
        if args.user:
            users = [db.user_by_id(conn, args.user)]
        else:
            users = conn.execute(
                "SELECT * FROM users WHERE daily_enabled = 1 AND onboarded_at IS NOT NULL"
            ).fetchall()
        users = [u for u in users if u]

    failures = 0
    for user in users:
        with db.connect() as conn:
            run_id = db.start_run(conn, user["id"])
        status, detail = run_for(user)
        failures += status == "failed"
        with db.connect() as conn:
            db.finish_run(conn, run_id, user["id"], status, detail)
        print(f"  {user['email']:<34} {status:<8} {detail.splitlines()[-1][:70] if detail else ''}")

    print(f"\n  {len(users)} user(s), {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
