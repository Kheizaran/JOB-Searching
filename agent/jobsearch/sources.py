"""Job sources.

Every source is a function that takes its config and returns a list of dicts in
one normalised shape:

    source, external_id, title, company, location, remote, url,
    description, salary_raw, posted_at

Only boards with public JSON endpoints are implemented. LinkedIn is deliberately
absent: its terms forbid scraping, and the Human Bridge line uses it the way a
person does — in a browser, with the agent preparing the search and the message.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"
CACHE_TTL = 6 * 3600
USER_AGENT = "job-search-agent (personal job search; contact: set JOBSEARCH_CONTACT)"

REGISTRY: dict[str, Callable[..., list[dict[str, Any]]]] = {}


def source(name: str):
    def wrap(fn):
        REGISTRY[name] = fn
        return fn

    return wrap


def fetch_json(url: str, *, ttl: int = CACHE_TTL) -> Any:
    """GET with a 6-hour disk cache and a polite backoff on 429."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = urllib.parse.quote(url, safe="")[:180]
    cached = CACHE_DIR / f"{key}.json"
    if cached.exists() and time.time() - cached.stat().st_mtime < ttl:
        return json.loads(cached.read_text())

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            cached.write_text(json.dumps(data))
            return data
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503) and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            raise
    return None


def _iso(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds")
    return str(value)


@source("greenhouse")
def greenhouse(board: str, **_) -> list[dict[str, Any]]:
    """board = the company's Greenhouse board token, e.g. 'stripe'."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    data = fetch_json(url) or {}
    out = []
    for j in data.get("jobs", []):
        out.append({
            "source": f"greenhouse:{board}",
            "external_id": str(j.get("id")),
            "title": j.get("title", ""),
            "company": board,
            "location": (j.get("location") or {}).get("name"),
            "remote": None,
            "url": j.get("absolute_url"),
            "description": _html_to_text(j.get("content", "")),
            "salary_raw": None,
            "posted_at": _iso(j.get("updated_at")),
        })
    return out


@source("lever")
def lever(company: str, **_) -> list[dict[str, Any]]:
    url = f"https://api.lever.co/v0/postings/{company}?mode=json"
    data = fetch_json(url) or []
    out = []
    for j in data:
        cats = j.get("categories") or {}
        out.append({
            "source": f"lever:{company}",
            "external_id": j.get("id"),
            "title": j.get("text", ""),
            "company": company,
            "location": cats.get("location"),
            "remote": cats.get("commitment"),
            "url": j.get("hostedUrl"),
            "description": _html_to_text(j.get("descriptionPlain") or j.get("description", "")),
            "salary_raw": None,
            "posted_at": _iso((j.get("createdAt") or 0) / 1000 or None),
        })
    return out


@source("ashby")
def ashby(company: str, **_) -> list[dict[str, Any]]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true"
    data = fetch_json(url) or {}
    out = []
    for j in data.get("jobs", []):
        comp = j.get("compensation") or {}
        out.append({
            "source": f"ashby:{company}",
            "external_id": j.get("id"),
            "title": j.get("title", ""),
            "company": company,
            "location": j.get("location"),
            "remote": "remote" if j.get("isRemote") else None,
            "url": j.get("jobUrl"),
            "description": _html_to_text(j.get("descriptionPlain") or ""),
            "salary_raw": comp.get("compensationTierSummary"),
            "posted_at": _iso(j.get("publishedAt")),
        })
    return out


@source("remoteok")
def remoteok(**_) -> list[dict[str, Any]]:
    data = fetch_json("https://remoteok.com/api") or []
    out = []
    for j in data[1:]:  # first element is the licence notice
        out.append({
            "source": "remoteok",
            "external_id": str(j.get("id")),
            "title": j.get("position", ""),
            "company": j.get("company", ""),
            "location": j.get("location") or "Remote",
            "remote": "remote",
            "url": j.get("url"),
            "description": _html_to_text(j.get("description", "")),
            "salary_raw": j.get("salary"),
            "posted_at": j.get("date"),
        })
    return out


@source("fixtures")
def fixtures(path: str = "agent/fixtures/jobs.json", **_) -> list[dict[str, Any]]:
    """Offline source used by --dry-run so the pipeline runs with no network."""
    root = Path(__file__).resolve().parents[2]
    return json.loads((root / path).read_text())


def _html_to_text(html: str) -> str:
    import html as html_mod
    import re

    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</li>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_mod.unescape(text)
    return re.sub(r"[ \t]+", " ", text).strip()


def collect(enabled: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Run each configured source; a broken source never kills the run."""
    results = []
    for cfg in enabled:
        name = cfg.get("type")
        fn = REGISTRY.get(name)
        if not fn:
            print(f"  ! unknown source type: {name}")
            continue
        args = {k: v for k, v in cfg.items() if k != "type"}
        label = cfg.get("board") or cfg.get("company") or name
        try:
            jobs = fn(**args)
        except Exception as exc:
            print(f"  ! {name}:{label} failed — {exc}")
            jobs = []
        results.append((f"{name}:{label}", jobs))
    return results
