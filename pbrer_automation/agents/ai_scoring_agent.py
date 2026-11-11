"""
Agent 6 -- AI Score Validation Agent.

Runs AFTER the deterministic validation/benchmark steps
(validation.calculation_validator, validation.reconciliation) have already
produced each MetricResult's validation_status and benchmark comparison.
Its job is NOT to recompute a number -- it assigns a 0.0-1.0 confidence
score to every calculated metric reflecting how well the available
evidence actually supports it, and an explicit citation (the previous/
approved PBRER's section/table, or failing that the source workbook/sheet)
so the score itself is checkable by a reviewer rather than an opaque
number. See tools/scoring_tools.compute_baseline_ai_scores for the
deterministic floor every mode runs, and agents/base.ToolCallingAgent for
why local-deterministic mode is an honest rule-based fallback rather than
a simulated model.

When PBRER_LLM_PROVIDER=bedrock, this agent is run through a real Bedrock
model (see llm.bedrock_provider / llm.factory): it can read the document
topic evidence it is given (historical_metrics, raw_table_rows) and adjust
the deterministic baseline score/citation where it has a concrete reason
to -- e.g. a historical figure that exists but under a slightly different
heading/table than the baseline matched on. It can never report
present_in_source=True without a real citation; report_ai_scores enforces
that regardless of what a provider claims (see build_scoring_tool_specs).

Output: AIScoreReport (see models.schemas).
"""
from __future__ import annotations

from datetime import datetime, UTC

from agents.base import ToolCallingAgent, last_tool_result
from llm.local_provider import LocalDeterministicProvider
from llm.provider import AgentStep, ToolSpec
from models.schemas import AIScoreReport, AIScoreResult, DocumentStructure, MetricResult
from tools import scoring_tools as st


def _clamp_score(value) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, value))


def build_scoring_tool_specs(document_topics: list[dict], metric_results: list[dict]) -> list[ToolSpec]:
    def _run_baseline(**_ignored_model_arguments):
        return st.compute_baseline_ai_scores(document_topics, metric_results)

    def _run_report(scores: list[dict] | None = None):
        scores = scores or []
        cleaned = []
        for s in scores:
            s = dict(s)
            s["score"] = _clamp_score(s.get("score"))
            citation = s.get("citation") or {}
            has_citation = bool(
                citation.get("document_section_number") or citation.get("document_section_title")
                or citation.get("source_workbook")
            )
            # present_in_source can never be True without an actual citation
            # backing it -- a provider claiming "found" with no document
            # section/title and no source workbook is downgraded to False
            # rather than trusted at face value.
            if s.get("present_in_source") and not has_citation:
                s["present_in_source"] = False
            s["citation"] = citation
            cleaned.append(s)
        return {"scores": cleaned}

    return [
        ToolSpec(
            "compute_baseline_ai_scores",
            "Compute the deterministic baseline AI confidence score for every metric result, derived "
            "from the benchmark comparison (if a historical figure exists) or the internal mandatory-"
            "check validation status otherwise. Takes no arguments -- the data is already loaded; just "
            "call it.",
            {"type": "object", "properties": {}},
            _run_baseline, "python",
        ),
        ToolSpec(
            "report_ai_scores",
            "Report the final list of AI confidence scores -- the baseline, adjusted using the document "
            "evidence you were given if you have a concrete reason to. Each score: metric_id, "
            "pbrer_section_number, topic_heading, score (0.0-1.0), present_in_source (bool -- true only "
            "if you can cite where the value appears in the source), citation (source_type: "
            "'document'|'workbook'|'none', document_section_number, document_section_title, "
            "source_workbook, source_sheet, detail), rationale.",
            {"type": "object", "properties": {"scores": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "metric_id": {"type": "string"},
                    "pbrer_section_number": {"type": ["string", "null"]},
                    "topic_heading": {"type": "string"},
                    "score": {"type": "number"},
                    "present_in_source": {"type": "boolean"},
                    "citation": {"type": "object"},
                    "rationale": {"type": "string"},
                },
                "required": ["metric_id", "score", "present_in_source", "citation"],
            }}}, "required": ["scores"]},
            _run_report, "python",
        ),
    ]


SCORING_AGENT_SYSTEM_PROMPT = (
    "You are the AI Score Validation Agent in a PBRER automation system. The deterministic calculation "
    "engine and validation checks have already run; your job is to assign a 0.0-1.0 confidence score to "
    "EVERY calculated metric, reflecting how well the available evidence actually supports it -- and to "
    "always back that score with a citation to where the evidence came from (the previous/approved "
    "PBRER's section/table, or the source workbook/sheet if no historical benchmark exists).\n\n"
    "1. Call compute_baseline_ai_scores for the deterministic baseline.\n"
    "2. Review the document topic evidence yourself (historical_metrics, raw_table_rows) for anything "
    "that should adjust a baseline score or sharpen its citation -- but never claim present_in_source=True "
    "without a concrete section/table or workbook/sheet citation.\n"
    "3. Call report_ai_scores exactly once with the complete list (baseline plus any adjustments).\n\n"
    "Then stop calling tools and reply with a brief confirmation."
)


class AIScoreAgent:
    agent_name = "ai_scoring_agent"

    def __init__(self, provider_factory=None, trace_sink=None, max_iterations: int | None = None):
        from config.settings import settings

        self.trace_sink = trace_sink
        self.max_iterations = max_iterations if max_iterations is not None else settings.llm.max_tool_iterations
        self._provider_factory = provider_factory

    def run(self, run_id: str, document_structure: DocumentStructure,
            metric_results: list[MetricResult]) -> AIScoreReport:
        document_topics = [t.model_dump(mode="json") for t in document_structure.topics]
        metric_dicts = [mr.model_dump(mode="json") for mr in metric_results]

        state = {"phase": "start"}

        def policy(conversation, tools):
            if state["phase"] == "start":
                state["phase"] = "awaiting_baseline"
                return AgentStep(type="call_tool", tool_name="compute_baseline_ai_scores", arguments={},
                                  rationale=f"Computing the deterministic AI-score baseline over "
                                            f"{len(metric_dicts)} metric result(s).")
            if state["phase"] == "awaiting_baseline":
                last_turn = conversation[-1] if conversation else {}
                baseline = (last_turn.get("structured") or {}).get("scores", [])
                state["phase"] = "done"
                return AgentStep(type="call_tool", tool_name="report_ai_scores",
                                  arguments={"scores": baseline},
                                  rationale="No real model available in local-deterministic mode -- "
                                            "reporting the deterministic baseline as-is.")
            return AgentStep(type="final", final_output={})

        provider = (self._provider_factory(policy) if self._provider_factory
                    else LocalDeterministicProvider(policy))
        tool_specs = build_scoring_tool_specs(document_topics, metric_dicts)
        runner = ToolCallingAgent(provider, tool_specs, max_iterations=self.max_iterations,
                                   trace_sink=self.trace_sink)
        runner.agent_name = self.agent_name
        result = runner.run(run_id, SCORING_AGENT_SYSTEM_PROMPT,
                             "Score every calculated Section 16.3 metric for how well the evidence "
                             "supports it, citing where that evidence comes from.")

        report = last_tool_result(result, "report_ai_scores") or {"scores": []}
        scores = [AIScoreResult.model_validate(s) for s in report.get("scores", [])]
        return AIScoreReport(run_id=run_id, generated_at=datetime.now(UTC), mode=provider.mode, scores=scores)
