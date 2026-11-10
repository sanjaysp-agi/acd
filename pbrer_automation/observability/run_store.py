"""Persists a full pipeline run result (every stage's Pydantic output) to
disk, keyed by run_id, and rehydrates it back into typed models.

Previously only a thin summary JSON (`{run_id}_summary.json`) was written --
the full result lived only in the calling process's memory (the Streamlit
session). A stateless HTTP API needs the full result to survive across
requests (and process restarts), so every page-equivalent endpoint can load
it with `load_result(run_id)` instead of needing the pipeline to still be
"warm" somewhere.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.settings import RUNS_DIR
from models.schemas import (
    BenchmarkReport,
    DocumentStructure,
    ExecutionPlan,
    MetricResult,
    TopicMappingResult,
    TopicReconstructionResult,
    ValidationReport,
    WorkbookInventory,
)

# Single-model fields vs. list-of-model fields -- everything else in the
# result dict (run_id, generated_at, _excel_dir) is already a plain
# JSON-safe scalar.
_MODEL_FIELDS = {
    "document_structure": DocumentStructure,
    "workbook_inventory": WorkbookInventory,
    "topic_mapping": TopicMappingResult,
    "execution_plan": ExecutionPlan,
    "benchmark_report": BenchmarkReport,
    "validation_report": ValidationReport,
}
_LIST_MODEL_FIELDS = {
    "metric_results": MetricResult,
    "topic_reconstruction": TopicReconstructionResult,
}


def _run_dir(run_id: str) -> Path:
    d = RUNS_DIR / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def result_path(run_id: str) -> Path:
    return _run_dir(run_id) / "result.json"


def save_result(run_id: str, result: dict[str, Any]) -> None:
    serialized: dict[str, Any] = {}
    for key, value in result.items():
        if key in _MODEL_FIELDS:
            serialized[key] = value.model_dump(mode="json")
        elif key in _LIST_MODEL_FIELDS:
            serialized[key] = [v.model_dump(mode="json") for v in value]
        else:
            serialized[key] = value if key != "generated_at" else str(value)
    result_path(run_id).write_text(json.dumps(serialized, indent=2), encoding="utf-8")


def load_result(run_id: str) -> dict[str, Any] | None:
    path = result_path(run_id)
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, Any] = {}
    for key, value in raw.items():
        if key in _MODEL_FIELDS:
            result[key] = _MODEL_FIELDS[key].model_validate(value)
        elif key in _LIST_MODEL_FIELDS:
            model = _LIST_MODEL_FIELDS[key]
            result[key] = [model.model_validate(v) for v in value]
        else:
            result[key] = value
    return result


def has_result(run_id: str) -> bool:
    return result_path(run_id).exists()
