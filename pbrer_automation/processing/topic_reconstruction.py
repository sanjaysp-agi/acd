"""
Independent topic reconstruction and cross-validation
(prompt.md Part 2 / Agent 3, lines 378-394; Part 5 mandatory check #13).

The topic-specific case/drug-event exports are the PRIMARY input for every
calculated figure (processing/topic_calculator.py). This module is a
SEPARATE, independent cross-check: where the all-drug-event workbook
carries its own MedDRA classification columns (Event PT/HLT/HLGT/SOC), the
topic's own Excel search criterion is re-applied directly to the all-event
dataset to reconstruct which cases/events SHOULD match the topic, and the
result is compared against the topic-specific export's own figures.

A discrepancy here does not override the primary calculation -- it is
recorded as evidence for review (prompt.md: "Record any discrepancies").
SMQ/CMQ criteria are never reconstructed this way: a standard all-event
export has no SMQ/CMQ membership column, so pretending to reproduce one
would fabricate a match the data cannot support.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from config.metric_registry import CanonicalField, CriterionType
from processing.case_calculator import compute_eligible_cases
from tools.topic_tools import extract_excel_criterion_terms

# Which canonical MedDRA column a given Excel criterion type must be
# re-applied against in the all-drug-event workbook.
CRITERION_TYPE_TO_MEDDRA_FIELD: dict[CriterionType, CanonicalField] = {
    CriterionType.PT: CanonicalField.EVENT_PT,
    CriterionType.HLT: CanonicalField.EVENT_HLT,
    CriterionType.HLGT: CanonicalField.EVENT_HLGT,
    CriterionType.SOC: CanonicalField.EVENT_SOC,
}


def reconstruction_feasible(criterion_type: CriterionType,
                              all_event_mapped_columns: dict[str, str]) -> tuple[bool, str, CanonicalField | None]:
    """Whether the all-event workbook carries the MedDRA column needed to
    re-apply this topic's own criterion type. SMQ/CMQ criteria are never
    reconstructable from a standard event export (prompt.md line 394) --
    those memberships require a separate SMQ/CMQ definition table this
    POC does not have."""
    if criterion_type in (CriterionType.SMQ, CriterionType.CMQ, CriterionType.UNKNOWN):
        return (False,
                f"Criterion type '{criterion_type.value}' cannot be independently reproduced from a "
                "standard all-event export (no SMQ/CMQ membership column available) -- not attempted.",
                None)
    field = CRITERION_TYPE_TO_MEDDRA_FIELD.get(criterion_type)
    if field is None or field.value not in all_event_mapped_columns:
        return (False,
                f"All-drug-event workbook has no mapped column for '{criterion_type.value if field else criterion_type}' "
                "-- reconstruction not possible with the columns actually available.",
                field)
    return True, "", field


def reconstruct_topic_from_all_events(
    all_event_file_path: str, all_event_sheet: str, all_event_header_row: int,
    case_id_col: str, date_col: str, source_col: str, meddra_col: str,
    criterion_type: CriterionType, criterion_value: str | None,
    reporting_start: str, reporting_end: str, data_end_row: int | None = None,
) -> dict[str, Any]:
    """Independently re-derive which events/cases match this topic by
    applying the topic's OWN Excel search criterion (split into
    individual MedDRA terms, see tools.topic_tools.extract_criterion_terms)
    to the all-drug-event workbook's MedDRA classification column, then
    the same date + Clinical Trials filters used everywhere else."""
    terms = set(extract_excel_criterion_terms(criterion_value))
    nrows = (data_end_row - all_event_header_row) if data_end_row else None
    df = pd.read_excel(all_event_file_path, sheet_name=all_event_sheet,
                         header=all_event_header_row - 1, nrows=nrows)
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]

    meddra_values = df[meddra_col].astype(str).str.strip().str.lower()
    matched_mask = meddra_values.isin(terms) if terms else pd.Series(False, index=df.index)
    matched_df = df[matched_mask]

    eligibility = compute_eligible_cases(matched_df, case_id_col, date_col, source_col,
                                           reporting_start, reporting_end)
    eligible_df = eligibility["eligible_df"]

    return {
        "criterion_type": criterion_type.value,
        "criterion_terms_used": sorted(terms),
        "matched_meddra_values_sample": sorted(set(meddra_values[matched_mask].unique().tolist()))[:50],
        "reconstructed_event_row_count": int(matched_mask.sum()),
        "reconstructed_case_count": eligibility["distinct_case_count"],
        "reconstructed_case_ids": set(eligible_df[case_id_col].unique()),
        "evidence": {
            "rows_before_filter": int(len(df)),
            "rows_matching_criterion_terms": int(matched_mask.sum()),
            "rows_in_period": eligibility["rows_in_period"],
            "rows_excluded_as_clinical_trial": eligibility["rows_excluded_as_clinical_trial"],
            "rows_after_filter": eligibility["rows_after_filter"],
        },
    }


def compare_reconstruction_with_topic_export(
    reconstructed_case_count: int, reconstructed_case_ids: set,
    topic_case_count: int, topic_case_ids: set,
) -> dict[str, Any]:
    """Compare the independently reconstructed case set against the
    topic-specific export's own eligible case set. A mismatch does not
    automatically mean the topic export is wrong -- it means the two
    need reconciliation (e.g. criterion wording vs. actual MedDRA values
    may not be perfectly reproducible from terms alone) -- so it is
    reported as a discrepancy for review, never silently resolved."""
    only_in_reconstruction = reconstructed_case_ids - topic_case_ids
    only_in_topic_export = topic_case_ids - reconstructed_case_ids
    counts_match = reconstructed_case_count == topic_case_count
    sets_identical = not only_in_reconstruction and not only_in_topic_export
    return {
        "counts_match": counts_match,
        "case_sets_identical": sets_identical,
        "cases_only_in_reconstruction_sample": sorted(str(c) for c in only_in_reconstruction)[:50],
        "cases_only_in_topic_export_sample": sorted(str(c) for c in only_in_topic_export)[:50],
        "cases_only_in_reconstruction_count": len(only_in_reconstruction),
        "cases_only_in_topic_export_count": len(only_in_topic_export),
        "status": "match" if (counts_match and sets_identical) else "discrepancy",
    }


def check_case_event_population_alignment(case_ids: set, event_case_ids: set) -> dict[str, Any]:
    """Rule H (prompt.md Part 3): check for mismatched topic case/event
    exports -- event-workbook case IDs with no matching record in the
    paired case workbook, and vice versa. A large mismatch suggests the
    two exports were not generated from the same search/snapshot and
    should not be treated as a matched pair without review."""
    event_ids_without_case = event_case_ids - case_ids
    case_ids_without_event = case_ids - event_case_ids
    return {
        "case_ids_total": len(case_ids),
        "event_case_ids_total": len(event_case_ids),
        "event_case_ids_without_matching_case_record": len(event_ids_without_case),
        "case_ids_without_any_matching_event_record": len(case_ids_without_event),
        "event_case_ids_without_matching_case_record_sample": sorted(str(c) for c in event_ids_without_case)[:20],
        "case_ids_without_any_matching_event_record_sample": sorted(str(c) for c in case_ids_without_event)[:20],
    }
