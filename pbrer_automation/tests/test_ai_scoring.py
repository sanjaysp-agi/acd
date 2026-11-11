"""
Fast unit tests for the AI Score Validation Agent (agents/ai_scoring_agent.py)
and its deterministic baseline tool (tools/scoring_tools.py). Uses hand-built
MetricResult/DocumentStructure fixtures rather than the real (slow) pipeline
fixtures, since the behaviour under test -- scoring + citation, never the
calculation itself -- does not depend on real files.
"""
from __future__ import annotations

from datetime import datetime, UTC

from agents.ai_scoring_agent import AIScoreAgent, build_scoring_tool_specs
from models.schemas import CalculationEvidence, DocumentStructure, DocumentTopic, MetricResult
from tools.scoring_tools import compute_baseline_ai_scores


def _evidence(**overrides) -> CalculationEvidence:
    base = dict(
        source_workbook="04_case_Hallucinations and confusion_CSMR.xlsx", source_sheet="CSMR Case_2",
        header_row=6, case_id_column="Case Number", date_column="Derived-Initial-Approval-Date-(YYYYMMDD)",
        date_format="%Y%m%d", reporting_start="2019-04-07", reporting_end="2024-04-06",
        source_exclusion_applied=True, rows_before_filter=2475, rows_after_filter=270,
        calculation_function="processing.topic_calculator.calculate_topic_case_metrics",
    )
    base.update(overrides)
    return CalculationEvidence(**base)


def _metric_result(metric_id="topic_case_count", calculated_value=270, historical_value=None,
                     difference=None, validation_status="verified", section="16.3.1.3",
                     heading="Hallucinations and confusion") -> MetricResult:
    return MetricResult(
        metric_id=metric_id, pbrer_section_number=section, topic_heading=heading,
        calculated_value=calculated_value, historical_value=historical_value, difference=difference,
        evidence=_evidence(), validation_status=validation_status,
    )


def _document_structure(topics: list[DocumentTopic]) -> DocumentStructure:
    return DocumentStructure(
        run_id="test", generated_at=datetime.now(UTC), document_file_name="pbrer.docx",
        target_section_title="Evaluation of Risks and New Information", target_section_located=True,
        topics=topics,
    )


def test_baseline_benchmark_match_scores_high_and_cites_document():
    mr = _metric_result(historical_value=270, difference=0, validation_status="verified")
    out = compute_baseline_ai_scores(
        document_topics=[{"section_number": "16.3.1.3", "title": "Hallucinations and confusion"}],
        metric_results=[mr.model_dump(mode="json")],
    )
    score = out["scores"][0]
    assert score["present_in_source"] is True
    assert score["score"] == 0.95
    assert score["citation"]["source_type"] == "document"
    assert score["citation"]["document_section_number"] == "16.3.1.3"


def test_baseline_benchmark_mismatch_scores_low_but_still_present():
    mr = _metric_result(calculated_value=275, historical_value=270, difference=5, validation_status="warning")
    out = compute_baseline_ai_scores(document_topics=[], metric_results=[mr.model_dump(mode="json")])
    score = out["scores"][0]
    assert score["present_in_source"] is True
    assert score["score"] == 0.3


def test_baseline_no_benchmark_falls_back_to_validation_status():
    mr = _metric_result(historical_value=None, validation_status="failed")
    out = compute_baseline_ai_scores(document_topics=[], metric_results=[mr.model_dump(mode="json")])
    score = out["scores"][0]
    assert score["present_in_source"] is False
    assert score["score"] == 0.1
    assert score["citation"]["source_type"] == "workbook"
    assert score["citation"]["source_workbook"] == "04_case_Hallucinations and confusion_CSMR.xlsx"


def test_report_ai_scores_downgrades_unsupported_present_in_source_claim():
    """A provider (real or local) claiming present_in_source=True with no
    actual citation must be downgraded to False -- see
    agents.ai_scoring_agent.build_scoring_tool_specs."""
    specs = {s.name: s for s in build_scoring_tool_specs(document_topics=[], metric_results=[])}
    result = specs["report_ai_scores"].fn(scores=[{
        "metric_id": "topic_case_count", "pbrer_section_number": "16.3.1.3", "topic_heading": "x",
        "score": 1.5, "present_in_source": True, "citation": {"source_type": "document", "detail": "no real citation"},
        "rationale": "unsupported claim",
    }])
    scored = result["scores"][0]
    assert scored["present_in_source"] is False  # no section/title/workbook citation to back it up
    assert scored["score"] == 1.0  # clamped to the valid 0.0-1.0 range


def test_ai_score_agent_run_reports_deterministic_baseline_in_local_mode():
    topic = DocumentTopic(section_number="16.3.1.3", title="Hallucinations and confusion", level=3,
                           historical_metrics={"topic_count": 270})
    document_structure = _document_structure([topic])
    mr = _metric_result(historical_value=270, difference=0, validation_status="verified")

    agent = AIScoreAgent()
    report = agent.run("pytest-ai-scoring", document_structure, [mr])

    assert report.mode == "local_deterministic"
    assert len(report.scores) == 1
    assert report.scores[0].metric_id == "topic_case_count"
    assert report.scores[0].present_in_source is True
    assert report.scores[0].score == 0.95
    assert report.scores[0].citation.document_section_number == "16.3.1.3"
