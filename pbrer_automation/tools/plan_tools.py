"""
Predefined Python tool backing the Calculation Planning Agent. Assembles
an execution plan from already-gathered structured evidence (workbook
inventory, topic mapping) and the APPROVED metric registry -- it never
invents a business rule or generates calculation code; it only decides
WHICH validated Python functions/columns feed each metric, and validates
that the required canonical fields were actually mapped with acceptable
confidence before marking a step as ready to execute.
"""
from __future__ import annotations

from typing import Any

from config.metric_registry import METRIC_REGISTRY, CanonicalField, WorkbookType


def _find_data_sheet(workbook_entry: dict[str, Any]) -> dict[str, Any] | None:
    for sheet in workbook_entry.get("sheets", []):
        if sheet.get("role") == "data_table":
            return sheet
    return None


def _mapped_columns(workbook_entry: dict[str, Any]) -> dict[str, str]:
    """canonical_field -> actual raw column name, from the Excel Agent's
    column_mappings (only columns it actually assigned a canonical field
    to -- not demoted/needs-review-without-assignment candidates)."""
    out = {}
    for m in workbook_entry.get("column_mappings", []):
        if m.get("canonical_field"):
            out[m["canonical_field"]] = m["raw_column"]
    return out


def _validate_required_fields(required_fields: list[str], mapped: dict[str, str]) -> tuple[bool, list[str]]:
    missing = [f for f in required_fields if f not in mapped]
    return (len(missing) == 0, missing)


def build_execution_plan(document_topics: list[dict[str, Any]], workbook_entries: list[dict[str, Any]],
                          topic_mappings: list[dict[str, Any]], reporting_start: str, reporting_end: str) -> dict[str, Any]:
    """Build one ExecutionPlanStep per (metric, topic) combination the
    evidence actually supports. A step is only marked validated=True if
    every canonical field the metric registry requires was mapped with
    sufficient confidence on the relevant workbook; otherwise it's
    included (for visibility) but flagged for review and MUST NOT be
    executed by the calculation engine."""
    workbooks_by_name = {w["file_name"]: w for w in workbook_entries}
    steps: list[dict[str, Any]] = []
    warnings: list[str] = []

    all_case_wb = next((w for w in workbook_entries if w.get("workbook_type") == WorkbookType.ALL_CASE.value), None)
    if all_case_wb is not None:
        sheet = _find_data_sheet(all_case_wb)
        mapped = _mapped_columns(all_case_wb)
        metric_def = METRIC_REGISTRY["total_case_count"]
        valid, missing = _validate_required_fields([f.value for f in metric_def.required_fields], mapped)
        steps.append(_make_step("total_case_count", None, "All post-marketing cases", all_case_wb, sheet,
                                 metric_def, mapped, reporting_start, reporting_end, valid, missing))
    else:
        warnings.append("No all-case workbook found; total_case_count cannot be planned.")

    for mapping in topic_mappings:
        case_wb_name = mapping.get("case_workbook")
        if not case_wb_name or case_wb_name not in workbooks_by_name:
            continue
        case_wb = workbooks_by_name[case_wb_name]
        case_sheet = _find_data_sheet(case_wb)
        case_mapped = _mapped_columns(case_wb)

        for metric_id in ("topic_case_count", "source_breakdown"):
            metric_def = METRIC_REGISTRY[metric_id]
            valid, missing = _validate_required_fields([f.value for f in metric_def.required_fields], case_mapped)
            steps.append(_make_step(metric_id, mapping.get("pbrer_section_number"), mapping.get("pbrer_heading"),
                                     case_wb, case_sheet, metric_def, case_mapped, reporting_start, reporting_end,
                                     valid, missing))

        event_wb_name = mapping.get("drug_event_workbook")
        if not event_wb_name or event_wb_name not in workbooks_by_name:
            warnings.append(f"Topic '{mapping.get('pbrer_heading')}' has no linked drug-event workbook; "
                             "serious/fatal/PT-frequency metrics cannot be planned.")
            continue
        event_wb = workbooks_by_name[event_wb_name]
        event_sheet = _find_data_sheet(event_wb)
        event_mapped = _mapped_columns(event_wb)

        for metric_id in ("serious_case_count", "fatal_case_count", "event_pt_frequency", "serious_fatal_percentages"):
            metric_def = METRIC_REGISTRY[metric_id]
            valid, missing = _validate_required_fields([f.value for f in metric_def.required_fields], event_mapped)
            steps.append(_make_step(metric_id, mapping.get("pbrer_section_number"), mapping.get("pbrer_heading"),
                                     event_wb, event_sheet, metric_def, event_mapped, reporting_start, reporting_end,
                                     valid, missing))

    return {"steps": steps, "warnings": warnings}


def _make_step(metric_id: str, section_number: str | None, heading: str | None, workbook: dict[str, Any],
                sheet: dict[str, Any] | None, metric_def, mapped: dict[str, str], reporting_start: str,
                reporting_end: str, valid: bool, missing: list[str]) -> dict[str, Any]:
    date_field = mapped.get(CanonicalField.INITIAL_APPROVAL_DATE.value)
    return {
        "metric_id": metric_id,
        "pbrer_section_number": section_number,
        "topic_heading": heading or "",
        "source_workbook": workbook["file_name"],
        "source_sheet": sheet["sheet_name"] if sheet else "",
        "canonical_fields": [f.value for f in metric_def.required_fields],
        "mapped_columns": mapped,
        "date_field": date_field,
        "date_format": "YYYYMMDD_numeric" if date_field else None,
        "reporting_start": reporting_start,
        "reporting_end": reporting_end,
        "applies_clinical_trials_exclusion": True,
        "grain": metric_def.grain.value,
        "distinct_by": metric_def.distinct_by.value if metric_def.distinct_by else None,
        "join_requirements": metric_def.join_requirements,
        "percentage_formula": metric_def.percentage_formula,
        "validated": valid,
        "validation_notes": [] if valid else [f"Missing required canonical field mapping(s): {missing}"],
        "header_row": sheet.get("header_row") if sheet else None,
        "data_end_row": sheet.get("data_end_row") if sheet else None,
    }
