"""Generates (idempotently, on request) and streams the 4 output xlsx
workbooks the old Downloads page produced on every render. Same generator
functions, same filenames, same `OUTPUT_DIR/{run_id}/` location."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from config.settings import OUTPUT_DIR
from generation.audit_generator import generate_audit_workbook
from generation.excel_generator import generate_results_workbook
from generation.report_generator import generate_benchmark_workbook, generate_report_ready_output
from observability import run_store

router = APIRouter(prefix="/api/runs", tags=["downloads"])

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_ARTIFACTS = {
    "calculation-results": ("calculation_results.xlsx",
                              lambda result, path: generate_results_workbook(result["metric_results"], path)),
    "audit-trail": ("audit_trail.xlsx",
                      lambda result, path: generate_audit_workbook(result["metric_results"], path)),
    "report-ready": ("section_16_3_figures.xlsx",
                       lambda result, path: generate_report_ready_output(result["metric_results"], path)),
    "benchmark-comparison": ("benchmark_comparison.xlsx",
                               lambda result, path: generate_benchmark_workbook(result["benchmark_report"], path)),
}


@router.get("/{run_id}/downloads/{artifact}")
def download_artifact(run_id: str, artifact: str) -> FileResponse:
    if artifact not in _ARTIFACTS:
        raise HTTPException(404, f"Unknown artifact: {artifact}. Valid options: {sorted(_ARTIFACTS)}")

    result = run_store.load_result(run_id)
    if result is None:
        raise HTTPException(404, f"No completed run found for run_id: {run_id}")

    filename, generator = _ARTIFACTS[artifact]
    run_output_dir: Path = OUTPUT_DIR / run_id
    run_output_dir.mkdir(parents=True, exist_ok=True)
    output_path = run_output_dir / filename

    generator(result, output_path)
    return FileResponse(output_path, media_type=_XLSX_MIME, filename=filename)
