"""
Predefined Python tool for the deterministic half of the AI Score
Validation Agent (agents/ai_scoring_agent.py).

Runs AFTER validation/calculation_validator and validation/reconciliation
have already produced each MetricResult's validation_status and (where a
historical figure exists) its match/mismatch against the previous/approved
PBRER. This tool turns that already-computed evidence into a baseline
confidence score PER METRIC plus an explicit citation -- never a bare
number with no explanation of where it came from. A real Bedrock-backed
agent can refine this baseline (e.g. reading the document topic's raw
table rows itself); local-deterministic mode reports the baseline as-is,
the same honest-fallback pattern as every other agent's local policy (see
agents/base.ToolCallingAgent).
"""
from __future__ import annotations

from typing import Any


def _document_topic_for(document_topics: list[dict[str, Any]], pbrer_section_number: str | None,
                          topic_heading: str) -> dict[str, Any] | None:
    for topic in document_topics:
        if pbrer_section_number is not None and topic.get("section_number") == pbrer_section_number:
            return topic
    for topic in document_topics:
        if topic.get("title") == topic_heading:
            return topic
    return None


# Internal-validation-status -> baseline score, used only when no historical
# benchmark figure exists at all (so there is no better evidence available).
_NO_BENCHMARK_SCORE_BY_STATUS = {"verified": 0.6, "warning": 0.4, "failed": 0.1, "unverified": 0.5}


def compute_baseline_ai_scores(document_topics: list[dict[str, Any]],
                                 metric_results: list[dict[str, Any]]) -> dict[str, Any]:
    """For each MetricResult, decide:
      - present_in_source: True only when the previous/approved PBRER
        actually carried a historical figure for this metric
        (mr["historical_value"] is not None) -- never inferred, never
        guessed from anything else.
      - score: how much the available evidence actually supports the
        calculated value. A benchmark match scores highest; a benchmark
        mismatch scores low (the value IS present in the source but
        disagrees with the current calculation); with no benchmark figure
        at all, the score falls back to the deterministic validation_status
        already attached to the MetricResult (the mandatory checks run in
        validation.calculation_validator), since that is the only other
        evidence available.
      - citation: where the score's reasoning comes from -- the document's
        section number/title when a historical figure exists, otherwise the
        calculation's own source workbook/sheet.
    """
    scores: list[dict[str, Any]] = []
    for mr in metric_results:
        section = mr.get("pbrer_section_number")
        heading = mr.get("topic_heading")
        historical = mr.get("historical_value")
        difference = mr.get("difference")
        validation_status = mr.get("validation_status", "unverified")
        evidence = mr.get("evidence") or {}

        if historical is not None:
            matched = difference == 0
            topic = _document_topic_for(document_topics, section, heading)
            citation = {
                "source_type": "document",
                "document_section_number": (topic or {}).get("section_number") or section,
                "document_section_title": (topic or {}).get("title") or heading,
                "source_workbook": None,
                "source_sheet": None,
                "detail": (
                    f"Historical figure {historical!r} for '{heading}' found in the previous/approved "
                    f"PBRER document; calculated value {mr.get('calculated_value')!r} "
                    + ("matches it exactly." if matched else "does not match it -- see benchmark report.")
                ),
            }
            scores.append({
                "metric_id": mr.get("metric_id"), "pbrer_section_number": section, "topic_heading": heading,
                "score": 0.95 if matched else 0.3, "present_in_source": True, "citation": citation,
                "rationale": ("Benchmark match against the previous/approved PBRER." if matched else
                              "Benchmark mismatch against the previous/approved PBRER -- value is present "
                              "in the source document but disagrees with the current calculation."),
            })
            continue

        citation = {
            "source_type": "workbook" if evidence.get("source_workbook") else "none",
            "document_section_number": None,
            "document_section_title": None,
            "source_workbook": evidence.get("source_workbook"),
            "source_sheet": evidence.get("source_sheet"),
            "detail": (
                "No historical figure for this metric exists in the previous/approved PBRER -- score "
                f"reflects only the internal mandatory-check validation status ('{validation_status}') "
                f"from {evidence.get('source_workbook') or 'the source workbook'}"
                + (f" / sheet {evidence['source_sheet']}" if evidence.get("source_sheet") else "") + "."
            ),
        }
        scores.append({
            "metric_id": mr.get("metric_id"), "pbrer_section_number": section, "topic_heading": heading,
            "score": _NO_BENCHMARK_SCORE_BY_STATUS.get(validation_status, 0.5),
            "present_in_source": False, "citation": citation,
            "rationale": f"No benchmark figure available; confidence derived from internal validation "
                         f"status '{validation_status}'.",
        })

    return {"scores": scores}
