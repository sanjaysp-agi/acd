"""
Generates run IDs and orchestrates a full pipeline run with tracing
wired in, persisting the stage outputs so the frontend's Results/
Validation/Downloads pages can reload a previous run without re-running
the pipeline.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from config.settings import RUNS_DIR
from observability.trace_store import TraceStore
from pipeline import run_full_pipeline


def new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


def execute_run(docx_path: str, excel_dir: str, reporting_start: str, reporting_end: str) -> dict[str, Any]:
    run_id = new_run_id()
    trace_store = TraceStore()
    sink = trace_store.make_sink(run_id)

    result = run_full_pipeline(run_id, docx_path, excel_dir, reporting_start, reporting_end, trace_sink=sink)
    _persist_summary(run_id, result)
    return result


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
