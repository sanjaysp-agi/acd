"""
Agent 4 -- Calculation Planning Agent.

Assembles an ExecutionPlan from the Document Agent, Excel Agent, and
Topic Mapping Agent outputs, validated against the APPROVED metric
registry (config.metric_registry.METRIC_REGISTRY). This agent does not
invent business rules or generate executable calculation code -- it only
decides which already-mapped columns/workbooks feed each approved
metric, and marks a step unvalidated (never executed) if required
canonical fields weren't mapped with acceptable confidence.
"""
from __future__ import annotations

from datetime import datetime, UTC

from agents.base import ToolCallingAgent
from config.metric_registry import CanonicalField, DataGrain
from llm.local_provider import LocalDeterministicProvider
from llm.provider import AgentStep, ToolSpec
from models.schemas import AgentWarning, ExecutionPlan, ExecutionPlanStep, TopicMappingResult, WorkbookInventory
from tools import plan_tools as pt


def build_plan_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec("build_execution_plan",
                 "Assemble validated execution plan steps from workbook inventory + topic mappings.",
                 {"type": "object", "properties": {
                     "document_topics": {"type": "array"}, "workbook_entries": {"type": "array"},
                     "topic_mappings": {"type": "array"}, "reporting_start": {"type": "string"},
                     "reporting_end": {"type": "string"}}},
                 pt.build_execution_plan, "python"),
    ]


PLANNER_SYSTEM_PROMPT = (
    "You are the Calculation Planning Agent. Assemble an execution plan using "
    "ONLY the approved metric registry and already-validated column mappings. "
    "Never invent a business rule or generate calculation code -- mark a step "
    "unvalidated if required fields are missing rather than guessing."
)


class CalculationPlanningAgent:
    agent_name = "calculation_planning_agent"

    def __init__(self, provider_factory=None, trace_sink=None, max_iterations: int | None = None):
        from config.settings import settings

        self.tool_specs = build_plan_tool_specs()
        self.trace_sink = trace_sink
        self.max_iterations = max_iterations if max_iterations is not None else settings.llm.max_tool_iterations
        self._provider_factory = provider_factory

    def run(self, run_id: str, document_topics: list[dict], workbook_inventory: WorkbookInventory,
            topic_mapping: TopicMappingResult, reporting_start: str, reporting_end: str) -> ExecutionPlan:
        workbook_entries = [wb.model_dump(mode="json") for wb in workbook_inventory.workbooks]
        topic_mappings = [m.model_dump(mode="json") for m in topic_mapping.mappings]

        state = {"phase": "start"}

        def policy(conversation, tools):
            if state["phase"] == "start":
                state["phase"] = "done"
                return AgentStep(type="call_tool", tool_name="build_execution_plan",
                                  arguments={"document_topics": document_topics, "workbook_entries": workbook_entries,
                                             "topic_mappings": topic_mappings, "reporting_start": reporting_start,
                                             "reporting_end": reporting_end},
                                  rationale="Assembling execution plan from validated inventory + topic mappings.")
            last_turn = conversation[-1] if conversation else {}
            return AgentStep(type="final", final_output={"plan_result": last_turn.get("structured")})

        provider = (self._provider_factory(policy) if self._provider_factory
                    else LocalDeterministicProvider(policy))
        runner = ToolCallingAgent(provider, self.tool_specs, max_iterations=self.max_iterations,
                                   trace_sink=self.trace_sink)
        runner.agent_name = self.agent_name
        result = runner.run(run_id, PLANNER_SYSTEM_PROMPT, "Build the Section 16.3 execution plan.")

        plan_result = result.output.get("plan_result") or {"steps": [], "warnings": []}
        steps = []
        for s in plan_result.get("steps", []):
            steps.append(ExecutionPlanStep(
                metric_id=s["metric_id"], pbrer_section_number=s.get("pbrer_section_number"),
                topic_heading=s.get("topic_heading", ""), source_workbook=s["source_workbook"],
                source_sheet=s["source_sheet"],
                canonical_fields=[CanonicalField(f) for f in s["canonical_fields"]],
                mapped_columns=s["mapped_columns"], date_field=s.get("date_field"),
                date_format=s.get("date_format"), reporting_start=s["reporting_start"],
                reporting_end=s["reporting_end"], applies_clinical_trials_exclusion=True,
                grain=DataGrain(s["grain"]), distinct_by=CanonicalField(s["distinct_by"]) if s.get("distinct_by") else None,
                join_requirements=s.get("join_requirements"), percentage_formula=s.get("percentage_formula"),
                header_row=s.get("header_row"), data_end_row=s.get("data_end_row"),
                validated=s.get("validated", False), validation_notes=s.get("validation_notes", []),
            ))

        warnings = [AgentWarning(code="planning_warning", severity="warning", message=w)
                    for w in plan_result.get("warnings", [])]

        return ExecutionPlan(run_id=run_id, generated_at=datetime.now(UTC), reporting_start=reporting_start,
                               reporting_end=reporting_end, steps=steps, warnings=warnings)
