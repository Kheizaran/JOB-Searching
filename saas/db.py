"""The control plane: accounts, sessions, keys, run history.

Deliberately separate from each user's tracker. This database knows who exists;
their jobs, applications and messages live in their own workspace, one SQLite
file per user, so deleting an account is a row plus a directory.

SQLite here is a starting point, not a decision — the schema is ordinary SQL and
moves to Postgres when concurrent writes start to hurt (a few hundred users).
"""

from __future__ import annotations

import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("SAAS_DB", ROOT / "data" / "saas" / "control.db"))
WORKSPACES = Path(os.environ.get("SAAS_WORKSPACES", ROOT / "data" / "saas" / "workspaces"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  api_key_enc TEXT,
  onboarded_at TEXT,
  daily_enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  last_run_at TEXT,
  last_run_status TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_runs_user ON runs(user_id, started_at DESC);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def workspace_for(user_id: str) -> Path:
    path = WORKSPACES / user_id
    (path / "config").mkdir(parents=True, exist_ok=True)
    return path


def create_user(conn: sqlite3.Connection, email: str, password_hash: str) -> str:
    user_id = secrets.token_hex(8)
    conn.execute(
        "INSERT INTO users (id, email, password_hash, created_at) VALUES (?,?,?,?)",
        (user_id, email.strip().lower(), password_hash, now()),
    )
    conn.commit()
    workspace_for(user_id)
    return user_id


def user_by_email(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
    ).fetchone()


def user_by_id(conn: sqlite3.Connection, user_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def update_user(conn: sqlite3.Connection, user_id: str, **fields) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE users SET {sets} WHERE id=?", (*fields.values(), user_id))
    conn.commit()


def start_run(conn: sqlite3.Connection, user_id: str) -> int:
    cur = conn.execute(
        "INSERT INTO runs (user_id, started_at, status) VALUES (?,?, 'running')",
        (user_id, now()),
    )
    conn.commit()
    return cur.lastrowid


def finish_run(conn: sqlite3.Connection, run_id: int, user_id: str, status: str, detail: str) -> None:
    conn.execute(
        "UPDATE runs SET finished_at=?, status=?, detail=? WHERE id=?",
        (now(), status, detail[:2000], run_id),
    )
    conn.execute(
        "UPDATE users SET last_run_at=?, last_run_status=? WHERE id=?", (now(), status, user_id)
    )
    conn.commit()


def recent_runs(conn: sqlite3.Connection, user_id: str, limit: int = 5) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM runs WHERE user_id = ? ORDER BY started_at DESC LIMIT ?", (user_id, limit)
    ).fetchall()


def delete_user(conn: sqlite3.Connection, user_id: str) -> None:
    """Account deletion means the row and every file. No soft delete: we are
    holding someone's CV, and 'deleted' has to mean deleted."""
    import shutil

    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    shutil.rmtree(WORKSPACES / user_id, ignore_errors=True)
