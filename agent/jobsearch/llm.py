"""Thin Claude wrapper.

Every call goes through `json_call`, which returns a dict. When the agent runs
with --dry-run (or without ANTHROPIC_API_KEY), the caller's `mock` value is
returned instead, so the whole pipeline is runnable offline against fixtures.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

MODEL_FAST = os.environ.get("JOBSEARCH_MODEL_FAST", "claude-haiku-4-5-20251001")
MODEL_MAIN = os.environ.get("JOBSEARCH_MODEL_MAIN", "claude-sonnet-5")

_clients: dict[str, Any] = {}
_offline = False

# The CLI uses one key from the environment. The SaaS runs each user's work
# under their own key, so it lives in a ContextVar rather than a global.
_api_key: ContextVar[str | None] = ContextVar("anthropic_api_key", default=None)


def set_offline(value: bool) -> None:
    """Force mock responses (used by --dry-run)."""
    global _offline
    _offline = value


@contextmanager
def use_key(key: str | None):
    """Run a block with one user's API key."""
    token = _api_key.set(key)
    try:
        yield
    finally:
        _api_key.reset(token)


def current_key() -> str | None:
    return _api_key.get() or os.environ.get("ANTHROPIC_API_KEY") or None


def available() -> bool:
    return not _offline and bool(current_key())


def _get_client():
    key = current_key()
    if key not in _clients:
        from anthropic import Anthropic  # imported lazily so --dry-run needs no deps

        _clients[key] = Anthropic(api_key=key)
    return _clients[key]


def json_call(
    system: str,
    prompt: str,
    mock: Any,
    *,
    model: str = MODEL_FAST,
    max_tokens: int = 2000,
    retries: int = 3,
) -> Any:
    """Ask Claude for JSON. Returns `mock` when running offline."""
    if not available():
        return mock

    system = system.rstrip() + "\n\nRespond with a single JSON value and nothing else."
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            resp = _get_client().messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            return json.loads(_strip_fence(text))
        except Exception as exc:  # network, rate limit, or bad JSON
            last_error = exc
            time.sleep(2**attempt)
    raise RuntimeError(f"Claude call failed after {retries} attempts: {last_error}")


def text_call(
    system: str,
    prompt: str,
    mock: str,
    *,
    model: str = MODEL_MAIN,
    max_tokens: int = 2000,
) -> str:
    """Same contract as json_call, for prose (resumes, letters, messages)."""
    if not available():
        return mock
    resp = _get_client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def _strip_fence(text: str) -> str:
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[: -3]
    return text.strip()
