"""Persists reviewer comments left against a generated Section 16.3 table
during Review & Validation, keyed by run_id -- same `{run_id}/*.json` per-run
file layout as `run_store.py`, so a reviewer's notes survive a page reload
and are visible to any later reviewer who opens that run (prompt.md's
regulatory-audit-visibility intent extends to the review workflow itself,
not just the calculation evidence)."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config.settings import RUNS_DIR


def _comments_path(run_id: str) -> Path:
    d = RUNS_DIR / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d / "comments.json"


def list_comments(run_id: str) -> list[dict[str, Any]]:
    path = _comments_path(run_id)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def add_comment(run_id: str, table_id: str, author: str, text: str) -> dict[str, Any]:
    comments = list_comments(run_id)
    comment = {
        "id": uuid.uuid4().hex,
        "table_id": table_id,
        "author": author or "Reviewer",
        "text": text,
        "created_at": datetime.now(UTC).isoformat(),
    }
    comments.append(comment)
    _comments_path(run_id).write_text(json.dumps(comments, indent=2), encoding="utf-8")
    return comment
