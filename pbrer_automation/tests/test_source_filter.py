from __future__ import annotations

import pandas as pd

from config.metric_registry import is_clinical_trial_source
from processing.source_filter import apply_clinical_trials_exclusion


def test_clinical_trial_dynamic_match_not_exact_literal():
    # The rule's VALUE recognition is a dynamic pattern match, not a
    # hardcoded exact-literal comparison -- these differently-worded
    # values all represent the same semantic category.
    assert is_clinical_trial_source("Report from study-Clinical Trials")
    assert is_clinical_trial_source("Clinical Trial Report")
    assert is_clinical_trial_source("CLINICAL TRIALS")
    assert not is_clinical_trial_source("Spontaneous")
    assert not is_clinical_trial_source("Report from study-Other Studies")
    assert not is_clinical_trial_source(None)


def test_exclusion_removes_only_clinical_trial_rows():
    df = pd.DataFrame({
        "case_id": ["A", "B", "C", "D"],
        "source": ["Spontaneous", "Report from study-Clinical Trials", "Report from study-Other Studies",
                    "Report from study-Clinical Trials"],
    })
    result = apply_clinical_trials_exclusion(df, "source")
    assert result["rows_before"] == 4
    assert result["rows_excluded_as_clinical_trial"] == 2
    assert len(result["filtered_df"]) == 2
    assert set(result["filtered_df"]["case_id"]) == {"A", "C"}
    assert result["matched_source_values"] == ["Report from study-Clinical Trials"]
