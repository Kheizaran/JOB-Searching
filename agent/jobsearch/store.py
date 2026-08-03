"""SQLite tracker: jobs, applications, contacts, messages.

Idempotent by design — a job's primary key is a hash of (source, external_id),
so re-running the scraper updates rows instead of duplicating them.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .workspace import tracker_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  external_id TEXT,
  title TEXT NOT NULL,
  company TEXT NOT NULL,
  location TEXT,
  remote TEXT,
  url TEXT,
  description TEXT,
  salary_raw TEXT,
  posted_at TEXT,
  first_seen TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'new',
  score INTEGER,
  analysis TEXT
);
CREATE TABLE IF NOT EXISTS applications (
  job_id TEXT PRIMARY KEY REFERENCES jobs(id),
  status TEXT NOT NULL DEFAULT 'approved',
  folder TEXT,
  approved_by TEXT,
  approved_at TEXT,
  submitted_at TEXT,
  portal TEXT,
  confirmation TEXT,
  referral_source TEXT,
  last_followup_at TEXT,
  followup_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS contacts (
  id TEXT PRIMARY KEY,
  job_id TEXT REFERENCES jobs(id),
  name TEXT,
  title TEXT,
  company TEXT,
  profile_url TEXT,
  source TEXT,
  hooks TEXT,
  status TEXT NOT NULL DEFAULT 'candidate',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  contact_id TEXT REFERENCES contacts(id),
  job_id TEXT REFERENCES jobs(id),
  channel TEXT,
  body TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  created_at TEXT NOT NULL,
  sent_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score DESC);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def job_id(source: str, external_id: str) -> str:
    return hashlib.sha256(f"{source}:{external_id}".encode()).hexdigest()[:16]


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or tracker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert_job(conn: sqlite3.Connection, job: dict[str, Any]) -> tuple[str, bool]:
    """Insert a scraped job. Returns (id, is_new)."""
    jid = job_id(job["source"], job.get("external_id") or job["url"])
    existing = conn.execute("SELECT id FROM jobs WHERE id = ?", (jid,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE jobs SET title=?, company=?, location=?, remote=?, url=?, "
            "description=?, salary_raw=?, posted_at=? WHERE id=?",
            (
                job["title"], job["company"], job.get("location"), job.get("remote"),
                job.get("url"), job.get("description"), job.get("salary_raw"),
                job.get("posted_at"), jid,
            ),
        )
        conn.commit()
        return jid, False

    conn.execute(
        "INSERT INTO jobs (id, source, external_id, title, company, location, remote, "
        "url, description, salary_raw, posted_at, first_seen) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            jid, job["source"], job.get("external_id"), job["title"], job["company"],
            job.get("location"), job.get("remote"), job.get("url"),
            job.get("description"), job.get("salary_raw"), job.get("posted_at"), now(),
        ),
    )
    conn.commit()
    return jid, True


def set_status(conn: sqlite3.Connection, jid: str, status: str) -> None:
    conn.execute("UPDATE jobs SET status=? WHERE id=?", (status, jid))
    conn.commit()


def save_analysis(conn: sqlite3.Connection, jid: str, score: int, analysis: dict) -> None:
    conn.execute(
        "UPDATE jobs SET score=?, analysis=?, status=? WHERE id=?",
        (score, json.dumps(analysis, ensure_ascii=False), "scored", jid),
    )
    conn.commit()


def by_status(conn: sqlite3.Connection, status: str | Iterable[str]) -> list[sqlite3.Row]:
    statuses = [status] if isinstance(status, str) else list(status)
    marks = ",".join("?" * len(statuses))
    return conn.execute(
        f"SELECT * FROM jobs WHERE status IN ({marks}) ORDER BY score DESC NULLS LAST, first_seen DESC",
        statuses,
    ).fetchall()


def get_job(conn: sqlite3.Connection, jid: str) -> sqlite3.Row | None:
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone()
    if row:
        return row
    # allow short prefixes on the CLI
    return conn.execute("SELECT * FROM jobs WHERE id LIKE ?", (jid + "%",)).fetchone()


def upsert_application(conn: sqlite3.Connection, jid: str, **fields: Any) -> None:
    conn.execute("INSERT OR IGNORE INTO applications (job_id) VALUES (?)", (jid,))
    if fields:
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(
            f"UPDATE applications SET {sets} WHERE job_id=?", (*fields.values(), jid)
        )
    conn.commit()


def add_contact(conn: sqlite3.Connection, contact: dict[str, Any]) -> str:
    cid = hashlib.sha256(
        f"{contact.get('job_id')}:{contact.get('name')}:{contact.get('profile_url')}".encode()
    ).hexdigest()[:16]
    conn.execute(
        "INSERT OR REPLACE INTO contacts (id, job_id, name, title, company, profile_url, "
        "source, hooks, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            cid, contact.get("job_id"), contact.get("name"), contact.get("title"),
            contact.get("company"), contact.get("profile_url"), contact.get("source"),
            json.dumps(contact.get("hooks", []), ensure_ascii=False),
            contact.get("status", "candidate"), now(),
        ),
    )
    conn.commit()
    return cid


def add_message(conn: sqlite3.Connection, contact_id: str, jid: str, channel: str, body: str) -> int:
    cur = conn.execute(
        "INSERT INTO messages (contact_id, job_id, channel, body, status, created_at) "
        "VALUES (?,?,?,?, 'draft', ?)",
        (contact_id, jid, channel, body, now()),
    )
    conn.commit()
    return cur.lastrowid


def set_contact_status(conn: sqlite3.Connection, contact_id: str, status: str) -> sqlite3.Row | None:
    contact = conn.execute(
        "SELECT * FROM contacts WHERE id LIKE ?", (contact_id + "%",)
    ).fetchone()
    if not contact:
        return None
    conn.execute("UPDATE contacts SET status=? WHERE id=?", (status, contact["id"]))
    if status == "messaged":
        conn.execute(
            "UPDATE messages SET status='sent', sent_at=? WHERE contact_id=? AND status='draft'",
            (now(), contact["id"]),
        )
    conn.commit()
    return contact


def recent_contact_conflict(conn: sqlite3.Connection, name: str, job_id: str, days: int) -> str | None:
    """Has this person already been messaged about a different role recently?"""
    if not name:
        return None
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    row = conn.execute(
        "SELECT m.created_at, j.title FROM messages m "
        "JOIN contacts c ON c.id = m.contact_id LEFT JOIN jobs j ON j.id = m.job_id "
        "WHERE c.name = ? AND m.job_id != ? AND m.created_at > ? LIMIT 1",
        (name, job_id, cutoff),
    ).fetchone()
    return f"{row['title']} on {row['created_at'][:10]}" if row else None


def status_report(conn: sqlite3.Connection) -> str:
    lines = [f"Pipeline — {date.today().isoformat()}", "-" * 34]
    rows = conn.execute(
        "SELECT status, COUNT(*) n FROM jobs GROUP BY status ORDER BY n DESC"
    ).fetchall()
    for r in rows:
        lines.append(f"  jobs.{r['status']:<12} {r['n']:>4}")
    rows = conn.execute(
        "SELECT status, COUNT(*) n FROM applications GROUP BY status ORDER BY n DESC"
    ).fetchall()
    for r in rows:
        lines.append(f"  apps.{r['status']:<12} {r['n']:>4}")
    n_contacts = conn.execute("SELECT COUNT(*) n FROM contacts").fetchone()["n"]
    n_drafts = conn.execute(
        "SELECT COUNT(*) n FROM messages WHERE status='draft'"
    ).fetchone()["n"]
    lines.append(f"  contacts{'':<9} {n_contacts:>4}")
    lines.append(f"  messages.draft{'':<3} {n_drafts:>4}")
    return "\n".join(lines)


if __name__ == "__main__":
    with connect() as conn:
        print(status_report(conn))
