"""
Deterministic primary-source filtering. The Clinical Trials exclusion
rule is FIXED and non-configurable (config.metric_registry.
CLINICAL_TRIALS_EXCLUSION_ENABLED) -- it is applied here unconditionally
to every metric that requires the primary_source canonical field.
"""
from __future__ import annotations

import pandas as pd

from config.metric_registry import is_clinical_trial_source


def apply_clinical_trials_exclusion(df: pd.DataFrame, primary_source_column: str) -> dict:
    """Exclude Clinical-Trial-sourced rows. Returns the filtered dataframe
    plus which actual distinct values in this column matched the
    Clinical-Trials pattern, so the exclusion is auditable rather than a
    silent hardcoded comparison."""
    is_ct = df[primary_source_column].apply(is_clinical_trial_source)
    matched_values = sorted(df.loc[is_ct, primary_source_column].dropna().unique().tolist())
    return {
        "filtered_df": df[~is_ct],
        "rows_before": len(df),
        "rows_excluded_as_clinical_trial": int(is_ct.sum()),
        "matched_source_values": matched_values,
    }


def source_breakdown(df: pd.DataFrame, case_id_column: str, primary_source_column: str) -> dict[str, int]:
    """Distinct-case counts grouped by primary source category, over
    already-eligible (deduplicated-by-case) rows."""
    deduped = df.drop_duplicates(subset=[case_id_column])
    return deduped[primary_source_column].value_counts(dropna=False).to_dict()
