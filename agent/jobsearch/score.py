"""Stage 2 — score each new job against the resume.

One call per job, cheap model, result cached on the job row so re-runs are free.
Anything below the threshold never reaches the resume line.
"""

from __future__ import annotations

import argparse

from . import llm, store
from .config import load_preferences, resume_summary

SYSTEM = """You screen job postings for one candidate.
Be strict: a high score means the candidate would likely pass a recruiter screen today.
Judge only on evidence present in the resume. Never assume unstated experience.
Return JSON: {"score": 0-100, "matched_skills": [], "missing_skills": [],
"verdict": "one sentence", "tailoring_hints": ["..."]}"""


def _mock(job) -> dict:
    """Deterministic stand-in so --dry-run exercises the same code path."""
    title = (job["title"] or "").lower()
    base = 78 if any(k in title for k in ("senior", "lead", "staff")) else 66
    return {
        "score": base + (len(job["company"]) % 12),
        "matched_skills": ["python", "data pipelines", "stakeholder communication"],
        "missing_skills": ["kubernetes"],
        "verdict": "[dry-run] Plausible match — run with ANTHROPIC_API_KEY for a real score.",
        "tailoring_hints": ["Lead with the pipeline work", "Use the posting's exact stack names"],
    }


def score_job(job, resume: str) -> dict:
    prompt = (
        f"## Candidate resume\n{resume}\n\n"
        f"## Posting\nTitle: {job['title']}\nCompany: {job['company']}\n"
        f"Location: {job['location']}\nSalary: {job['salary_raw']}\n\n"
        f"{(job['description'] or '')[:8000]}"
    )
    return llm.json_call(SYSTEM, prompt, mock=_mock(job))


def run(limit: int = 40, **_) -> dict:
    prefs = load_preferences()
    threshold = int(prefs.get("score_threshold", 70))
    resume = resume_summary()
    scored = passed = 0

    with store.connect() as conn:
        for job in store.by_status(conn, "new")[:limit]:
            result = score_job(job, resume)
            score = int(result.get("score", 0))
            store.save_analysis(conn, job["id"], score, result)
            scored += 1
            if score >= threshold:
                passed += 1
            else:
                store.set_status(conn, job["id"], "rejected")
    print(f"  scored {scored}, above threshold ({threshold}): {passed}")
    return {"scored": scored, "passed": passed}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Score new jobs against the resume")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args()
    llm.set_offline(args.dry_run)
    run(limit=args.limit)
