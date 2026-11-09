from __future__ import annotations

from processing.topic_calculator import calculate_percentages, calculate_topic_case_metrics, calculate_topic_event_metrics


def test_hallucinations_serious_fatal_match_benchmark(hallucinations_case_file, hallucinations_event_file):
    case_result = calculate_topic_case_metrics(
        str(hallucinations_case_file), "CSMR Case_2", 6,
        "Case Number", "Derived-Initial-Approval-Date-(YYYYMMDD)", "Derived-Primary-Source",
        "2019-04-07", "2024-04-06", data_end_row=2475,
    )
    event_result = calculate_topic_event_metrics(
        str(hallucinations_event_file), "CSMR Drug Event_2", 6,
        "Case Number", "Derived-Initial-Approval-Date-(YYYYMMDD)", "Derived-Primary-Source",
        "Event Seriousness", "Death (Event)", "Event PT (Primary Path)",
        "2019-04-07", "2024-04-06", eligible_case_ids=case_result["eligible_case_ids"], data_end_row=2889,
    )
    assert event_result["serious_case_count"] == 98  # PBRER benchmark
    assert event_result["fatal_case_count"] == 1

    pct = calculate_percentages(event_result["serious_case_count"], event_result["fatal_case_count"],
                                  case_result["case_count"])
    assert pct["serious_pct"] == 36.3
    assert pct["fatal_pct"] == 0.4


def test_serious_uses_event_level_rollup_not_case_level_flag(hallucinations_case_file, hallucinations_event_file):
    """Regression guard for the exact bug the traceability HTML calls out:
    using the case-level Seriousness flag instead of the topic-specific
    event-level rollup silently inflates the serious count (82 vs 55 for
    ICD in the documented example). Confirm the event-row count is >=
    the distinct-case count (a case can have multiple serious rows)."""
    case_result = calculate_topic_case_metrics(
        str(hallucinations_case_file), "CSMR Case_2", 6,
        "Case Number", "Derived-Initial-Approval-Date-(YYYYMMDD)", "Derived-Primary-Source",
        "2019-04-07", "2024-04-06", data_end_row=2475,
    )
    event_result = calculate_topic_event_metrics(
        str(hallucinations_event_file), "CSMR Drug Event_2", 6,
        "Case Number", "Derived-Initial-Approval-Date-(YYYYMMDD)", "Derived-Primary-Source",
        "Event Seriousness", "Death (Event)", "Event PT (Primary Path)",
        "2019-04-07", "2024-04-06", eligible_case_ids=case_result["eligible_case_ids"], data_end_row=2889,
    )
    assert event_result["serious_event_row_count"] >= event_result["serious_case_count"]


def test_event_pt_frequency_uses_row_counts_not_distinct_cases(hallucinations_case_file, hallucinations_event_file):
    case_result = calculate_topic_case_metrics(
        str(hallucinations_case_file), "CSMR Case_2", 6,
        "Case Number", "Derived-Initial-Approval-Date-(YYYYMMDD)", "Derived-Primary-Source",
        "2019-04-07", "2024-04-06", data_end_row=2475,
    )
    event_result = calculate_topic_event_metrics(
        str(hallucinations_event_file), "CSMR Drug Event_2", 6,
        "Case Number", "Derived-Initial-Approval-Date-(YYYYMMDD)", "Derived-Primary-Source",
        "Event Seriousness", "Death (Event)", "Event PT (Primary Path)",
        "2019-04-07", "2024-04-06", eligible_case_ids=case_result["eligible_case_ids"], data_end_row=2889,
    )
    hallucination_pt = next(p for p in event_result["event_pt_frequency"] if p["event_pt"] == "Hallucination")
    # A case reporting the same PT twice (e.g. on follow-up) must count
    # twice at the event-row level -- row count >= distinct case count.
    assert hallucination_pt["event_row_count"] >= hallucination_pt["distinct_case_count"]
