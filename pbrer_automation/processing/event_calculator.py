"""
Deterministic event-level calculations (Part 3 F/G/H/I/L of prompt.md).

Critical rule, confirmed against the development-only traceability HTML:
serious/fatal are a TOPIC-SPECIFIC EVENT-LEVEL rollup (ANY matching event
row for that case says Yes), restricted to the eligible case-number set
from the case file -- NOT the general case-level Seriousness/Death flag,
and NOT filtered by Derived-Overall-Event-Relatedness (config.
metric_registry.RELATEDNESS_RULE documents why).
"""
from __future__ import annotations

import pandas as pd

from config.metric_registry import is_affirmative
from processing.date_normalizer import filter_by_reporting_period
from processing.source_filter import apply_clinical_trials_exclusion


def compute_eligible_events(df: pd.DataFrame, case_id_column: str, date_column: str,
                              primary_source_column: str, reporting_start: str, reporting_end: str,
                              eligible_case_ids: set | None = None,
                              date_format_hint: str | None = None) -> dict:
    """Same date + Clinical Trials filters as the case file, PLUS
    (optionally) restriction to the eligible case-number set established
    by the case-level calculation, so event-level figures never include
    cases the case file itself excluded."""
    period = filter_by_reporting_period(df, date_column, reporting_start, reporting_end, date_format_hint)
    ct = apply_clinical_trials_exclusion(period["filtered_df"], primary_source_column)
    eligible_df = ct["filtered_df"]
    # Captured BEFORE the eligible-case-set restriction below, so callers
    # can independently check for mismatched case/event exports (Part 3
    # Rule H: "Case IDs with no matching case record") -- restricting
    # first would make that comparison vacuous.
    case_ids_before_restriction = set(eligible_df[case_id_column].dropna().unique())

    rows_outside_case_set = 0
    if eligible_case_ids is not None:
        in_case_set = eligible_df[case_id_column].isin(eligible_case_ids)
        rows_outside_case_set = int((~in_case_set).sum())
        eligible_df = eligible_df[in_case_set]

    return {
        "eligible_df": eligible_df,
        "rows_before_filter": period["rows_before"],
        "rows_in_period": period["rows_in_period"],
        "rows_excluded_as_clinical_trial": ct["rows_excluded_as_clinical_trial"],
        "clinical_trial_values_matched": ct["matched_source_values"],
        "rows_outside_eligible_case_set": rows_outside_case_set,
        "rows_after_filter": len(eligible_df),
        "case_ids_before_case_set_restriction": case_ids_before_restriction,
    }


def compute_serious_case_count(eligible_event_df: pd.DataFrame, case_id_column: str,
                                 event_seriousness_column: str) -> dict:
    """A case counts as serious if ANY of its topic-matching event rows
    has Event Seriousness = Yes (normalized comparison). A case with
    multiple serious rows still counts once."""
    is_serious_row = eligible_event_df[event_seriousness_column].apply(is_affirmative)
    serious_case_ids = set(eligible_event_df.loc[is_serious_row, case_id_column].unique())
    return {
        "serious_event_row_count": int(is_serious_row.sum()),
        "serious_distinct_case_count": len(serious_case_ids),
        "serious_case_ids": serious_case_ids,
    }


def compute_fatal_case_count(eligible_event_df: pd.DataFrame, case_id_column: str,
                               event_death_column: str) -> dict:
    """Only an explicit Yes on Death (Event) qualifies. No/No Information/
    blank remain distinct from Yes and from each other -- never coalesced."""
    is_fatal_row = eligible_event_df[event_death_column].apply(is_affirmative)
    fatal_case_ids = set(eligible_event_df.loc[is_fatal_row, case_id_column].unique())
    return {
        "fatal_event_row_count": int(is_fatal_row.sum()),
        "fatal_distinct_case_count": len(fatal_case_ids),
        "fatal_case_ids": fatal_case_ids,
    }


def compute_event_pt_frequency(eligible_event_df: pd.DataFrame, case_id_column: str, pt_column: str) -> list[dict]:
    """Event-row counts per PT (NOT distinct-case counts, which would
    undercount a case reporting the same PT twice e.g. on follow-up) --
    with the distinct-case count shown alongside for case review."""
    grouped = eligible_event_df.groupby(pt_column)[case_id_column]
    out = []
    for pt, cases in grouped:
        out.append({
            "event_pt": pt,
            "event_row_count": int(len(cases)),
            "distinct_case_count": int(cases.nunique()),
        })
    out.sort(key=lambda d: -d["event_row_count"])
    return out


def compute_percentage(numerator: int, denominator: int, decimals: int = 1) -> float | None:
    if denominator == 0:
        return None
    return round(100 * numerator / denominator, decimals)
