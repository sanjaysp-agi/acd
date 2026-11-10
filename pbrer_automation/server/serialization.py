"""Shared JSON serialization for pipeline-result fields returned by the API.

Every heavy value in a `run_full_pipeline`/`pipeline_result` dict is already
a Pydantic model (or a list of them) -- see `models/schemas.py` -- so this
is just dispatch on `.model_dump(mode="json")`, not a hand-rolled DTO layer.
"""
from __future__ import annotations

from typing import Any


def to_json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [to_json(v) for v in value]
    return value


def result_to_json(result: dict[str, Any]) -> dict[str, Any]:
    """Converts a full pipeline-result dict to a JSON-safe dict, stripping
    `_excel_dir` (a server-local filesystem path, never for the client)."""
    out: dict[str, Any] = {}
    for key, value in result.items():
        if key.startswith("_"):
            continue
        out[key] = str(value) if key == "generated_at" else to_json(value)
    return out
