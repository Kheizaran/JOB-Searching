"""Whose files are we working on right now?

The CLI has one workspace: the repo itself. The SaaS has one per user. Every
path in the pipeline resolves through here, so the same modules serve both —
`with workspace(path):` is the only difference between them.

A ContextVar rather than a global: concurrent requests each keep their own.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_current: ContextVar[Path | None] = ContextVar("workspace", default=None)


def current() -> Path:
    """The workspace in force — the repo root unless one has been set."""
    return _current.get() or ROOT


@contextmanager
def workspace(path: Path | str):
    """Run a block against one user's files."""
    path = Path(path)
    (path / "config").mkdir(parents=True, exist_ok=True)
    token = _current.set(path)
    try:
        yield path
    finally:
        _current.reset(token)


def config_dir() -> Path:
    """Where resume.md, preferences.json and snippets.json live."""
    ws = current()
    return ws / "agent" / "config" if ws == ROOT else ws / "config"


def data_dir() -> Path:
    ws = current()
    return ws / "data" if ws == ROOT else ws / "data"


def applications_dir() -> Path:
    return data_dir() / "applications"


def digests_dir() -> Path:
    return data_dir() / "digests"


def logs_dir() -> Path:
    return data_dir() / "logs"


def tracker_path() -> Path:
    return data_dir() / "tracker.db"
