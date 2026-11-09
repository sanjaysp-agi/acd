"""
Top-level orchestrator for one topic's full metric set: topic case count,
total case count (caller supplies the all-case side separately, since
it's shared across topics), source breakdown, serious/fatal counts and
percentages, event PT frequency. Pure pandas -- this IS "Part 3: the
deterministic Python calculation engine", not an AI agent. It consumes
an already-validated execution plan (file paths, header rows, column
mappings, reporting dates); it does not discover any of that itself.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from processing.case_calculator import check_duplicate_case_ids, check_missing_case_ids, compute_case_source_breakdown, compute_eligible_cases
from processing.event_calculator import compute_eligible_events, compute_event_pt_frequency, compute_fatal_case_count, compute_percentage, compute_serious_case_count


def calculate_topic_case_metrics(case_file_path: str, case_sheet: str, case_header_row: int,
                                    case_id_col: str, date_col: str, source_col: str,
                                    reporting_start: str, reporting_end: str,
                                    data_end_row: int | None = None) -> dict[str, Any]:
    """Topic (or all-case) case count + source breakdown, with full audit
    evidence. data_end_row should already exclude footer rows (from
    detect_footer_rows), established by the Excel Understanding Agent."""
    nrows = (data_end_row - case_header_row) if data_end_row else None
    df = pd.read_excel(case_file_path, sheet_name=case_sheet, header=case_header_row - 1, nrows=nrows)
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]

    dup_check = check_duplicate_case_ids(df, case_id_col)
    missing_check = check_missing_case_ids(df, case_id_col)

    eligibility = compute_eligible_cases(df, case_id_col, date_col, source_col, reporting_start, reporting_end)
    eligible_df = eligibility["eligible_df"]
    breakdown = compute_case_source_breakdown(eligible_df, case_id_col, source_col)

    return {
        "case_count": eligibility["distinct_case_count"],
        "source_breakdown": breakdown,
        "eligible_case_ids": set(eligible_df[case_id_col].unique()),
        "evidence": {
            "rows_before_filter": eligibility["rows_before_filter"],
            "rows_in_period": eligibility["rows_in_period"],
            "rows_outside_period": eligibility["rows_outside_period"],
            "rows_unparseable_date": eligibility["rows_unparseable_date"],
            "rows_excluded_as_clinical_trial": eligibility["rows_excluded_as_clinical_trial"],
            "clinical_trial_values_matched": eligibility["clinical_trial_values_matched"],
            "rows_after_filter": eligibility["rows_after_filter"],
            "duplicate_case_check": dup_check,
            "missing_case_id_check": missing_check,
        },
    }


def calculate_topic_event_metrics(event_file_path: str, event_sheet: str, event_header_row: int,
                                     case_id_col: str, date_col: str, source_col: str,
                                     event_seriousness_col: str, event_death_col: str, event_pt_col: str,
                                     reporting_start: str, reporting_end: str,
                                     eligible_case_ids: set | None,
                                     data_end_row: int | None = None) -> dict[str, Any]:
    """Serious/fatal event-level rollup + event PT frequency, restricted
    to the eligible case-number set from the paired case file."""
    nrows = (data_end_row - event_header_row) if data_end_row else None
    df = pd.read_excel(event_file_path, sheet_name=event_sheet, header=event_header_row - 1, nrows=nrows)
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]

    eligibility = compute_eligible_events(df, case_id_col, date_col, source_col, reporting_start, reporting_end,
                                            eligible_case_ids=eligible_case_ids)
    eligible_df = eligibility["eligible_df"]

    serious = compute_serious_case_count(eligible_df, case_id_col, event_seriousness_col)
    fatal = compute_fatal_case_count(eligible_df, case_id_col, event_death_col)
    pt_freq = compute_event_pt_frequency(eligible_df, case_id_col, event_pt_col)

    return {
        "serious_event_row_count": serious["serious_event_row_count"],
        "serious_case_count": serious["serious_distinct_case_count"],
        "fatal_event_row_count": fatal["fatal_event_row_count"],
        "fatal_case_count": fatal["fatal_distinct_case_count"],
        "event_pt_frequency": pt_freq,
        "evidence": {
            "rows_before_filter": eligibility["rows_before_filter"],
            "rows_in_period": eligibility["rows_in_period"],
            "rows_excluded_as_clinical_trial": eligibility["rows_excluded_as_clinical_trial"],
            "clinical_trial_values_matched": eligibility["clinical_trial_values_matched"],
            "rows_outside_eligible_case_set": eligibility["rows_outside_eligible_case_set"],
            "rows_after_filter": eligibility["rows_after_filter"],
        },
    }


def calculate_percentages(serious_case_count: int, fatal_case_count: int, topic_case_count: int,
                            decimals: int = 1) -> dict[str, float | None]:
    return {
        "serious_pct": compute_percentage(serious_case_count, topic_case_count, decimals),
        "fatal_pct": compute_percentage(fatal_case_count, topic_case_count, decimals),
    }
