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

from agents.base import ToolCallingAgent
from config.metric_registry import CriterionType, WorkbookType
from llm.local_provider import LocalDeterministicProvider
from llm.provider import AgentStep, ToolSpec
from models.schemas import AgentWarning, DocumentStructure, TopicMappingEntry, TopicMappingResult, WorkbookInventory
from tools import topic_tools as tt


def build_topic_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec("match_topics_to_workbooks",
                 "Greedy best-match document topics to topic-specific case workbooks by criterion overlap.",
                 {"type": "object", "properties": {"document_topics": {"type": "array"},
                                                     "case_workbooks": {"type": "array"}}},
                 tt.match_topics_to_workbooks, "python"),
    ]


TOPIC_MAPPING_SYSTEM_PROMPT = (
    "You are the Topic Mapping Agent. Connect PBRER Section 16.3 topics to the "
    "topic-specific case/drug-event workbooks that cover them, using criterion "
    "overlap evidence -- never assume a heading's number tells you which "
    "workbook belongs to it, and never force a low-confidence match."
)


class TopicMappingAgent:
    agent_name = "topic_mapping_agent"

    def __init__(self, provider_factory=None, trace_sink=None, max_iterations: int | None = None):
        from config.settings import settings

        self.tool_specs = build_topic_tool_specs()
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

        state = {"phase": "start", "result": None}

        def policy(conversation, tools):
            if state["phase"] == "start":
                state["phase"] = "done"
                return AgentStep(type="call_tool", tool_name="match_topics_to_workbooks",
                                  arguments={"document_topics": document_topics, "case_workbooks": case_workbooks},
                                  rationale=f"Matching {len(document_topics)} document topics against "
                                            f"{len(case_workbooks)} topic-specific case workbooks.")
            last_turn = conversation[-1] if conversation else {}
            return AgentStep(type="final", final_output={"match_result": last_turn.get("structured")})

        provider = (self._provider_factory(policy) if self._provider_factory
                    else LocalDeterministicProvider(policy))
        runner = ToolCallingAgent(provider, self.tool_specs, max_iterations=self.max_iterations,
                                   trace_sink=self.trace_sink)
        runner.agent_name = self.agent_name
        result = runner.run(run_id, TOPIC_MAPPING_SYSTEM_PROMPT,
                             "Map PBRER topics to Excel workbooks.")

        match_result = result.output.get("match_result") or {"mappings": [], "unmatched_workbooks": []}
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
