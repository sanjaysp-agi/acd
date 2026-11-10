"""Manual topic<->workbook correction/approval (prompt.md line 881).
Mirrors the old Streamlit Topic Mapping page's "Apply corrections and
re-run calculations" button exactly -- same row-order zip against the
stored mapping, same recompute call, now `pipeline.recompute_from_topic_mapping`
instead of a page-local function."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from models.schemas import TopicMappingEntry, TopicMappingResult
from observability import run_store
from pipeline import recompute_from_topic_mapping
from server.serialization import result_to_json

router = APIRouter(prefix="/api/runs", tags=["topic-mapping"])


@router.post("/{run_id}/topic-mapping/recompute")
def recompute(run_id: str, rows: list[dict[str, Any]] = Body(..., embed=True)) -> dict[str, Any]:
    result = run_store.load_result(run_id)
    if result is None:
        raise HTTPException(404, f"No completed run found for run_id: {run_id}")

    mapping: TopicMappingResult = result["topic_mapping"]
    if len(rows) != len(mapping.mappings):
        raise HTTPException(400, f"Expected {len(mapping.mappings)} mapping rows, got {len(rows)}.")

    new_mappings = []
    for original, row in zip(mapping.mappings, rows):
        case_wb = row.get("case_workbook") or None
        event_wb = row.get("drug_event_workbook") or None
        approved = bool(row.get("approved"))
        new_mappings.append(TopicMappingEntry(
            pbrer_section_number=original.pbrer_section_number, pbrer_heading=original.pbrer_heading,
            excel_criterion_type=original.excel_criterion_type, excel_criterion_value=original.excel_criterion_value,
            case_workbook=case_wb, drug_event_workbook=event_wb,
            confidence=1.0 if approved else original.confidence,
            needs_review=not approved,
            warnings=[] if (case_wb != original.case_workbook or event_wb != original.drug_event_workbook or approved)
            else original.warnings,
        ))

    new_mapping = TopicMappingResult(
        run_id=mapping.run_id, generated_at=datetime.now(UTC), mappings=new_mappings,
        unmatched_workbooks=mapping.unmatched_workbooks, unmatched_document_topics=mapping.unmatched_document_topics,
    )

    new_result = recompute_from_topic_mapping(result, new_mapping)
    run_store.save_result(run_id, new_result)
    return result_to_json(new_result)
