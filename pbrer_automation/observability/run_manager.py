"""
Generates run IDs, saves uploaded inputs to a stable per-run directory,
and orchestrates a full pipeline run with tracing wired in -- both to the
persisted JSONL trace (`TraceStore`) and to a live in-memory queue so an
HTTP server can stream progress over Server-Sent Events while the run
(3-5 minutes for large exports) is still in flight.

Full stage output is persisted via `run_store.save_result` so the
frontend's pages can reload a run without the pipeline still being "warm"
in this process.
"""
from __future__ import annotations

import json
import queue
import threading
import uuid
from pathlib import Path
from typing import Any

from config.settings import RUNS_DIR
from observability import run_store
from observability.trace_store import TraceStore
from pipeline import run_full_pipeline

# In-memory bookkeeping for runs started in THIS process. Durable state
# (the full result, the trace JSONL, the summary) lives on disk via
# run_store/TraceStore and survives a restart; this dict only needs to
# survive long enough to serve the live SSE stream and status poll for a
# run that's currently executing.
_RUN_STATUS: dict[str, dict[str, Any]] = {}
_RUN_QUEUES: dict[str, "queue.Queue"] = {}
_LOCK = threading.Lock()

_MAX_SAFE_PATH_LEN = 240  # Windows MAX_PATH (260) minus headroom for long CSMR export names.


def new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


def _safe_filename(directory: Path, name: str) -> str:
    """Shortens a filename if directory/name would risk exceeding Windows
    MAX_PATH (reported as FileNotFoundError, not a path-length error)."""
    candidate_len = len(str(directory / name))
    if candidate_len <= _MAX_SAFE_PATH_LEN:
        return name
    stem, ext = Path(name).stem, Path(name).suffix
    overflow = candidate_len - _MAX_SAFE_PATH_LEN
    truncated_stem = stem[: max(10, len(stem) - overflow)]
    return f"{truncated_stem}{ext}"


def save_uploads(run_id: str, docx_name: str, docx_bytes: bytes,
                  excel_files: list[tuple[str, bytes]]) -> tuple[str, str]:
    """Saves the uploaded docx + excel files under a stable, per-run
    directory (not a throwaway OS temp dir) so a later topic-mapping
    recompute can still find them. Returns (docx_path, excel_dir)."""
    input_dir = RUNS_DIR / run_id / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    docx_path = input_dir / _safe_filename(input_dir, docx_name)
    docx_path.write_bytes(docx_bytes)

    for name, data in excel_files:
        (input_dir / _safe_filename(input_dir, name)).write_bytes(data)

    return str(docx_path), str(input_dir)


def start_run_async(run_id: str, docx_path: str, excel_dir: str, reporting_start: str, reporting_end: str) -> None:
    """Kicks off `run_full_pipeline` on a background thread for an
    already-allocated `run_id` (see `new_run_id` / `save_uploads`, which
    need the id up front to know where to save the input files), so the
    HTTP request that triggered it doesn't block for the full 3-5 minute
    run."""
    q: "queue.Queue" = queue.Queue()
    with _LOCK:
        _RUN_QUEUES[run_id] = q
        _RUN_STATUS[run_id] = {"status": "running", "error": None}

    trace_store = TraceStore()
    jsonl_sink = trace_store.make_sink(run_id)

    def live_sink(event: dict[str, Any]) -> None:
        jsonl_sink(event)
        q.put(event)

    def worker() -> None:
        try:
            result = run_full_pipeline(run_id, docx_path, excel_dir, reporting_start, reporting_end,
                                        trace_sink=live_sink)
            run_store.save_result(run_id, result)
            _persist_summary(run_id, result)
            with _LOCK:
                _RUN_STATUS[run_id] = {"status": "completed", "error": None}
            q.put({"event_type": "run_completed", "run_id": run_id})
        except Exception as exc:  # noqa: BLE001 -- surfaced to the client via status, not swallowed
            with _LOCK:
                _RUN_STATUS[run_id] = {"status": "failed", "error": str(exc)}
            q.put({"event_type": "run_failed", "run_id": run_id, "message": str(exc)})
        finally:
            q.put(None)  # sentinel: closes any SSE stream currently reading this queue
            with _LOCK:
                # Drop the queue so a LATER /events request for this now-finished
                # run_id gets a clean 404 (-> client falls back to /status) instead
                # of blocking forever on a queue nothing will ever write to again.
                # Any consumer already iterating keeps its own reference to `q`
                # and still receives the sentinel above.
                _RUN_QUEUES.pop(run_id, None)

    threading.Thread(target=worker, daemon=True).start()


def get_run_status(run_id: str) -> dict[str, Any] | None:
    with _LOCK:
        status = _RUN_STATUS.get(run_id)
    if status is not None:
        return status
    # Process restarted (or a different worker handled the run) -- fall
    # back to what's durable on disk.
    if run_store.has_result(run_id):
        return {"status": "completed", "error": None}
    return None


def get_run_queue(run_id: str) -> "queue.Queue | None":
    with _LOCK:
        return _RUN_QUEUES.get(run_id)


def _persist_summary(run_id: str, result: dict[str, Any]) -> None:
    path = RUNS_DIR / f"{run_id}_summary.json"
    summary = {
        "run_id": run_id,
        "generated_at": str(result["generated_at"]),
        "topics_found": len(result["document_structure"].topics),
        "workbooks_found": len(result["workbook_inventory"].workbooks),
        "topics_mapped": sum(1 for m in result["topic_mapping"].mappings if m.case_workbook),
        "metrics_calculated": len(result["metric_results"]),
        "benchmark_matches": sum(1 for r in result["benchmark_report"].rows if r.status == "match"),
        "benchmark_mismatches": sum(1 for r in result["benchmark_report"].rows if r.status == "mismatch"),
        "benchmark_unverified": sum(1 for r in result["benchmark_report"].rows if r.status == "unverified"),
    }
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def list_past_runs() -> list[dict[str, Any]]:
    out = []
    for path in sorted(RUNS_DIR.glob("*_summary.json"), reverse=True):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return out
