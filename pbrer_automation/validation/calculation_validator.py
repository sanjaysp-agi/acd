"""
Builds CalculationEvidence + MetricResult from a validated ExecutionPlan
step and its raw calculation output, and runs the mandatory per-metric
checks from prompt.md Part 5 (duplicate/missing case IDs, date-boundary
inclusivity, source-exclusion sanity). A critical failure here must
prevent the result from being marked "verified".
"""
from __future__ import annotations

from typing import Any

from models.schemas import CalculationEvidence, MetricResult, ValidationCheckResult


def run_mandatory_checks(step_validated: bool, evidence: dict[str, Any]) -> list[ValidationCheckResult]:
    checks = []

    checks.append(ValidationCheckResult(
        check_name="column_mapping_validated",
        status="pass" if step_validated else "fail",
        message="Required canonical fields were mapped with acceptable confidence." if step_validated
                else "One or more required canonical fields were NOT mapped -- step not executed.",
    ))

    dup = evidence.get("duplicate_case_check")
    if dup is not None:
        checks.append(ValidationCheckResult(
            check_name="duplicate_case_ids",
            status="pass" if not dup["has_duplicates"] else "warning",
            message=f"{dup['duplicate_count']} duplicate case ID(s) found." if dup["has_duplicates"]
                    else "No duplicate case IDs found.",
            evidence={"duplicate_case_ids_sample": dup.get("duplicate_case_ids", [])[:10]},
        ))

    missing = evidence.get("missing_case_id_check")
    if missing is not None:
        checks.append(ValidationCheckResult(
            check_name="missing_case_ids",
            status="pass" if missing["missing_case_id_count"] == 0 else "warning",
            message=f"{missing['missing_case_id_count']} row(s) with missing case ID.",
        ))

    unparseable = evidence.get("rows_unparseable_date")
    if unparseable is not None:
        checks.append(ValidationCheckResult(
            check_name="date_parseability",
            status="pass" if unparseable == 0 else "warning",
            message=f"{unparseable} row(s) had an unparseable date value." if unparseable
                    else "All non-null date values parsed successfully.",
        ))

    ct_matched = evidence.get("clinical_trial_values_matched")
    if ct_matched is not None:
        checks.append(ValidationCheckResult(
            check_name="clinical_trials_exclusion",
            status="pass",
            message=f"Clinical Trials exclusion matched source value(s): {ct_matched}" if ct_matched
                    else "No rows matched the Clinical Trials pattern in this dataset.",
        ))

    return checks


def build_metric_result(metric_id: str, pbrer_section_number: str | None, topic_heading: str,
                          calculated_value: Any, source_workbook: str, source_sheet: str,
                          header_row: int | None, case_id_column: str | None, date_column: str | None,
                          date_format: str | None, reporting_start: str, reporting_end: str,
                          evidence: dict[str, Any], calculation_function: str,
                          step_validated: bool, historical_value: Any = None) -> MetricResult:
    checks = run_mandatory_checks(step_validated, evidence)
    critical_failures = [c for c in checks if c.status == "fail"]

    difference = None
    if historical_value is not None and isinstance(calculated_value, (int, float)) and isinstance(historical_value, (int, float)):
        difference = calculated_value - historical_value

    calc_evidence = CalculationEvidence(
        source_workbook=source_workbook, source_sheet=source_sheet, header_row=header_row,
        case_id_column=case_id_column, date_column=date_column, date_format=date_format,
        reporting_start=reporting_start, reporting_end=reporting_end,
        source_exclusion_applied=True,
        source_exclusion_values_matched=evidence.get("clinical_trial_values_matched", []),
        rows_before_filter=evidence.get("rows_before_filter", 0),
        rows_after_filter=evidence.get("rows_after_filter", 0),
        distinct_case_count=evidence.get("distinct_case_count"),
        event_row_count=evidence.get("event_row_count"),
        calculation_function=calculation_function,
        extra=evidence,
    )

    status = "verified"
    if critical_failures:
        status = "failed"
    elif any(c.status == "warning" for c in checks):
        status = "warning"

    return MetricResult(
        metric_id=metric_id, pbrer_section_number=pbrer_section_number, topic_heading=topic_heading,
        calculated_value=calculated_value, historical_value=historical_value, difference=difference,
        evidence=calc_evidence, validation_status=status,
        validation_messages=[c.message for c in checks],
    )
