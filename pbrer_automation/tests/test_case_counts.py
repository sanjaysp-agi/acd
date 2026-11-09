from __future__ import annotations

from processing.topic_calculator import calculate_percentages, calculate_topic_case_metrics


def test_hallucinations_topic_case_count_matches_benchmark(hallucinations_case_file):
    result = calculate_topic_case_metrics(
        str(hallucinations_case_file), "CSMR Case_2", 6,
        "Case Number", "Derived-Initial-Approval-Date-(YYYYMMDD)", "Derived-Primary-Source",
        "2019-04-07", "2024-04-06", data_end_row=2475,
    )
    assert result["case_count"] == 270  # PBRER benchmark figure
    assert result["source_breakdown"]["Spontaneous"] == 224
    assert result["source_breakdown"]["Report from study-Other Studies"] == 46


def test_no_duplicate_case_ids_in_hallucinations_case_file(hallucinations_case_file):
    result = calculate_topic_case_metrics(
        str(hallucinations_case_file), "CSMR Case_2", 6,
        "Case Number", "Derived-Initial-Approval-Date-(YYYYMMDD)", "Derived-Primary-Source",
        "2019-04-07", "2024-04-06", data_end_row=2475,
    )
    assert result["evidence"]["duplicate_case_check"]["has_duplicates"] is False
