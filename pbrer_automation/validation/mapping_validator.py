"""
Topic-mapping and case/event-join validation (prompt.md Part 5 mandatory
checks #8, #12, #13): case/event join validation (Part 3 Rule H),
topic-criteria matching confidence, and independent topic reconstruction.
Pure formatting/judgment over already-computed evidence -- the actual
set arithmetic lives in processing.topic_reconstruction so it can be
unit-tested independently of ValidationCheckResult wording.
"""
from __future__ import annotations

from typing import Any

from models.schemas import TopicMappingEntry, TopicReconstructionResult, ValidationCheckResult


def check_topic_criteria_matching(mapping_entries: list[TopicMappingEntry]) -> list[ValidationCheckResult]:
    """Mandatory check #12. A topic mapping with no workbook match, or one
    the Topic Mapping Agent itself flagged `needs_review`, must produce a
    formal validation entry -- not just a UI-only warning badge -- so it
    shows up wherever validation results are audited."""
    checks = []
    for entry in mapping_entries:
        if entry.case_workbook is None:
            status, message = "warning", (
                f"'{entry.pbrer_heading}' ({entry.pbrer_section_number}): no Excel workbook matched "
                "this PBRER topic -- it will have no calculated figures this run.")
        elif entry.needs_review:
            status, message = "warning", (
                f"'{entry.pbrer_heading}' ({entry.pbrer_section_number}): matched to "
                f"'{entry.case_workbook}' with confidence {entry.confidence:.2f} -- below the "
                "auto-approve threshold, needs manual review.")
        else:
            status, message = "pass", (
                f"'{entry.pbrer_heading}' ({entry.pbrer_section_number}): matched to "
                f"'{entry.case_workbook}' with confidence {entry.confidence:.2f}.")
        checks.append(ValidationCheckResult(
            check_name="topic_criteria_matching", status=status, message=message,
            evidence={"pbrer_section_number": entry.pbrer_section_number, "pbrer_heading": entry.pbrer_heading,
                       "case_workbook": entry.case_workbook, "confidence": entry.confidence,
                       "needs_review": entry.needs_review},
        ))
    return checks


def check_case_event_join(topic_heading: str, pbrer_section_number: str | None,
                             alignment: dict[str, Any]) -> ValidationCheckResult:
    """Mandatory check #8 / Part 3 Rule H: a topic-matching event-row case
    ID with no record at all in the paired case workbook (or a case with
    zero matching event rows in the paired event workbook) suggests the
    two exports were not pulled from the same search/snapshot -- flagged
    for review, never silently ignored."""
    orphan_events = alignment["event_case_ids_without_matching_case_record"]
    orphan_cases = alignment["case_ids_without_any_matching_event_record"]
    ok = orphan_events == 0
    messages = [f"{orphan_events} event-workbook case ID(s) have no matching case-workbook record."] if orphan_events \
        else ["Every event-workbook case ID has a matching case-workbook record."]
    if orphan_cases:
        messages.append(f"{orphan_cases} case-workbook case ID(s) have zero matching rows in the "
                          "paired event workbook (informational -- a case can legitimately report "
                          "no event matching this specific topic's drug-event export columns).")
    return ValidationCheckResult(
        check_name="case_event_join_validation",
        status="pass" if ok else "warning",
        message=f"'{topic_heading}' ({pbrer_section_number}): " + " ".join(messages),
        evidence=alignment,
    )


def check_independent_topic_reconstruction(result: TopicReconstructionResult) -> ValidationCheckResult:
    """Mandatory check #13. Cross-validates the topic-specific export
    against an independent reconstruction from the all-drug-event
    workbook, where the required MedDRA column is actually available.
    Not feasible (e.g. SMQ/CMQ criteria) is reported as 'pass' with an
    explicit reason, never as a failure -- the spec explicitly allows
    skipping reconstruction when it genuinely cannot be done."""
    if not result.feasible:
        return ValidationCheckResult(
            check_name="independent_topic_reconstruction",
            status="pass",
            message=f"'{result.topic_heading}' ({result.pbrer_section_number}): reconstruction not "
                     f"attempted -- {result.reason}",
            evidence={"feasible": False, "reason": result.reason},
        )
    status_from_comparison = (result.comparison or {}).get("status")
    ok = status_from_comparison == "match"
    return ValidationCheckResult(
        check_name="independent_topic_reconstruction",
        status="pass" if ok else "warning",
        message=f"'{result.topic_heading}' ({result.pbrer_section_number}): independent reconstruction "
                 f"from the all-drug-event workbook found {result.reconstructed_case_count} case(s) vs. "
                 f"{result.topic_export_case_count} in the topic-specific export -- "
                 f"{'match' if ok else 'DISCREPANCY, see evidence'}.",
        evidence={"feasible": True, "reconstructed_case_count": result.reconstructed_case_count,
                   "topic_export_case_count": result.topic_export_case_count, "comparison": result.comparison},
    )
