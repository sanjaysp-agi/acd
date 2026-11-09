"""
Agent 2 -- Excel Understanding Agent.

Investigates every uploaded workbook from raw structure, with NO
assumption about sheet count, header offset, or column set. The
local-mode policy below is a genuine state machine that branches on what
each tool call actually returns (how many sheets a workbook has, whether
a sheet structurally looks like a cover page vs. a data table, whether a
column mapping needs review) -- it is not a fixed script that happens to
match this development tenant's 10 files.

Output: WorkbookInventory (see models.schemas), one entry per workbook,
plus cross-workbook case<->drug-event pairing.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from agents.base import ToolCallingAgent
from config.metric_registry import CanonicalField, CriterionType, DataGrain, WorkbookType
from llm.local_provider import LocalDeterministicProvider
from llm.provider import AgentStep, ToolSpec
from models.schemas import (
    AgentWarning,
    ColumnMapping,
    ColumnProfile,
    CoverPageCriterion,
    SheetInspection,
    WorkbookInventory,
    WorkbookInventoryEntry,
)
from tools import excel_tools as et


# ---------------------------------------------------------------------------
# Sheet-role heuristic: a decision the AGENT makes by interpreting
# inspect_sheet's raw structural output, not a new "tool". A cover page in
# this exporter family (and plausibly others) is narrow (few populated
# columns) and dominated by label/value pairs; a data table is wide and
# has a large row count relative to its header.
# ---------------------------------------------------------------------------
def _guess_sheet_role(sheet_inspection: dict[str, Any]) -> str:
    max_col = sheet_inspection["max_col"]
    max_row = sheet_inspection["max_row"]
    head_rows = sheet_inspection["head_rows"]
    if max_col <= 6 and max_row <= 40:
        return "cover_page"
    if max_row > 40 and max_col > 6:
        return "data_table"
    # Ambiguous: look for colon/label-heavy rows as a cover-page signal.
    label_like = 0
    for values in head_rows.values():
        strs = [v for v in values if isinstance(v, str)]
        if strs and sum(1 for s in strs if len(s) < 60) / max(len(strs), 1) > 0.7:
            label_like += 1
    return "cover_page" if label_like > len(head_rows) * 0.5 else "data_table"


class _WorkbookPolicyState:
    """Per-workbook investigation state machine for local/deterministic mode."""

    def __init__(self, file_path: str, file_name: str):
        self.file_path = file_path
        self.file_name = file_name
        self.sheets_to_visit: list[str] = []
        self.sheet_queue_index = 0
        self.current_sheet: str | None = None
        self.current_sheet_inspection: dict[str, Any] | None = None
        self.current_role: str | None = None
        self.current_header_row: int | None = None
        self.current_columns: list[str] = []
        self.current_profiles: list[dict[str, Any]] = []
        self.current_footer_info: dict[str, Any] | None = None
        self.phase = "start"  # start -> inspect_workbook -> per-sheet phases -> classify -> done
        self.sheet_results: dict[str, SheetInspection] = {}
        self.cover_page_criteria: CoverPageCriterion | None = None
        self.warnings: list[AgentWarning] = []

    def next_step(self, last_tool_name: str | None, last_result: Any, error: str | None) -> AgentStep:
        if self.phase == "start":
            self.phase = "awaiting_workbook_inspection"
            return AgentStep(type="call_tool", tool_name="inspect_workbook",
                              arguments={"file_path": self.file_path},
                              rationale="Discover sheet names and sizes before assuming any structure.")

        if self.phase == "awaiting_workbook_inspection":
            if error or not last_result:
                self.warnings.append(AgentWarning(code="workbook_inspect_failed",
                                                   message=f"Could not inspect {self.file_name}: {error}",
                                                   severity="critical"))
                return self._finalize()
            self.sheets_to_visit = [s["sheet_name"] for s in last_result["sheets"]]
            return self._advance_to_next_sheet()

        if self.phase == "awaiting_sheet_inspection":
            self.current_sheet_inspection = last_result
            self.current_role = _guess_sheet_role(last_result)
            if self.current_role == "cover_page":
                self.phase = "awaiting_cover_page_criteria"
                return AgentStep(type="call_tool", tool_name="extract_cover_page_criteria",
                                  arguments={"file_path": self.file_path, "sheet_name": self.current_sheet},
                                  rationale=f"Sheet '{self.current_sheet}' looks like a cover page (narrow, label-heavy); "
                                            "extracting its search criteria.")
            self.phase = "awaiting_header_detection"
            return AgentStep(type="call_tool", tool_name="detect_header_row",
                              arguments={"sheet_inspection": last_result},
                              rationale=f"Sheet '{self.current_sheet}' looks like a data table; locating its real header row.")

        if self.phase == "awaiting_cover_page_criteria":
            raw = last_result or {}
            self.cover_page_criteria = CoverPageCriterion(
                criterion_type=CriterionType(raw.get("criterion_type", "unknown")),
                criterion_value=raw.get("criterion_value"),
                raw_fields=raw.get("raw_fields", {}),
            )
            self.sheet_results[self.current_sheet] = SheetInspection(
                sheet_name=self.current_sheet, role="cover_page",
                detection_evidence=["classified as cover page by structural heuristic"],
            )
            return self._advance_to_next_sheet()

        if self.phase == "awaiting_header_detection":
            header_row = (last_result or {}).get("header_row")
            if header_row is None:
                self.warnings.append(AgentWarning(
                    code="header_not_found",
                    message=f"No viable header row found in {self.current_sheet} of {self.file_name}.",
                    severity="critical"))
                self.sheet_results[self.current_sheet] = SheetInspection(
                    sheet_name=self.current_sheet, role="unknown",
                    detection_evidence=["header detection failed"],
                )
                return self._advance_to_next_sheet()
            self.current_header_row = header_row
            self.phase = "awaiting_data_region"
            return AgentStep(type="call_tool", tool_name="detect_data_region",
                              arguments={"file_path": self.file_path, "sheet_name": self.current_sheet,
                                         "header_row": header_row},
                              rationale=f"Header row {header_row} detected (confidence "
                                        f"{(last_result or {}).get('confidence', 0):.2f}); establishing data boundary.")

        if self.phase == "awaiting_data_region":
            self.current_columns = (last_result or {}).get("columns", [])
            self.phase = "awaiting_footer_detection"
            return AgentStep(type="call_tool", tool_name="detect_footer_rows",
                              arguments={"file_path": self.file_path, "sheet_name": self.current_sheet,
                                         "header_row": self.current_header_row},
                              rationale="Checking for trailing footer/boilerplate rows before trusting the row count.")

        if self.phase == "awaiting_footer_detection":
            self.current_footer_info = last_result or {}
            data_end_row = self.current_footer_info.get("effective_last_data_row")
            self.phase = "awaiting_column_profiles"
            return AgentStep(type="call_tool", tool_name="profile_columns",
                              arguments={"file_path": self.file_path, "sheet_name": self.current_sheet,
                                         "header_row": self.current_header_row,
                                         "data_end_row": (data_end_row + 1) if data_end_row else None},
                              rationale=f"Footer rows identified: {self.current_footer_info.get('footer_rows')}; "
                                        "profiling columns over the real data region only.")

        if self.phase == "awaiting_column_profiles":
            self.current_profiles = last_result or []
            self.phase = "awaiting_column_mapping"
            return AgentStep(type="call_tool", tool_name="map_columns_to_schema",
                              arguments={"columns": self.current_columns, "column_profiles": self.current_profiles},
                              rationale="Mapping raw headers onto the canonical schema using name + value evidence.")

        if self.phase == "awaiting_column_mapping":
            mappings = last_result or []
            for m in mappings:
                if m.get("needs_review"):
                    self.warnings.append(AgentWarning(
                        code="low_confidence_mapping",
                        message=f"Column '{m['raw_column']}' in {self.current_sheet} ({self.file_name}) "
                                f"needs review: {m.get('evidence')}",
                        severity="warning",
                    ))
            self.sheet_results[self.current_sheet] = SheetInspection(
                sheet_name=self.current_sheet, role="data_table",
                header_row=self.current_header_row,
                data_start_row=(self.current_header_row or 0) + 1,
                data_end_row=self.current_footer_info.get("effective_last_data_row") if self.current_footer_info else None,
                footer_rows=self.current_footer_info.get("footer_rows", []) if self.current_footer_info else [],
                row_count=(self.current_footer_info.get("effective_last_data_row", 0) - (self.current_header_row or 0))
                if self.current_footer_info else None,
                columns=self.current_columns,
                column_profiles=[ColumnProfile(**p) for p in self.current_profiles],
                detection_evidence=[f"header_row={self.current_header_row}"],
            )
            self._column_mappings = mappings

            # Part 3 Rule A: the column mapped onto the canonical reporting-date
            # field is the one that actually drives every downstream reporting-
            # period filter, so its detected format is independently re-validated
            # with the dedicated detect_date_formats tool (not just the inline
            # guess made inside profile_columns) -- an ambiguous result is
            # surfaced as a warning requiring review rather than silently trusted.
            date_mapping = next((m for m in mappings
                                  if m.get("canonical_field") == CanonicalField.INITIAL_APPROVAL_DATE.value), None)
            if date_mapping:
                profile = next((p for p in self.current_profiles if p["column_name"] == date_mapping["raw_column"]), None)
                if profile is not None:
                    self._pending_date_mapping = date_mapping
                    self.phase = "awaiting_date_format_detection"
                    return AgentStep(type="call_tool", tool_name="detect_date_formats",
                                      arguments={"sample_values": profile.get("sample_values", [])},
                                      rationale=f"Independently validating the detected date format for the "
                                                f"mapped initial-approval-date column '{date_mapping['raw_column']}'.")
            return self._advance_to_next_sheet()

        if self.phase == "awaiting_date_format_detection":
            detection = last_result or {}
            date_mapping = getattr(self, "_pending_date_mapping", None)
            sheet = self.sheet_results.get(self.current_sheet)
            if sheet and date_mapping:
                for p in sheet.column_profiles:
                    if p.column_name == date_mapping["raw_column"] and detection.get("format"):
                        p.possible_date_format = detection["format"]
                        break
                sheet.detection_evidence.append(
                    f"detect_date_formats({date_mapping['raw_column']})={detection.get('format')} "
                    f"(confidence {detection.get('confidence', 0):.2f})")
            if detection.get("confidence", 1.0) < 0.6:
                self.warnings.append(AgentWarning(
                    code="ambiguous_date_format",
                    message=f"Date column '{date_mapping['raw_column'] if date_mapping else '?'}' in "
                            f"{self.current_sheet} ({self.file_name}) has an ambiguous detected format "
                            f"({detection.get('format')}, confidence {detection.get('confidence')}) -- requires review.",
                    severity="warning",
                ))
            return self._advance_to_next_sheet()

        return self._finalize()

    def _advance_to_next_sheet(self) -> AgentStep:
        if self.sheet_queue_index >= len(self.sheets_to_visit):
            return self._finalize()
        self.current_sheet = self.sheets_to_visit[self.sheet_queue_index]
        self.sheet_queue_index += 1
        self.phase = "awaiting_sheet_inspection"
        return AgentStep(type="call_tool", tool_name="inspect_sheet",
                          arguments={"file_path": self.file_path, "sheet_name": self.current_sheet},
                          rationale=f"Inspecting raw cell structure of sheet '{self.current_sheet}' before classifying it.")

    def _finalize(self) -> AgentStep:
        data_sheet = next((s for s in self.sheet_results.values() if s.role == "data_table"), None)
        columns = data_sheet.columns if data_sheet else []
        criterion_value = self.cover_page_criteria.criterion_value if self.cover_page_criteria else None
        self.phase = "awaiting_classification"
        return AgentStep(type="call_tool", tool_name="classify_workbook",
                          arguments={"columns": columns, "cover_page_criterion_value": criterion_value},
                          rationale="All sheets inspected; classifying workbook type from accumulated evidence.")

    def finalize_with_classification(self, classification: dict[str, Any]) -> AgentStep:
        mappings = getattr(self, "_column_mappings", [])
        entry = WorkbookInventoryEntry(
            file_name=self.file_name,
            file_path=self.file_path,
            workbook_type=WorkbookType(classification["workbook_type"]),
            classification_confidence=classification["confidence"],
            classification_evidence=classification["evidence"],
            sheets=list(self.sheet_results.values()),
            cover_page_criteria=self.cover_page_criteria,
            data_grain=DataGrain(classification["data_grain"]),
            column_mappings=[ColumnMapping(**m) for m in mappings],
            warnings=self.warnings,
        )
        return AgentStep(type="final", final_output={"entry": entry.model_dump(mode="json")})


def build_excel_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec("inspect_workbook", "Open a workbook; list its sheets, sizes, merges.",
                 {"type": "object", "properties": {"file_path": {"type": "string"}}}, et.inspect_workbook, "openpyxl"),
        ToolSpec("inspect_sheet", "Read raw cell values/merges for a sheet.",
                 {"type": "object", "properties": {"file_path": {"type": "string"}, "sheet_name": {"type": "string"}}},
                 et.inspect_sheet, "openpyxl"),
        ToolSpec("detect_header_row", "Score candidate header rows from a sheet inspection.",
                 {"type": "object", "properties": {"sheet_inspection": {"type": "object"}}},
                 et.detect_header_row, "openpyxl+pandas"),
        ToolSpec("detect_data_region", "Load the sheet with the detected header to get real columns/row count.",
                 {"type": "object", "properties": {"file_path": {"type": "string"}, "sheet_name": {"type": "string"},
                                                     "header_row": {"type": "integer"}}},
                 et.detect_data_region, "pandas"),
        ToolSpec("detect_footer_rows", "Identify trailing footer/boilerplate rows to exclude.",
                 {"type": "object", "properties": {"file_path": {"type": "string"}, "sheet_name": {"type": "string"},
                                                     "header_row": {"type": "integer"}}},
                 et.detect_footer_rows, "pandas"),
        ToolSpec("profile_columns", "Profile every column's type, samples, missing/invalid counts.",
                 {"type": "object", "properties": {"file_path": {"type": "string"}, "sheet_name": {"type": "string"},
                                                     "header_row": {"type": "integer"}, "data_end_row": {"type": ["integer", "null"]}}},
                 et.profile_columns, "pandas"),
        ToolSpec("detect_date_formats", "Independently determine the likely date format for a candidate "
                 "date column from its raw sample values.",
                 {"type": "object", "properties": {"sample_values": {"type": "array"}}},
                 et.detect_date_formats, "pandas"),
        ToolSpec("extract_cover_page_criteria", "Scan a cover-page sheet for label:value search criteria.",
                 {"type": "object", "properties": {"file_path": {"type": "string"}, "sheet_name": {"type": "string"}}},
                 et.extract_cover_page_criteria, "openpyxl"),
        ToolSpec("classify_workbook", "Classify a workbook as all/topic case or drug-event.",
                 {"type": "object", "properties": {"columns": {"type": "array"}, "cover_page_criterion_value": {"type": ["string", "null"]}}},
                 et.classify_workbook, "python"),
        ToolSpec("map_columns_to_schema", "Map raw columns onto the canonical schema.",
                 {"type": "object", "properties": {"columns": {"type": "array"}, "column_profiles": {"type": "array"}}},
                 et.map_columns_to_schema, "python"),
    ]


EXCEL_AGENT_SYSTEM_PROMPT = (
    "You are the Excel Understanding Agent in a PBRER automation system. "
    "You investigate ONE Excel workbook at a time using only the predefined tools "
    "provided. Never assume a fixed sheet count, header row, or column set -- "
    "always inspect first, then decide. Classify the workbook's type and map its "
    "columns onto the canonical schema, flagging anything uncertain for review."
)


class ExcelUnderstandingAgent:
    agent_name = "excel_understanding_agent"

    def __init__(self, provider_factory=None, trace_sink=None, max_iterations: int | None = None, max_workers: int = 10):
        from config.settings import settings

        self.tool_specs = build_excel_tool_specs()
        self.trace_sink = trace_sink
        self.max_iterations = max_iterations if max_iterations is not None else settings.llm.max_tool_iterations
        self.max_workers = max_workers
        self._provider_factory = provider_factory  # callable(policy) -> ToolCallingProvider
        self._trace_lock = threading.Lock()

    def _thread_safe_trace_sink(self, event: dict[str, Any]) -> None:
        if self.trace_sink is None:
            return
        with self._trace_lock:
            self.trace_sink(event)

    def _make_runner(self, policy) -> ToolCallingAgent:
        provider = (self._provider_factory(policy) if self._provider_factory
                    else LocalDeterministicProvider(policy))
        # Each workbook gets its own ToolCallingAgent/provider/policy instance
        # (all local to this call), so concurrent investigate_workbook() calls
        # from different threads never share mutable state -- only the trace
        # sink and the caller's `entries` list are shared, both guarded.
        runner = ToolCallingAgent(provider, self.tool_specs, max_iterations=self.max_iterations,
                                   trace_sink=self._thread_safe_trace_sink)
        runner.agent_name = self.agent_name
        return runner

    def investigate_workbook(self, run_id: str, file_path: str, file_name: str) -> dict[str, Any]:
        from config.settings import settings
        from llm.cache import AnalysisCache

        cache = AnalysisCache() if settings.llm.enable_cache else None
        if cache is not None:
            cached_entry = cache.get("workbook", file_path)
            if cached_entry is not None:
                cached_entry["file_path"] = file_path  # current run's path, not whatever cached it
                self._thread_safe_trace_sink({
                    "run_id": run_id, "timestamp": datetime.now(UTC), "agent_name": self.agent_name,
                    "event_type": "analysis_cache_hit", "status": "info",
                    "message": f"Workbook analysis cache hit for '{file_name}' (unchanged file content) "
                                "-- skipped re-running the per-workbook investigation loop.",
                })
                return {"agent_result": None, "entry": cached_entry}

        state = _WorkbookPolicyState(file_path, file_name)

        def policy(conversation, tools):
            last_turn = conversation[-1] if conversation else {}
            last_tool_name = last_turn.get("tool_name")
            last_result = last_turn.get("structured")
            error = last_turn.get("error")
            if state.phase == "awaiting_classification":
                return state.finalize_with_classification(last_result or {})
            return state.next_step(last_tool_name, last_result, error)

        runner = self._make_runner(policy)
        result = runner.run(run_id, EXCEL_AGENT_SYSTEM_PROMPT,
                             f"Investigate workbook: {file_name}")
        entry = result.output.get("entry")
        if cache is not None and entry is not None:
            cache.put("workbook", file_path, entry)
        return {"agent_result": result, "entry": entry}

    def run(self, run_id: str, input_dir: str | Path) -> WorkbookInventory:
        files = et.discover_excel_files(input_dir)
        if not files:
            return WorkbookInventory(run_id=run_id, generated_at=datetime.now(UTC), workbooks=[])

        # Workbooks are investigated independently (no shared state across
        # files), so they run concurrently -- capped at max_workers (default
        # 10) so a large batch doesn't spin up an unbounded number of
        # threads. This matters in practice: the all-case/all-drug-event
        # workbooks here have 28k-63k rows each and dominate wall-clock time
        # if processed sequentially after the small topic-specific ones.
        results_by_index: dict[int, dict[str, Any]] = {}
        worker_count = max(1, min(self.max_workers, len(files)))
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            future_to_index = {
                pool.submit(self.investigate_workbook, run_id, f["file_path"], f["file_name"]): i
                for i, f in enumerate(files)
            }
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    results_by_index[idx] = future.result()
                except Exception as exc:  # noqa: BLE001 -- one workbook failing must not drop the others
                    results_by_index[idx] = {"agent_result": None, "entry": None, "error": str(exc)}

        entries = []
        for i in range(len(files)):  # preserve original discovery order, not completion order
            outcome = results_by_index.get(i) or {}
            if outcome.get("entry"):
                entries.append(WorkbookInventoryEntry.model_validate(outcome["entry"]))

        case_entries = [e.model_dump() for e in entries if e.workbook_type in (WorkbookType.ALL_CASE, WorkbookType.TOPIC_CASE)]
        event_entries = [e.model_dump() for e in entries if e.workbook_type in (WorkbookType.ALL_DRUG_EVENT, WorkbookType.TOPIC_DRUG_EVENT)]
        pairs = et.match_workbooks(case_entries, event_entries)
        pair_map = {p["case_workbook"]: p["drug_event_workbook"] for p in pairs}
        for e in entries:
            if e.file_name in pair_map:
                e.linked_workbook = pair_map[e.file_name]

        return WorkbookInventory(run_id=run_id, generated_at=datetime.now(UTC), workbooks=entries)
