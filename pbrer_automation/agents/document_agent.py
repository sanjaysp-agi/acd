"""
Agent 1 -- Document Understanding Agent.

Investigates the previous/approved PBRER Word document from raw structure:
no assumption about heading style names, whether section numbers are
literal text, or that the target section is called "16.3". The local-mode
policy is a genuine state machine that branches on what each tool call
returns (which heading-detection strategy worked, whether front matter
needed excluding, whether absolute-number calibration succeeded).

Output: DocumentStructure (see models.schemas) -- the Section 16.3-
equivalent topic catalogue with historical figures, used as development-
time ground truth for benchmark comparison. Never re-presented as a
"calculated" figure (see prompt.md Part 1: never copy historical PBRER
figures and present them as newly calculated results).
"""
from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from agents.base import ToolCallingAgent
from llm.local_provider import LocalDeterministicProvider
from llm.provider import AgentStep, ToolSpec
from models.schemas import AgentWarning, DocumentStructure, DocumentTopic
from tools import document_tools as dtools

# Candidate titles for the PBRER section that contains topic-level safety
# evaluations. This is domain configuration for "what we are looking for
# in a PBRER" (this application's whole purpose), not a guess about one
# tenant's wording -- multiple phrasings are tried because different
# PBRER templates/versions word this heading slightly differently.
TARGET_SECTION_TITLE_CANDIDATES = [
    "Evaluation of Risks and New Information",
    "Signal and Risk Evaluation",
]

# The leaf topics we want metrics for sit two levels below the target
# section header (16.3 -> 16.3.1 "New information on important identified
# risks" -> 16.3.1.1 "Cardiac failure"). This depth is a template
# convention, applied generically rather than hardcoding topic names.
LEAF_TOPIC_DEPTH_BELOW_TARGET = 2


def build_document_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec("inspect_document_metadata", "Report paragraph/table counts and style usage.",
                 {"type": "object", "properties": {"file_path": {"type": "string"}}},
                 dtools.inspect_document_metadata, "python-docx"),
        ToolSpec("sample_paragraph_styles", "Sample text per distinct paragraph style.",
                 {"type": "object", "properties": {"file_path": {"type": "string"}}},
                 dtools.sample_paragraph_styles, "python-docx"),
        ToolSpec("detect_headings", "Detect headings via style-name/outline-level/bold heuristics.",
                 {"type": "object", "properties": {"file_path": {"type": "string"}}},
                 dtools.detect_headings, "python-docx"),
        ToolSpec("exclude_front_matter_headings", "Drop leading unnumbered front-matter headings.",
                 {"type": "object", "properties": {"headings": {"type": "array"}}},
                 dtools.exclude_front_matter_headings, "python"),
        ToolSpec("reconstruct_section_numbers", "Assign relative dotted numbers via sibling counting.",
                 {"type": "object", "properties": {"headings": {"type": "array"}}},
                 dtools.reconstruct_section_numbers, "python"),
        ToolSpec("locate_target_section", "Find the heading matching known PBRER section titles.",
                 {"type": "object", "properties": {"headings_with_numbers": {"type": "array"},
                                                     "candidate_title_patterns": {"type": "array"}}},
                 dtools.locate_target_section, "python"),
        ToolSpec("calibrate_section_numbers", "Try to confirm the absolute section number via citations.",
                 {"type": "object", "properties": {"file_path": {"type": "string"},
                                                     "target_heading_text": {"type": "string"},
                                                     "target_relative_number": {"type": "string"}}},
                 dtools.calibrate_section_numbers, "python-docx"),
        ToolSpec("extract_topic_subtree", "Get all descendant headings of the target section.",
                 {"type": "object", "properties": {"headings_with_numbers": {"type": "array"},
                                                     "target_block_index": {"type": "integer"}}},
                 dtools.extract_topic_subtree, "python"),
        ToolSpec("extract_tables_near_heading", "Collect tables/paragraphs between two headings.",
                 {"type": "object", "properties": {"file_path": {"type": "string"},
                                                     "heading_block_index": {"type": "integer"},
                                                     "next_heading_block_index": {"type": ["integer", "null"]}}},
                 dtools.extract_tables_near_heading, "python-docx"),
        ToolSpec("parse_topic_historical_metrics", "Extract structured numbers from a topic's table/paragraphs.",
                 {"type": "object", "properties": {"table_rows": {"type": "array"}, "paragraphs": {"type": "array"}}},
                 dtools.parse_topic_historical_metrics, "python"),
    ]


DOCUMENT_AGENT_SYSTEM_PROMPT = (
    "You are the Document Understanding Agent in a PBRER automation system. "
    "You investigate the previous/approved PBRER Word document using only the "
    "predefined tools provided. Never assume a specific heading style name or "
    "that section numbers are literal text -- detect the actual convention this "
    "document uses, reconstruct numbering, and locate the Section 16.3-equivalent "
    "topic catalogue by content, not by assumed numbering."
)


class _DocumentPolicyState:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.phase = "start"
        self.headings: list[dict[str, Any]] = []
        self.numbered: list[dict[str, Any]] = []
        self.target: dict[str, Any] | None = None
        self.heading_strategy: str = ""
        self.subtree: list[dict[str, Any]] = []
        self.leaf_topics: list[dict[str, Any]] = []
        self.topic_queue_index = 0
        self.current_topic: dict[str, Any] | None = None
        self.current_table_rows: list[dict[str, Any]] = []
        self.current_paragraphs: list[dict[str, Any]] = []
        self.topics_out: list[DocumentTopic] = []
        self.warnings: list[AgentWarning] = []

    def next_step(self, last_result: Any, error: str | None) -> AgentStep:
        if self.phase == "start":
            self.phase = "awaiting_headings"
            return AgentStep(type="call_tool", tool_name="detect_headings",
                              arguments={"file_path": self.file_path},
                              rationale="Detect the document's own heading convention before assuming any numbering.")

        if self.phase == "awaiting_headings":
            self.heading_strategy = (last_result or {}).get("strategy", "")
            self.headings = (last_result or {}).get("headings", [])
            if not self.headings:
                self.warnings.append(AgentWarning(code="no_headings_detected",
                                                   message="No headings could be detected in the document.",
                                                   severity="critical"))
                return self._finalize()
            self.phase = "awaiting_front_matter"
            return AgentStep(type="call_tool", tool_name="exclude_front_matter_headings",
                              arguments={"headings": self.headings},
                              rationale=f"Detected {len(self.headings)} headings via '{self.heading_strategy}'; "
                                        "removing unnumbered front matter before counting siblings.")

        if self.phase == "awaiting_front_matter":
            kept = (last_result or {}).get("headings", self.headings)
            excluded = (last_result or {}).get("excluded_front_matter", [])
            if excluded:
                self.warnings.append(AgentWarning(
                    code="front_matter_excluded", severity="info",
                    message=f"Excluded {len(excluded)} front-matter heading(s) before numbering: "
                            f"{[h['text'] for h in excluded]}"))
            self.phase = "awaiting_numbering"
            return AgentStep(type="call_tool", tool_name="reconstruct_section_numbers",
                              arguments={"headings": kept},
                              rationale="Assigning relative sibling-count numbers in document order.")

        if self.phase == "awaiting_numbering":
            self.numbered = last_result or []
            self.phase = "awaiting_target_location"
            return AgentStep(type="call_tool", tool_name="locate_target_section",
                              arguments={"headings_with_numbers": self.numbered,
                                         "candidate_title_patterns": TARGET_SECTION_TITLE_CANDIDATES},
                              rationale="Locating the target section by TITLE content, not by assumed number.")

        if self.phase == "awaiting_target_location":
            result = last_result or {}
            if not result.get("found"):
                self.warnings.append(AgentWarning(
                    code="target_section_not_found", severity="critical",
                    message=f"Could not locate any heading matching {TARGET_SECTION_TITLE_CANDIDATES}."))
                return self._finalize()
            self.target = result["heading"]
            self.phase = "awaiting_calibration"
            return AgentStep(type="call_tool", tool_name="calibrate_section_numbers",
                              arguments={"file_path": self.file_path, "target_heading_text": self.target["text"],
                                         "target_relative_number": self.target["relative_number"]},
                              rationale=f"Target located: '{self.target['text']}' at relative "
                                        f"{self.target['relative_number']}; attempting absolute-number calibration.")

        if self.phase == "awaiting_calibration":
            calibration = last_result or {}
            self.target["absolute_number"] = calibration.get("absolute_number")
            self.target["calibration_confidence"] = calibration.get("confidence", 0.0)
            if not calibration.get("absolute_number"):
                self.warnings.append(AgentWarning(
                    code="section_number_unconfirmed", severity="warning",
                    message=f"Could not independently confirm the absolute section number for "
                            f"'{self.target['text']}' (relative: {self.target['relative_number']}). "
                            f"Evidence: {calibration.get('evidence')}"))
            self.phase = "awaiting_subtree"
            return AgentStep(type="call_tool", tool_name="extract_topic_subtree",
                              arguments={"headings_with_numbers": self.numbered,
                                         "target_block_index": self.target["block_index"]},
                              rationale="Extracting every descendant heading under the target section.")

        if self.phase == "awaiting_subtree":
            self.subtree = last_result or []
            target_level = self.target["level"]
            leaf_level = target_level + LEAF_TOPIC_DEPTH_BELOW_TARGET
            self.leaf_topics = [h for h in self.subtree if h["level"] == leaf_level]
            if not self.leaf_topics:
                self.warnings.append(AgentWarning(
                    code="no_leaf_topics_found", severity="warning",
                    message=f"No headings found at depth {leaf_level} under the target section; "
                            "topic catalogue may be incomplete."))
            return self._advance_to_next_topic()

        if self.phase == "awaiting_table_extraction":
            result = last_result or {"tables": [], "paragraphs": []}
            # A topic's data can be split across more than one <w:tbl>
            # element (observed on Augmentation/RLS: Post-marketing/
            # Spontaneous/Other-studies in one table, Evaluation/
            # Conclusion in a SECOND table immediately after -- likely a
            # page-break artifact in the Word doc). Using only the first
            # table silently drops the Evaluation sentence (serious/fatal
            # counts) for any topic authored this way.
            self.current_table_rows = [row for t in result.get("tables", []) for row in t["rows"]]
            self.current_paragraphs = result.get("paragraphs", [])
            self.phase = "awaiting_metrics_parse"
            return AgentStep(type="call_tool", tool_name="parse_topic_historical_metrics",
                              arguments={"table_rows": self.current_table_rows, "paragraphs": self.current_paragraphs},
                              rationale=f"Parsing historical figures for '{self.current_topic['text']}'.")

        if self.phase == "awaiting_metrics_parse":
            metrics = last_result or {}
            ct = self.current_topic
            self.topics_out.append(DocumentTopic(
                section_number=ct.get("absolute_number") or ct["relative_number"],
                section_number_confidence=ct.get("calibration_confidence", 0.3 if not ct.get("absolute_number") else 0.0),
                title=ct["text"], level=ct["level"],
                historical_metrics={k: v for k, v in metrics.items() if v is not None},
                raw_table_rows=self.current_table_rows,
                source_paragraph_index=ct["block_index"],
            ))
            return self._advance_to_next_topic()

        return self._finalize()

    def _advance_to_next_topic(self) -> AgentStep:
        if self.topic_queue_index >= len(self.leaf_topics):
            return self._finalize()
        self.current_topic = self.leaf_topics[self.topic_queue_index]
        self.topic_queue_index += 1
        all_idx = self.numbered.index(next(h for h in self.numbered if h["block_index"] == self.current_topic["block_index"]))
        next_heading = self.numbered[all_idx + 1] if all_idx + 1 < len(self.numbered) else None
        self.phase = "awaiting_table_extraction"
        return AgentStep(type="call_tool", tool_name="extract_tables_near_heading",
                          arguments={"file_path": self.file_path,
                                     "heading_block_index": self.current_topic["block_index"],
                                     "next_heading_block_index": next_heading["block_index"] if next_heading else None},
                          rationale=f"Extracting data table for topic '{self.current_topic['text']}'.")

    def _finalize(self) -> AgentStep:
        output = DocumentStructure(
            run_id="",  # filled by caller
            generated_at=datetime.now(UTC),
            document_file_name=Path(self.file_path).name,
            target_section_title=self.target["text"] if self.target else "",
            target_section_located=self.target is not None,
            heading_style_strategy=self.heading_strategy,
            topics=self.topics_out,
            warnings=self.warnings,
        )
        return AgentStep(type="final", final_output={"structure": output.model_dump(mode="json")})


class DocumentUnderstandingAgent:
    agent_name = "document_understanding_agent"

    def __init__(self, provider_factory=None, trace_sink=None, max_iterations: int | None = None):
        from config.settings import settings

        self.tool_specs = build_document_tool_specs()
        self.trace_sink = trace_sink
        self.max_iterations = max_iterations if max_iterations is not None else settings.llm.max_tool_iterations
        self._provider_factory = provider_factory

    def run(self, run_id: str, file_path: str | Path) -> DocumentStructure:
        from config.settings import settings
        from llm.cache import AnalysisCache

        cache = AnalysisCache() if settings.llm.enable_cache else None
        if cache is not None:
            cached = cache.get("document", file_path)
            if cached is not None:
                cached["run_id"] = run_id
                cached["generated_at"] = datetime.now(UTC).isoformat()
                if self.trace_sink:
                    self.trace_sink({
                        "run_id": run_id, "timestamp": datetime.now(UTC), "agent_name": self.agent_name,
                        "event_type": "analysis_cache_hit", "status": "info",
                        "message": f"Document analysis cache hit for '{Path(file_path).name}' (unchanged file "
                                    "content) -- skipped re-running the tool-calling loop.",
                    })
                return DocumentStructure.model_validate(cached)

        state = _DocumentPolicyState(str(file_path))

        def policy(conversation, tools):
            last_turn = conversation[-1] if conversation else {}
            last_result = last_turn.get("structured")
            error = last_turn.get("error")
            return state.next_step(last_result, error)

        provider = (self._provider_factory(policy) if self._provider_factory
                    else LocalDeterministicProvider(policy))
        runner = ToolCallingAgent(provider, self.tool_specs, max_iterations=self.max_iterations,
                                   trace_sink=self.trace_sink)
        runner.agent_name = self.agent_name
        result = runner.run(run_id, DOCUMENT_AGENT_SYSTEM_PROMPT, f"Investigate PBRER document: {Path(file_path).name}")

        structure_dict = result.output.get("structure")
        if structure_dict is None:
            return DocumentStructure(
                run_id=run_id, generated_at=datetime.now(UTC), document_file_name=Path(file_path).name,
                target_section_title="", target_section_located=False,
                warnings=[AgentWarning(code="agent_failed", severity="critical",
                                        message="Document Understanding Agent did not reach a final answer.")],
            )
        if cache is not None:
            cache.put("document", file_path, structure_dict)
        structure_dict["run_id"] = run_id
        return DocumentStructure.model_validate(structure_dict)
