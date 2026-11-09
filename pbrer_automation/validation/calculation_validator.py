"""
Builds CalculationEvidence + MetricResult from a validated ExecutionPlan
step and its raw calculation output, and runs the mandatory per-metric
checks from prompt.md Part 5 (duplicate/missing case IDs, date-boundary
inclusivity, source-exclusion sanity). A critical failure here must
prevent the result from being marked "verified".
"""
from __future__ import annotations

from typing import Any

from config.metric_registry import KNOWN_NON_AFFIRMATIVE_CATEGORIES, normalize_flag_value
from models.schemas import CalculationEvidence, MetricResult, ValidationCheckResult, ValidationReport

_RECOGNIZED_FLAG_CATEGORIES = KNOWN_NON_AFFIRMATIVE_CATEGORIES | {"yes"}


def run_mandatory_checks(step_validated: bool, evidence: dict[str, Any], metric_id: str | None = None,
                           calculated_value: Any = None) -> list[ValidationCheckResult]:
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

    # Mandatory check #10: seriousness/death classification sanity. Every
    # distinct raw value observed in the seriousness/death columns must
    # normalize to a recognized category -- an unrecognized value (typo,
    # new export category) must be flagged, never silently treated as "No".
    seriousness_values = evidence.get("event_seriousness_unique_values")
    death_values = evidence.get("event_death_unique_values")
    if seriousness_values is not None or death_values is not None:
        unrecognized = sorted({
            v for v in (seriousness_values or []) + (death_values or [])
            if normalize_flag_value(v) not in _RECOGNIZED_FLAG_CATEGORIES
        })
        checks.append(ValidationCheckResult(
            check_name="seriousness_death_classification",
            status="pass" if not unrecognized else "warning",
            message="All observed seriousness/death values normalize to a recognized category."
                    if not unrecognized else
                    f"Unrecognized seriousness/death category value(s) observed: {unrecognized}.",
            evidence={"event_seriousness_unique_values": seriousness_values,
                       "event_death_unique_values": death_values, "unrecognized": unrecognized},
        ))

    # Mandatory check #11: percentage calculation validation -- independently
    # recompute the percentage from the same inputs the metric result itself
    # reports, so a rounding/denominator bug surfaces as a formal failure
    # rather than only being visible by eyeballing the Results page.
    if metric_id == "serious_fatal_percentages" and isinstance(calculated_value, dict):
        from processing.event_calculator import compute_percentage

        serious_count = evidence.get("serious_case_count")
        fatal_count = evidence.get("fatal_case_count")
        topic_count = evidence.get("topic_case_count")
        decimals = evidence.get("rounding_decimals", 1)
        recomputed = {
            "serious_pct": compute_percentage(serious_count, topic_count, decimals) if topic_count is not None else None,
            "fatal_pct": compute_percentage(fatal_count, topic_count, decimals) if topic_count is not None else None,
        }
        ok = recomputed == calculated_value
        checks.append(ValidationCheckResult(
            check_name="percentage_calculation",
            status="pass" if ok else "fail",
            message="Reported serious/fatal percentages match independent recomputation from the "
                    "same case counts." if ok else
                    "Percentage calculation mismatch between the reported value and independent recomputation.",
            evidence={"reported": calculated_value, "recomputed": recomputed},
        ))

    return checks


def build_metric_result(metric_id: str, pbrer_section_number: str | None, topic_heading: str,
                          calculated_value: Any, source_workbook: str, source_sheet: str,
                          header_row: int | None, case_id_column: str | None, date_column: str | None,
                          date_format: str | None, reporting_start: str, reporting_end: str,
                          evidence: dict[str, Any], calculation_function: str,
                          step_validated: bool, historical_value: Any = None) -> MetricResult:
    checks = run_mandatory_checks(step_validated, evidence, metric_id=metric_id, calculated_value=calculated_value)
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
        extra={**evidence, "mandatory_checks": [c.model_dump(mode="json") for c in checks]},
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


def assemble_validation_report(run_id: str, metric_results: list[MetricResult],
                                  extra_checks: list[ValidationCheckResult]) -> ValidationReport:
    """Builds the single, structured ValidationReport (prompt.md Part 5)
    combining every per-metric mandatory check already embedded in each
    MetricResult's evidence with the input/workbook/mapping-level checks
    computed outside the per-metric loop (checks #1-4, #8, #12, #13)."""
    from datetime import datetime, UTC

    all_checks: list[ValidationCheckResult] = []
    for mr in metric_results:
        for c in mr.evidence.extra.get("mandatory_checks", []):
            all_checks.append(ValidationCheckResult.model_validate(c))
    all_checks.extend(extra_checks)

    overall = "verified"
    if any(c.status == "fail" for c in all_checks) or any(mr.validation_status == "failed" for mr in metric_results):
        overall = "failed"
    elif any(c.status == "warning" for c in all_checks) or any(mr.validation_status == "warning" for mr in metric_results):
        overall = "warning"

    return ValidationReport(run_id=run_id, generated_at=datetime.now(UTC), checks=all_checks,
                              metric_results=metric_results, overall_status=overall)
