"""Stage 1 — collect, filter, dedupe, store.

Cheap rules run before any model call: title allow-list, excluded keywords,
location policy, max age. What survives lands in the tracker as status='new'.
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from . import sources, store
from .config import load_preferences


def normalise(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def title_matches(title: str, prefs: dict) -> bool:
    t = normalise(title)
    allow = [normalise(x) for x in prefs.get("target_titles", [])]
    if allow and not any(a in t for a in allow):
        return False
    for bad in prefs.get("exclude_title_keywords", []):
        if normalise(bad) in t:
            return False
    return True


def location_ok(job: dict, prefs: dict) -> bool:
    loc = normalise(job.get("location")) + " " + normalise(job.get("remote"))
    if prefs.get("remote_only") and "remote" not in loc and "anywhere" not in loc:
        return False
    allowed = [normalise(x) for x in prefs.get("locations", [])]
    if not allowed:
        return True
    return any(a in loc for a in allowed) or "remote" in loc


def body_ok(job: dict, prefs: dict) -> bool:
    body = normalise(job.get("description"))
    return not any(normalise(bad) in body for bad in prefs.get("exclude_keywords", []))


def fresh_enough(job: dict, max_age_days: int) -> bool:
    raw = job.get("posted_at")
    if not raw:
        return True
    try:
        posted = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return True
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
    return posted >= datetime.now(timezone.utc) - timedelta(days=max_age_days)


def dedupe(jobs: list[dict]) -> tuple[list[dict], int]:
    seen: set[str] = set()
    kept, dupes = [], 0
    for job in jobs:
        key = f"{normalise(job.get('company'))}|{normalise(job.get('title'))}|{normalise(job.get('location'))[:12]}"
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        kept.append(job)
    return kept, dupes


def run(dry_run: bool = False) -> dict[str, Any]:
    prefs = load_preferences()
    enabled = [{"type": "fixtures"}] if dry_run else prefs.get("sources", [])
    max_age = int(prefs.get("max_age_days", 21))

    collected: list[dict] = []
    for label, jobs in sources.collect(enabled):
        kept = [
            j for j in jobs
            if title_matches(j.get("title", ""), prefs)
            and location_ok(j, prefs)
            and body_ok(j, prefs)
            and fresh_enough(j, max_age)
        ]
        print(f"  {label:<28} fetched {len(jobs):>4}  kept {len(kept):>4}")
        collected.extend(kept)

    collected, dupes = dedupe(collected)
    new_count = 0
    with store.connect() as conn:
        for job in collected:
            _, is_new = store.upsert_job(conn, job)
            new_count += int(is_new)

    print(f"  {'total':<28} kept {len(collected):>4}  duplicates {dupes:>4}  new {new_count:>4}")
    return {"kept": len(collected), "duplicates": dupes, "new": new_count}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Scrape and filter jobs")
    ap.add_argument("--dry-run", action="store_true", help="use fixtures, no network")
    run(**vars(ap.parse_args()))
