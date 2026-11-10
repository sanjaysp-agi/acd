"""
Agent 3 -- Topic Mapping Agent.

Connects the Document Agent's topic catalogue (models.schemas.
DocumentStructure) to the Excel Agent's workbook inventory
(models.schemas.WorkbookInventory). Does not assume a PBRER heading's
wording matches an Excel search criterion's wording exactly -- see
tools/topic_tools.py for the term-overlap scoring this relies on.

Output: TopicMappingResult.
"""
from __future__ import annotations

from datetime import datetime, UTC

from agents.base import ToolCallingAgent, last_tool_result
from config.metric_registry import CriterionType, WorkbookType
from llm.local_provider import LocalDeterministicProvider
from llm.provider import AgentStep, ToolSpec
from models.schemas import AgentWarning, DocumentStructure, TopicMappingEntry, TopicMappingResult, WorkbookInventory
from tools import topic_tools as tt


def build_topic_tool_specs(document_topics: list[dict], case_workbooks: list[dict]) -> list[ToolSpec]:
    """The tool's real arguments are bound here via closure rather than
    supplied by whatever calls it. A model-driven provider only has to
    decide to call this tool -- it is never asked to retype the full
    document_topics/case_workbooks arrays as JSON (risking truncation on
    a large run); local-deterministic mode gets the same real data for
    free. See agents.base.last_tool_result, which is what actually reads
    this tool's output back out afterward."""
    def _run(**_ignored_model_arguments):
        return tt.match_topics_to_workbooks(document_topics, case_workbooks)

    return [
        ToolSpec("match_topics_to_workbooks",
                 "Match PBRER topics to topic-specific case workbooks by criterion overlap. "
                 "Takes no arguments -- the topic and workbook data is already loaded; just call it.",
                 {"type": "object", "properties": {}},
                 _run, "python"),
    ]


TOPIC_MAPPING_SYSTEM_PROMPT = (
    "You are the Topic Mapping Agent. Connect PBRER Section 16.3 topics to the "
    "topic-specific case/drug-event workbooks that cover them, using criterion "
    "overlap evidence -- never assume a heading's number tells you which "
    "workbook belongs to it, and never force a low-confidence match. Call "
    "match_topics_to_workbooks (it needs no arguments) to get the real match "
    "result, then finish."
)


class TopicMappingAgent:
    agent_name = "topic_mapping_agent"

    def __init__(self, provider_factory=None, trace_sink=None, max_iterations: int | None = None):
        from config.settings import settings

        self.trace_sink = trace_sink
        self.max_iterations = max_iterations if max_iterations is not None else settings.llm.max_tool_iterations
        self._provider_factory = provider_factory

    def run(self, run_id: str, document_structure: DocumentStructure,
            workbook_inventory: WorkbookInventory) -> TopicMappingResult:
        case_workbooks = [
            wb.model_dump(mode="json") for wb in workbook_inventory.workbooks
            if wb.workbook_type == WorkbookType.TOPIC_CASE
        ]
        document_topics = [t.model_dump(mode="json") for t in document_structure.topics]

        state = {"phase": "start"}

        def policy(conversation, tools):
            if state["phase"] == "start":
                state["phase"] = "done"
                return AgentStep(type="call_tool", tool_name="match_topics_to_workbooks", arguments={},
                                  rationale=f"Matching {len(document_topics)} document topics against "
                                            f"{len(case_workbooks)} topic-specific case workbooks.")
            return AgentStep(type="final", final_output={})

        provider = (self._provider_factory(policy) if self._provider_factory
                    else LocalDeterministicProvider(policy))
        tool_specs = build_topic_tool_specs(document_topics, case_workbooks)
        runner = ToolCallingAgent(provider, tool_specs, max_iterations=self.max_iterations,
                                   trace_sink=self.trace_sink)
        runner.agent_name = self.agent_name
        result = runner.run(run_id, TOPIC_MAPPING_SYSTEM_PROMPT,
                             "Map PBRER topics to Excel workbooks.")

        match_result = (last_tool_result(result, "match_topics_to_workbooks")
                         or {"mappings": [], "unmatched_workbooks": []})
        mappings = []
        unmatched_topics = []
        for m in match_result.get("mappings", []):
            entry = TopicMappingEntry(
                pbrer_section_number=m.get("pbrer_section_number"),
                pbrer_heading=m.get("pbrer_heading", ""),
                excel_criterion_type=CriterionType(m.get("excel_criterion_type", "unknown")),
                excel_criterion_value=m.get("excel_criterion_value"),
                case_workbook=m.get("case_workbook"),
                drug_event_workbook=m.get("drug_event_workbook"),
                confidence=m.get("confidence", 0.0),
                needs_review=m.get("needs_review", True),
            )
            if entry.case_workbook is None:
                unmatched_topics.append(entry.pbrer_heading)
                entry.warnings.append(AgentWarning(
                    code="no_workbook_match", severity="warning",
                    message=f"No Excel workbook found for topic '{entry.pbrer_heading}' -- "
                            "this topic will not have calculated figures."))
            mappings.append(entry)

        return TopicMappingResult(
            run_id=run_id, generated_at=datetime.now(UTC), mappings=mappings,
            unmatched_workbooks=match_result.get("unmatched_workbooks", []),
            unmatched_document_topics=unmatched_topics,
        )
