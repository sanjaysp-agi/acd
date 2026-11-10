"""Agent Execution & Traceability page support -- reads real persisted
tool-call events, never simulated (same guarantee the old Streamlit page
made). Trace events live in their own per-run JSONL, independent of the
pipeline-result JSON (`observability/trace_store.py`)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from observability.trace_store import TraceStore

router = APIRouter(prefix="/api/runs", tags=["trace"])


@router.get("/{run_id}/trace")
def get_trace(run_id: str) -> list[dict[str, Any]]:
    return TraceStore().load_run(run_id)
