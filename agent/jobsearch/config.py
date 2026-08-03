"""Paths and profile loading.

Real files (resume.md, preferences.json) are gitignored; the *.example.*
versions are committed so a fresh clone runs immediately.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "agent" / "config"
DATA_DIR = ROOT / "data"
APPLICATIONS_DIR = DATA_DIR / "applications"
DIGESTS_DIR = DATA_DIR / "digests"
LOGS_DIR = DATA_DIR / "logs"


def _pick(name: str) -> Path:
    real = CONFIG_DIR / name
    if real.exists():
        return real
    stem, suffix = name.rsplit(".", 1)
    example = CONFIG_DIR / f"{stem}.example.{suffix}"
    if example.exists():
        return example
    raise FileNotFoundError(f"Missing {real} (and no example fallback)")


def load_preferences() -> dict:
    return json.loads(_pick("preferences.json").read_text())


def load_resume() -> str:
    return _pick("resume.md").read_text()


def load_snippets() -> dict:
    """Standard answers reused verbatim across applications."""
    return json.loads(_pick("snippets.json").read_text())


def resume_summary(limit: int = 6000) -> str:
    """Resume text trimmed to keep scoring calls cheap."""
    return load_resume()[:limit]


def story_bank() -> str:
    """The '## Story bank' section, the only source of achievement bullets."""
    text = load_resume()
    marker = "## Story bank"
    if marker not in text:
        return ""
    return text.split(marker, 1)[1].strip()


def application_dir(job_id: str, company: str = "", title: str = "") -> Path:
    slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in f"{company}-{title}".lower())
    slug = "-".join(filter(None, slug.split("-")))[:60]
    path = APPLICATIONS_DIR / f"{job_id}{('-' + slug) if slug else ''}"
    path.mkdir(parents=True, exist_ok=True)
    return path
