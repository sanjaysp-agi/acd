"""
Agent 5 -- Extraction Completeness Review Agent.

Runs AFTER the Document/Excel Understanding Agents and the calculation
engine, as an independent check that nothing required was missed while
pulling values out of the source documents -- a topic with historical
figures but no calculated counterpart, a canonical field no workbook ever
mapped, a workbook that never resolved to a usable type. This is a review
of EXTRACTION COMPLETENESS, distinct from validation/calculation_validator
and validation/reconciliation (which check whether a number that WAS
produced is internally consistent / matches history).

Advisory only, by design: every finding is capped to severity 'info' or
'warning' (never 'critical'), and feeds the ValidationReport as additional
warning-level checks -- it can surface something for a human to look at,
but it can never flip a run to 'failed' on its own. An LLM judgment call
("does this look incomplete?") is not the kind of thing this pipeline lets
block a regulatory submission unattended; see check_extraction_completeness
in tools/review_tools.py for the deterministic floor every mode runs, and
agents/base.ToolCallingAgent for why local-deterministic mode is an honest
rule-based fallback rather than a simulated model.

Output: list[ExtractionReviewFinding] (see models.schemas).
"""
from __future__ import annotations

from agents.base import ToolCallingAgent, last_tool_result
from llm.local_provider import LocalDeterministicProvider
from llm.provider import AgentStep, ToolSpec
from models.schemas import DocumentStructure, ExtractionReviewFinding, MetricResult, WorkbookInventory
from tools import review_tools as rt

_ALLOWED_SEVERITIES = {"info", "warning"}


def _clamp_severity(value: str | None) -> str:
    """A finding's severity can never escalate past 'warning' -- this
    layer is advisory only, so even a provider that tries to report
    'critical' is downgraded rather than allowed to affect run status."""
    return value if value in _ALLOWED_SEVERITIES else "warning"


def build_review_tool_specs(document_topics: list[dict], workbook_entries: list[dict],
                              metric_results: list[dict]) -> list[ToolSpec]:
    def _run_baseline(**_ignored_model_arguments):
        return rt.check_extraction_completeness(document_topics, workbook_entries, metric_results)

    def _run_report(findings: list[dict] | None = None):
        findings = findings or []
        return {"findings": [{**f, "severity": _clamp_severity(f.get("severity"))} for f in findings]}

    return [
        ToolSpec(
            "check_extraction_completeness",
            "Compute the deterministic baseline of completeness findings (missing metrics for a "
            "historical topic, unmapped required fields, unclassified workbooks). Takes no arguments "
            "-- the data is already loaded; just call it.",
            {"type": "object", "properties": {}},
            _run_baseline, "python",
        ),
        ToolSpec(
            "report_review_findings",
            "Report the final list of completeness findings -- the baseline plus anything else you "
            "noticed in the provided evidence that it missed. Each finding: severity ('info' or "
            "'warning', never higher -- this review is advisory only), optional pbrer_section_number "
            "and topic_heading, and a message.",
            {"type": "object", "properties": {"findings": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["info", "warning"]},
                    "pbrer_section_number": {"type": ["string", "null"]},
                    "topic_heading": {"type": ["string", "null"]},
                    "message": {"type": "string"},
                },
                "required": ["severity", "message"],
            }}}, "required": ["findings"]},
            _run_report, "python",
        ),
    ]


REVIEW_AGENT_SYSTEM_PROMPT = (
    "You are the Extraction Completeness Review Agent in a PBRER automation system. "
    "The Document and Excel Understanding Agents have already extracted structured data; your job "
    "is to catch anything their extraction may have missed before it reaches calculation -- an "
    "incomplete topic, an unmapped required field, a workbook that never resolved to a usable type, "
    "or any other gap visible in the evidence you're given.\n\n"
    "1. Call check_extraction_completeness for the deterministic baseline.\n"
    "2. Review the topic/workbook evidence yourself for anything the baseline did not catch.\n"
    "3. Call report_review_findings exactly once with the complete list (baseline plus anything you "
    "add). Every finding's severity must be 'info' or 'warning' -- never higher; this review informs "
    "a human reviewer and must never block the pipeline.\n\n"
    "Then stop calling tools and reply with a brief confirmation."
)


class ExtractionReviewAgent:
    agent_name = "extraction_review_agent"

    def __init__(self, provider_factory=None, trace_sink=None, max_iterations: int | None = None):
        from config.settings import settings

        self.trace_sink = trace_sink
        self.max_iterations = max_iterations if max_iterations is not None else settings.llm.max_tool_iterations
        self._provider_factory = provider_factory

    def run(self, run_id: str, document_structure: DocumentStructure, workbook_inventory: WorkbookInventory,
            metric_results: list[MetricResult]) -> list[ExtractionReviewFinding]:
        document_topics = [t.model_dump(mode="json") for t in document_structure.topics]
        workbook_entries = [wb.model_dump(mode="json") for wb in workbook_inventory.workbooks]
        metric_dicts = [mr.model_dump(mode="json") for mr in metric_results]

        state = {"phase": "start", "baseline": None}

        def policy(conversation, tools):
            if state["phase"] == "start":
                state["phase"] = "awaiting_baseline"
                return AgentStep(type="call_tool", tool_name="check_extraction_completeness", arguments={},
                                  rationale=f"Computing the deterministic completeness baseline over "
                                            f"{len(document_topics)} topic(s) and {len(workbook_entries)} "
                                            "workbook(s).")
            if state["phase"] == "awaiting_baseline":
                last_turn = conversation[-1] if conversation else {}
                baseline = (last_turn.get("structured") or {}).get("findings", [])
                state["phase"] = "done"
                return AgentStep(type="call_tool", tool_name="report_review_findings",
                                  arguments={"findings": baseline},
                                  rationale="No real model available in local-deterministic mode -- "
                                            "reporting the deterministic baseline as-is.")
            return AgentStep(type="final", final_output={})

        provider = (self._provider_factory(policy) if self._provider_factory
                    else LocalDeterministicProvider(policy))
        tool_specs = build_review_tool_specs(document_topics, workbook_entries, metric_dicts)
        runner = ToolCallingAgent(provider, tool_specs, max_iterations=self.max_iterations,
                                   trace_sink=self.trace_sink)
        runner.agent_name = self.agent_name
        result = runner.run(run_id, REVIEW_AGENT_SYSTEM_PROMPT,
                             "Review the extracted PBRER data for completeness.")

        report = last_tool_result(result, "report_review_findings") or {"findings": []}
        return [ExtractionReviewFinding.model_validate(f) for f in report.get("findings", [])]
