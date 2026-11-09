"""
Deterministic case-level calculations (Part 3 C/D/E of prompt.md).
Pure pandas, no AI involved.
"""
from __future__ import annotations

import pandas as pd

from processing.date_normalizer import filter_by_reporting_period
from processing.source_filter import apply_clinical_trials_exclusion, source_breakdown


def compute_eligible_cases(df: pd.DataFrame, case_id_column: str, date_column: str,
                             primary_source_column: str, reporting_start: str, reporting_end: str,
                             date_format_hint: str | None = None) -> dict:
    """Apply the reporting-period filter (inclusive both ends) THEN the
    Clinical Trials exclusion, in that order, and return the eligible
    rows plus every intermediate count needed for audit evidence."""
    period = filter_by_reporting_period(df, date_column, reporting_start, reporting_end, date_format_hint)
    ct = apply_clinical_trials_exclusion(period["filtered_df"], primary_source_column)
    eligible_df = ct["filtered_df"]
    return {
        "eligible_df": eligible_df,
        "rows_before_filter": period["rows_before"],
        "rows_in_period": period["rows_in_period"],
        "rows_outside_period": period["rows_outside_period"],
        "rows_unparseable_date": period["rows_unparseable_date"],
        "rows_excluded_as_clinical_trial": ct["rows_excluded_as_clinical_trial"],
        "clinical_trial_values_matched": ct["matched_source_values"],
        "rows_after_filter": len(eligible_df),
        "distinct_case_count": int(eligible_df[case_id_column].nunique()),
    }


def compute_case_source_breakdown(eligible_df: pd.DataFrame, case_id_column: str,
                                    primary_source_column: str) -> dict[str, int]:
    return source_breakdown(eligible_df, case_id_column, primary_source_column)


def check_duplicate_case_ids(df: pd.DataFrame, case_id_column: str) -> dict:
    """Validation helper (Part 5, mandatory check #7): duplicate case
    records in a file that is supposed to be one-row-per-case."""
    counts = df[case_id_column].value_counts()
    duplicates = counts[counts > 1]
    return {
        "has_duplicates": len(duplicates) > 0,
        "duplicate_case_ids": duplicates.index.tolist()[:50],  # cap for audit display
        "duplicate_count": int(len(duplicates)),
    }


def check_missing_case_ids(df: pd.DataFrame, case_id_column: str) -> dict:
    missing = df[case_id_column].isna().sum()
    return {"missing_case_id_count": int(missing)}
