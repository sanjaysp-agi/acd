"""
Regression test for a real bug: observability/run_store.py keeps an
explicit allow-list of which pipeline-result keys are Pydantic models
(_MODEL_FIELDS/_LIST_MODEL_FIELDS) so save_result() knows to call
.model_dump() before handing the result to json.dumps(). Adding a new
top-level model field to pipeline.run_full_pipeline's return dict
(ai_score_report) without registering it here caused save_result() to
call json.dumps() directly on a raw AIScoreReport object, raising
TypeError -- silently failing every real run right after the AI Score
Validation Agent completed, with no run_completed/run_failed trace event
ever written (see pipeline.run_ai_scoring).
"""
from __future__ import annotations

from datetime import datetime, UTC

import observability.run_store as run_store
from models.schemas import AIScoreCitation, AIScoreReport, AIScoreResult


def test_save_and_load_result_round_trips_ai_score_report(tmp_path, monkeypatch):
    monkeypatch.setattr(run_store, "RUNS_DIR", tmp_path)

    ai_score_report = AIScoreReport(
        run_id="pytest-run-store", generated_at=datetime.now(UTC), mode="local_deterministic",
        scores=[AIScoreResult(
            metric_id="topic_case_count", pbrer_section_number="16.3.1.3", topic_heading="Hallucinations",
            score=0.95, present_in_source=True,
            citation=AIScoreCitation(source_type="document", document_section_number="16.3.1.3",
                                       document_section_title="Hallucinations and confusion"),
            rationale="Benchmark match.",
        )],
    )
    result = {"run_id": "pytest-run-store", "generated_at": datetime.now(UTC), "ai_score_report": ai_score_report}

    run_store.save_result("pytest-run-store", result)  # must not raise TypeError
    loaded = run_store.load_result("pytest-run-store")

    assert loaded is not None
    assert isinstance(loaded["ai_score_report"], AIScoreReport)
    assert loaded["ai_score_report"].scores[0].metric_id == "topic_case_count"
    assert loaded["ai_score_report"].scores[0].score == 0.95
