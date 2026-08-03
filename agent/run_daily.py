"""Daily entrypoint: scrape → score → digest.

    python3 -m agent.run_daily --dry-run   # fixtures, no network, no API key
    python3 -m agent.run_daily             # the real thing

Exits non-zero if any stage fails, so a scheduler notices when it breaks.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import date

from agent.jobsearch import digest, followup, llm, scrape, score, store
from agent.jobsearch.config import LOGS_DIR

STAGES = [
    ("scrape", scrape.run),
    ("score", score.run),
    ("digest", digest.run),
    ("followup", followup.run),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the daily job search")
    ap.add_argument("--dry-run", action="store_true", help="fixtures + mock model, no credentials")
    ap.add_argument("--status", action="store_true", help="print the pipeline and exit")
    args = ap.parse_args()

    if args.status:
        with store.connect() as conn:
            print(store.status_report(conn))
        return 0

    llm.set_offline(args.dry_run)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log = LOGS_DIR / f"{date.today().isoformat()}.log"
    failures = []

    with log.open("a") as fh:
        for name, fn in STAGES:
            print(f"\n[{name}]")
            fh.write(f"\n[{name}] {store.now()}\n")
            try:
                result = fn(dry_run=args.dry_run)
                fh.write(f"  ok {result}\n")
            except Exception:
                failures.append(name)
                traceback.print_exc()
                fh.write(traceback.format_exc())

    with store.connect() as conn:
        print(f"\n{store.status_report(conn)}")

    if failures:
        print(f"\nFAILED stages: {', '.join(failures)} (log: {log})", file=sys.stderr)
        return 1
    print(f"\nlog: {log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
