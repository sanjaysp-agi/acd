from __future__ import annotations

import openpyxl

from config.metric_registry import CanonicalField, CriterionType
from processing.topic_reconstruction import (
    check_case_event_population_alignment,
    compare_reconstruction_with_topic_export,
    reconstruct_topic_from_all_events,
    reconstruction_feasible,
)


def test_smq_cmq_criteria_are_never_reconstructed():
    """prompt.md line 394: SMQ/CMQ criteria must never be assumed
    reproducible from a standard all-event export."""
    feasible, reason, field = reconstruction_feasible(CriterionType.SMQ, {"event_hlt": "Event HLT"})
    assert feasible is False
    assert field is None
    assert "SMQ" in reason or "CMQ" in reason


def test_hlt_criterion_feasible_only_when_column_mapped():
    not_feasible, _, _ = reconstruction_feasible(CriterionType.HLT, {"event_pt": "Event PT"})
    assert not_feasible is False

    feasible, reason, field = reconstruction_feasible(CriterionType.HLT, {"event_hlt": "Event HLT"})
    assert feasible is True
    assert reason == ""
    assert field == CanonicalField.EVENT_HLT


def _build_all_event_workbook(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Case Number", "Derived-Initial-Approval-Date-(YYYYMMDD)", "Derived-Primary-Source", "Event HLT"])
    rows = [
        ("C-1", 20200101, "Spontaneous", "Hallucinations (excl sleep-related)"),
        ("C-2", 20200102, "Spontaneous", "Confusion and disorientation"),
        ("C-3", 20200103, "Report from study-Clinical Trials", "Hallucinations (excl sleep-related)"),  # CT excluded
        ("C-4", 20180101, "Spontaneous", "Hallucinations (excl sleep-related)"),  # outside reporting period
        ("C-5", 20200104, "Spontaneous", "Nausea"),  # unrelated topic, must not match
    ]
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_reconstruct_topic_from_all_events_applies_criterion_date_and_ct_filters(tmp_path):
    path = tmp_path / "all_event.xlsx"
    _build_all_event_workbook(path)

    result = reconstruct_topic_from_all_events(
        all_event_file_path=str(path), all_event_sheet="Sheet", all_event_header_row=1,
        case_id_col="Case Number", date_col="Derived-Initial-Approval-Date-(YYYYMMDD)",
        source_col="Derived-Primary-Source", meddra_col="Event HLT",
        criterion_type=CriterionType.HLT,
        criterion_value="Hallucinations (excl sleep-related), Confusion and disorientation",
        reporting_start="2019-04-07", reporting_end="2024-04-06",
    )

    # C-1 and C-2 match the criterion, are in-period, and not Clinical Trials.
    # C-3 matches the criterion but is Clinical-Trial-sourced -- excluded.
    # C-4 matches the criterion but is outside the reporting period -- excluded.
    # C-5 is in-period and eligible but doesn't match the criterion -- excluded.
    assert result["reconstructed_case_count"] == 2
    assert result["reconstructed_case_ids"] == {"C-1", "C-2"}
    assert result["evidence"]["rows_excluded_as_clinical_trial"] == 1


def test_compare_reconstruction_identical_sets_match():
    comparison = compare_reconstruction_with_topic_export(
        reconstructed_case_count=2, reconstructed_case_ids={"C-1", "C-2"},
        topic_case_count=2, topic_case_ids={"C-1", "C-2"},
    )
    assert comparison["status"] == "match"
    assert comparison["cases_only_in_reconstruction_count"] == 0
    assert comparison["cases_only_in_topic_export_count"] == 0


def test_compare_reconstruction_records_discrepancy_never_silently_resolved():
    comparison = compare_reconstruction_with_topic_export(
        reconstructed_case_count=2, reconstructed_case_ids={"C-1", "C-2"},
        topic_case_count=1, topic_case_ids={"C-1"},
    )
    assert comparison["status"] == "discrepancy"
    assert comparison["cases_only_in_reconstruction_count"] == 1
    assert "C-2" in comparison["cases_only_in_reconstruction_sample"]


def test_case_event_population_alignment_flags_orphans():
    """Part 3 Rule H: an event-workbook case ID with no matching case
    record (or vice versa) must be surfaced, never silently dropped."""
    alignment = check_case_event_population_alignment(
        case_ids={"C-1", "C-2", "C-3"}, event_case_ids={"C-1", "C-2", "C-4"},
    )
    assert alignment["event_case_ids_without_matching_case_record"] == 1
    assert "C-4" in alignment["event_case_ids_without_matching_case_record_sample"]
    assert alignment["case_ids_without_any_matching_event_record"] == 1
    assert "C-3" in alignment["case_ids_without_any_matching_event_record_sample"]
