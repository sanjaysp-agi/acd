"""Generates (idempotently, on request) and streams the Results & Exports
download artifacts: the business-facing XLSX and DOCX reports, plus a single
zipped "audit package" bundling every supporting evidence file for a
regulatory reviewer who needs the full trail in one download."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from config.settings import OUTPUT_DIR
from generation.audit_generator import generate_audit_workbook
from generation.docx_generator import generate_docx_report
from generation.excel_generator import generate_results_workbook
from generation.report_generator import generate_benchmark_workbook, generate_report_ready_output
from observability import comment_store, run_store
from observability.trace_store import TraceStore
from server.serialization import result_to_json

router = APIRouter(prefix="/api/runs", tags=["downloads"])

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_ZIP_MIME = "application/zip"

_XLSX_ARTIFACTS = {
    "calculation-results": ("calculation_results.xlsx",
                              lambda result, path: generate_results_workbook(result["metric_results"], path)),
    "audit-trail": ("audit_trail.xlsx",
                      lambda result, path: generate_audit_workbook(
                          result["metric_results"], path, result.get("ai_score_report"))),
    "report-ready": ("section_16_3_figures.xlsx",
                       lambda result, path: generate_report_ready_output(result["metric_results"], path)),
    "benchmark-comparison": ("benchmark_comparison.xlsx",
                               lambda result, path: generate_benchmark_workbook(result["benchmark_report"], path)),
}


def _build_audit_package(run_id: str, result: dict, run_output_dir: Path) -> Path:
    for key, (filename, generator) in _XLSX_ARTIFACTS.items():
        generator(result, run_output_dir / filename)

    (run_output_dir / "trace.json").write_text(
        json.dumps(TraceStore().load_run(run_id), indent=2, default=str), encoding="utf-8",
    )
    (run_output_dir / "validation_report.json").write_text(
        json.dumps(result_to_json(result).get("validation_report"), indent=2, default=str), encoding="utf-8",
    )
    # AI Score Validation Agent output (runs AFTER the validation report
    # above -- see pipeline.run_ai_scoring) -- bundled as its own file so a
    # reviewer can see every metric's confidence score and citation
    # independently of the (already-embedded) audit_trail.xlsx columns.
    (run_output_dir / "ai_score_report.json").write_text(
        json.dumps(result_to_json(result).get("ai_score_report"), indent=2, default=str), encoding="utf-8",
    )
    (run_output_dir / "comments.json").write_text(
        json.dumps(comment_store.list_comments(run_id), indent=2, default=str), encoding="utf-8",
    )

    zip_path = run_output_dir / "audit_package.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for key, (filename, _) in _XLSX_ARTIFACTS.items():
            zf.write(run_output_dir / filename, filename)
        for filename in ("trace.json", "validation_report.json", "ai_score_report.json", "comments.json"):
            zf.write(run_output_dir / filename, filename)
    return zip_path


_ARTIFACTS = {
    **_XLSX_ARTIFACTS,
    "docx-report": ("section_16_3_report.docx",
                      lambda result, path: generate_docx_report(result["metric_results"], path)),
}


@router.get("/{run_id}/downloads/{artifact}")
def download_artifact(run_id: str, artifact: str) -> FileResponse:
    if artifact != "audit-package" and artifact not in _ARTIFACTS:
        raise HTTPException(404, f"Unknown artifact: {artifact}. Valid options: {sorted(_ARTIFACTS)}, audit-package")

    result = run_store.load_result(run_id)
    if result is None:
        raise HTTPException(404, f"No completed run found for run_id: {run_id}")

    run_output_dir: Path = OUTPUT_DIR / run_id
    run_output_dir.mkdir(parents=True, exist_ok=True)

    if artifact == "audit-package":
        zip_path = _build_audit_package(run_id, result, run_output_dir)
        return FileResponse(zip_path, media_type=_ZIP_MIME, filename="audit_package.zip")

    filename, generator = _ARTIFACTS[artifact]
    output_path = run_output_dir / filename
    generator(result, output_path)
    mime = _DOCX_MIME if filename.endswith(".docx") else _XLSX_MIME
    return FileResponse(output_path, media_type=mime, filename=filename)
