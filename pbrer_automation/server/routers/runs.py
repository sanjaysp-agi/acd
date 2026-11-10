"""Create/list/inspect pipeline runs, plus the live SSE progress stream.

Replaces `frontend/pages/upload.py` (create a run) and the implicit "is
there a run yet" check every other Streamlit page used to do via
`frontend.state`.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from observability import run_manager, run_store
from server.serialization import result_to_json

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("")
async def create_run(
    docx_file: UploadFile,
    excel_files: list[UploadFile],
    reporting_start: str = Form(...),
    reporting_end: str = Form(...),
) -> dict[str, str]:
    if not docx_file or not excel_files:
        raise HTTPException(400, "Both the PBRER document and at least one Excel export are required.")

    run_id = run_manager.new_run_id()
    docx_bytes = await docx_file.read()
    excel_payload = [(f.filename, await f.read()) for f in excel_files]

    docx_path, excel_dir = await run_in_threadpool(
        run_manager.save_uploads, run_id, docx_file.filename, docx_bytes, excel_payload,
    )
    await run_in_threadpool(
        run_manager.start_run_async, run_id, docx_path, excel_dir, reporting_start, reporting_end,
    )
    return {"run_id": run_id}


@router.get("")
def list_runs() -> list[dict[str, Any]]:
    return run_manager.list_past_runs()


@router.get("/{run_id}/status")
def run_status(run_id: str) -> dict[str, Any]:
    status = run_manager.get_run_status(run_id)
    if status is None:
        raise HTTPException(404, f"Unknown run_id: {run_id}")
    return status


@router.get("/{run_id}/events")
async def run_events(run_id: str) -> StreamingResponse:
    """Server-Sent Events stream of live trace events for a run that is
    still executing. The browser's built-in `EventSource` consumes this
    directly -- no client library needed."""
    q = run_manager.get_run_queue(run_id)
    if q is None:
        raise HTTPException(404, f"No live event stream for run_id: {run_id} (already finished or never started).")

    async def event_generator():
        while True:
            item = await run_in_threadpool(q.get)
            if item is None:
                break
            yield f"data: {json.dumps(item, default=str)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    result = run_store.load_result(run_id)
    if result is None:
        raise HTTPException(404, f"No completed run found for run_id: {run_id}")
    return result_to_json(result)
