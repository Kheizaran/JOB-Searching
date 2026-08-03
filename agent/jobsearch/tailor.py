"""Stage 4 — tailor the resume for one approved job.

Three steps, each inspectable:
  1. parse_jd          — what the posting actually asks for
  2. evidence_map      — which real bullet backs each requirement (or: a gap)
  3. tailored resume   — same facts, reordered and reworded, plus a cover letter

The system prompts forbid inventing experience. That constraint is the product:
a resume that survives the interview is worth more than one that wins the screen.
"""

from __future__ import annotations

import argparse
import json

from . import llm, store
from .config import application_dir, load_resume, load_snippets, story_bank

JD_SYSTEM = """Extract what a job posting really requires.
Preserve the posting's own spelling of every technology (keyword filters match literally).
Return JSON: {"must_have": [], "nice_to_have": [], "exact_keywords": [],
"seniority": "", "team_problem": "one sentence", "tone": ""}"""

EVIDENCE_SYSTEM = """Map job requirements to a candidate's real achievements.
Use ONLY the achievements given. If nothing supports a requirement, mark it a gap —
never infer, upgrade, or invent experience.
Return JSON: {"matched": [{"requirement": "", "evidence": "", "confidence": "high|medium|low"}],
"gaps": [""]}"""

RESUME_SYSTEM = """Rewrite a resume for one specific job.
Hard rules:
- Every claim must already exist in the master resume. No new employers, dates, titles, tools or metrics.
- Keep every number exactly as written in the source.
- Reorder sections and bullets so the posting's must-haves appear first.
- Use the posting's exact keyword spellings where they are honestly applicable.
- Single column Markdown, no tables, no columns, no graphics.
Return only the resume Markdown."""

LETTER_SYSTEM = """Write a three-paragraph cover letter.
P1: a specific reason for this company drawn from the posting itself — no flattery.
P2: the two strongest pieces of evidence for their must-haves, with the metrics.
P3: what the candidate would work on in the first 90 days.
Under 250 words. Plain, direct, no AI throat-clearing ("I am excited to apply").
Return only the letter."""


def parse_jd(job) -> dict:
    return llm.json_call(
        JD_SYSTEM,
        f"Title: {job['title']}\nCompany: {job['company']}\n\n{(job['description'] or '')[:9000]}",
        mock={
            "must_have": ["python", "sql", "data pipelines"],
            "nice_to_have": ["kubernetes", "dbt"],
            "exact_keywords": ["Python", "SQL", "Airflow"],
            "seniority": "senior",
            "team_problem": "[dry-run] The team needs reliable daily data delivery.",
            "tone": "direct, engineering-led",
        },
    )


def evidence_map(jd: dict, bank: str) -> dict:
    return llm.json_call(
        EVIDENCE_SYSTEM,
        f"## Requirements\n{json.dumps(jd, ensure_ascii=False, indent=2)}\n\n## Achievements\n{bank}",
        mock={
            "matched": [
                {"requirement": r, "evidence": "[dry-run] strongest matching bullet", "confidence": "medium"}
                for r in jd.get("must_have", [])
            ],
            "gaps": jd.get("nice_to_have", []),
        },
        max_tokens=3000,
    )


def tailored_resume(job, jd: dict, evidence: dict, master: str) -> str:
    return llm.text_call(
        RESUME_SYSTEM,
        f"## Target role\n{job['title']} at {job['company']}\n\n"
        f"## What they ask for\n{json.dumps(jd, ensure_ascii=False, indent=2)}\n\n"
        f"## Requirement → evidence\n{json.dumps(evidence, ensure_ascii=False, indent=2)}\n\n"
        f"## Master resume\n{master}",
        mock=f"# [dry-run] Resume tailored for {job['title']} at {job['company']}\n\n"
             f"Run with ANTHROPIC_API_KEY set to generate the real document.\n\n"
             f"Priority keywords: {', '.join(jd.get('exact_keywords', []))}\n",
        max_tokens=4000,
    )


def cover_letter(job, jd: dict, evidence: dict) -> str:
    return llm.text_call(
        LETTER_SYSTEM,
        f"## Role\n{job['title']} at {job['company']}\n\n"
        f"## Posting\n{(job['description'] or '')[:5000]}\n\n"
        f"## Evidence\n{json.dumps(evidence, ensure_ascii=False, indent=2)}",
        mock=f"[dry-run] Cover letter for {job['title']} at {job['company']}.",
        max_tokens=1200,
    )


ANSWERS_SYSTEM = """Prepare a candidate's application-form answers.
Extract every free-text question the posting asks for, and answer each in the
candidate's voice using only facts from their resume and saved snippets.
Also list the plain fields the form will ask for (name, links, availability).
Return JSON: {"fields": ["field the site will ask for"],
"answers": [{"question": "", "answer": "", "source": "snippet|resume"}]}"""


def screening_answers(job, jd: dict, resume: str) -> str:
    """Stop 30.2 — the long questions, answered before you open the form."""
    snippets = load_snippets()
    result = llm.json_call(
        ANSWERS_SYSTEM,
        f"## Posting\n{(job['description'] or '')[:6000]}\n\n"
        f"## Saved snippets\n{json.dumps(snippets, ensure_ascii=False, indent=2)}\n\n"
        f"## Resume\n{resume[:5000]}",
        mock={
            "fields": ["Full name", "Email", "LinkedIn", "Notice period", "Salary expectation"],
            "answers": [
                {"question": "When could you start?", "answer": snippets.get("notice_period", ""), "source": "snippet"},
                {"question": "Why this role?", "answer": "[dry-run] answer in the candidate's voice.", "source": "resume"},
            ],
        },
        max_tokens=2500,
    )
    lines = ["# Screening answers", "", "## Submission checklist", ""]
    lines += [f"- [ ] {f}" for f in result.get("fields", [])]
    lines += ["", "## Answers", ""]
    for a in result.get("answers", []):
        lines += [
            f"### {a['question']}",
            f"_{len(a['answer'])} characters · from {a.get('source', 'resume')}_",
            "",
            a["answer"],
            "",
        ]
    return "\n".join(lines)


def evidence_table(evidence: dict) -> str:
    rows = ["| Requirement | Evidence | Confidence |", "|---|---|---|"]
    for m in evidence.get("matched", []):
        rows.append(f"| {m['requirement']} | {m['evidence']} | {m.get('confidence', '')} |")
    gaps = evidence.get("gaps", [])
    if gaps:
        rows += ["", "**Gaps — interview prep, not resume lines:** " + ", ".join(gaps)]
    return "\n".join(rows)


def prepare(job_ref: str) -> str:
    """Run the full tailoring pass for one job; returns the folder path."""
    with store.connect() as conn:
        job = store.get_job(conn, job_ref)
        if not job:
            raise SystemExit(f"No job matching {job_ref}")
        if job["status"] not in ("approved", "prepared"):
            raise SystemExit(f"Job {job['id'][:8]} is '{job['status']}' — approve it first")

        folder = application_dir(job["id"], job["company"], job["title"])
        master = load_resume()
        jd = parse_jd(job)
        evidence = evidence_map(jd, story_bank())
        resume = tailored_resume(job, jd, evidence, master)
        letter = cover_letter(job, jd, evidence)
        answers = screening_answers(job, jd, master)

        (folder / "jd.json").write_text(json.dumps(jd, ensure_ascii=False, indent=2))
        (folder / "evidence.md").write_text(evidence_table(evidence))
        (folder / "resume.md").write_text(resume)
        (folder / "letter.md").write_text(letter)
        (folder / "answers.md").write_text(answers)

        store.set_status(conn, job["id"], "prepared")
        store.upsert_application(conn, job["id"], status="prepared", folder=str(folder))

    print(f"  prepared → {folder}")
    return str(folder)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Tailor a resume + letter for one job")
    ap.add_argument("job_id")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    llm.set_offline(args.dry_run)
    prepare(args.job_id)
