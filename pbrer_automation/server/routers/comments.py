"""Reviewer comments against a generated Section 16.3 table (Review &
Validation's right-rail "Reviewer Comments" tab). See
observability/comment_store.py for the persistence layer."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from observability import comment_store, run_store

router = APIRouter(prefix="/api/runs", tags=["comments"])


@router.get("/{run_id}/comments")
def list_comments(run_id: str) -> list[dict[str, Any]]:
    if run_store.load_result(run_id) is None:
        raise HTTPException(404, f"No completed run found for run_id: {run_id}")
    return comment_store.list_comments(run_id)


@router.post("/{run_id}/comments")
def create_comment(
    run_id: str,
    table_id: str = Body(...),
    author: str = Body(""),
    text: str = Body(...),
) -> dict[str, Any]:
    if run_store.load_result(run_id) is None:
        raise HTTPException(404, f"No completed run found for run_id: {run_id}")
    if not text.strip():
        raise HTTPException(400, "Comment text must not be empty.")
    return comment_store.add_comment(run_id, table_id, author, text)
