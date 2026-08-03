"""Onboarding — turn an uploaded resume plus a few answers into a profile.

Everything here runs on the person's own machine and writes to their own
agent/config/. No resume is uploaded anywhere: the file is read, turned into
text, and (if a key is set) sent to Claude only to be restructured.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

from . import llm
from .config import config_dir

SUPPORTED = (".pdf", ".docx", ".md", ".txt", ".rtf")

RESUME_SYSTEM = """Restructure a raw resume into clean Markdown for an automated job search.

Rules:
- Keep every fact exactly as written. Never add an employer, date, title, tool or metric.
- Sections in this order: name heading, contact line, ## Summary, ## Experience
  (### Role — Company (dates), then bullets), ## Skills, ## Education.
- Then add a "## Story bank" section: 10-15 achievement bullets drawn from the
  experience above, each self-contained, each keeping its original numbers, each
  ending with (Company, year).
- If the resume has no metric for an achievement, keep the bullet but list it in
  missing_metrics so the candidate can add one later. Do not invent numbers.

Return JSON: {"name": "", "contact": "", "resume_md": "the full Markdown",
"missing_metrics": ["bullets that have no number in them"]}"""


def extract_text(filename: str, data: bytes) -> tuple[str, str | None]:
    """Resume file to plain text. Returns (text, warning)."""
    suffix = Path(filename).suffix.lower()

    if suffix in (".md", ".txt", ".rtf"):
        text = data.decode("utf-8", errors="replace")
        if suffix == ".rtf":
            text = re.sub(r"\\[a-z]+-?\d* ?|[{}]", "", text)
        return text.strip(), None

    if suffix == ".docx":
        with zipfile.ZipFile(BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
        xml = re.sub(r"</w:p>", "\n", xml)
        xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
        return re.sub(r"<[^>]+>", "", xml).strip(), None

    if suffix == ".pdf":
        if shutil.which("pdftotext"):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
                fh.write(data)
                tmp = fh.name
            out = subprocess.run(
                ["pdftotext", "-layout", tmp, "-"], capture_output=True, text=True
            ).stdout
            Path(tmp).unlink(missing_ok=True)
            if out.strip():
                return out.strip(), None
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(BytesIO(data))
            out = "\n".join(page.extract_text() or "" for page in reader.pages)
            if out.strip():
                return out.strip(), None
        except ImportError:
            pass
        raise ValueError(
            "Could not read this PDF. Install poppler-utils (pdftotext) or pypdf, "
            "or paste the text of your resume into the box instead."
        )

    raise ValueError(f"Unsupported file type '{suffix}'. Use {', '.join(SUPPORTED)} or paste the text.")


def _offline_profile(text: str) -> dict:
    """No API key: keep the person's text intact and scaffold the story bank."""
    bullets = [
        b.strip(" -*•\t") for b in text.splitlines() if b.strip().startswith(("-", "*", "•"))
    ]
    story = "\n".join(f"- {b}" for b in bullets[:15]) or "- (add your achievements here, one per line)"
    return {
        "name": next((ln.strip() for ln in text.splitlines() if ln.strip()), "Your Name"),
        "contact": "",
        "resume_md": f"{text.strip()}\n\n## Story bank\n\n{story}\n",
        "missing_metrics": [b for b in bullets[:15] if not re.search(r"\d", b)],
    }


def structure_resume(text: str) -> dict:
    """Raw resume text to structured Markdown with a story bank."""
    if not text.strip():
        raise ValueError("The resume is empty — upload a file or paste the text.")
    return llm.json_call(
        RESUME_SYSTEM, text[:20000], mock=_offline_profile(text),
        model=llm.MODEL_MAIN, max_tokens=6000,
    )


def _split(value: str) -> list[str]:
    return [v.strip() for v in re.split(r"[,\n;]+", value or "") if v.strip()]


def build_preferences(answers: dict) -> dict:
    sources = []
    for raw in _split(answers.get("boards", "")):
        if ":" in raw:
            kind, name = raw.split(":", 1)
            key = "board" if kind.strip() == "greenhouse" else "company"
            sources.append({"type": kind.strip(), key: name.strip()})
    if answers.get("include_remoteok"):
        sources.append({"type": "remoteok"})

    return {
        "target_titles": [t.lower() for t in _split(answers.get("titles", ""))],
        "exclude_title_keywords": [t.lower() for t in _split(answers.get("exclude_titles", ""))],
        "seniority": answers.get("seniority", ""),
        "locations": [l.lower() for l in _split(answers.get("locations", ""))],
        "remote_only": bool(answers.get("remote_only")),
        "work_authorisation": answers.get("work_authorisation", ""),
        "salary_floor": answers.get("salary_floor", ""),
        "exclude_keywords": [k.lower() for k in _split(answers.get("exclude_keywords", ""))],
        "max_age_days": int(answers.get("max_age_days") or 21),
        "score_threshold": int(answers.get("score_threshold") or 72),
        "daily_shortlist_size": 10,
        "sources": sources,
        "outreach": {"max_followups": 2, "followup_days": [4, 11], "cooldown_days_per_contact": 30},
    }


def build_snippets(answers: dict, profile: dict) -> dict:
    return {
        "notice_period": answers.get("notice_period", ""),
        "earliest_start": answers.get("earliest_start", ""),
        "salary_expectation": answers.get("salary_expectation", ""),
        "work_authorisation": answers.get("work_authorisation", ""),
        "relocation": answers.get("relocation", ""),
        "why_leaving": answers.get("why_leaving", ""),
        "linkedin": answers.get("linkedin", ""),
        "github": answers.get("github", ""),
        "portfolio": answers.get("portfolio", ""),
        "how_did_you_hear": "",
        "_contact_line": profile.get("contact", ""),
    }


def write_profile(resume_text: str, answers: dict, overwrite: bool = False) -> dict:
    """Write resume.md, preferences.json and snippets.json. Existing files are
    backed up rather than lost."""
    profile = structure_resume(resume_text)
    files = {
        "resume.md": profile["resume_md"],
        "preferences.json": json.dumps(build_preferences(answers), ensure_ascii=False, indent=2),
        "snippets.json": json.dumps(build_snippets(answers, profile), ensure_ascii=False, indent=2),
    }

    target = config_dir()
    target.mkdir(parents=True, exist_ok=True)
    existing = [n for n in files if (target / n).exists()]
    if existing and not overwrite:
        return {"needs_confirmation": True, "existing": existing}

    written, backups = [], []
    for name, content in files.items():
        path = target / name
        if path.exists():
            backup = path.with_suffix(path.suffix + ".bak")
            shutil.copy2(path, backup)
            backups.append(str(backup))
        path.write_text(content if content.endswith("\n") else content + "\n")
        written.append(str(path))

    return {
        "written": written,
        "backups": backups,
        "name": profile.get("name", ""),
        "missing_metrics": profile.get("missing_metrics", []),
        "offline": not llm.available(),
    }
