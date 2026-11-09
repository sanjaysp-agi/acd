"""
Pydantic schemas shared across agents, tools, calculation engine, validation
and the frontend. These are the structured contracts that make agent output
inspectable/traceable rather than free-form text.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from config.metric_registry import CanonicalField, CriterionType, DataGrain, WorkbookType


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------
class ToolCallRecord(BaseModel):
    """One actual invocation of a predefined Python tool by an agent."""

    tool_name: str
    library: str
    arguments_redacted: dict[str, Any] = Field(default_factory=dict)
    result_summary: str
    raw_result: dict[str, Any] | None = None
    timestamp: datetime | None = None
    duration_ms: float | None = None


class AgentWarning(BaseModel):
    code: str
    message: str
    severity: Literal["info", "warning", "critical"] = "warning"
    context: dict[str, Any] = Field(default_factory=dict)


class AgentRunResult(BaseModel):
    """Generic wrapper every agent returns -- feeds the traceability UI."""

    agent_name: str
    run_id: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    input_summary: str = ""
    mode: Literal["bedrock", "local_deterministic"] = "local_deterministic"
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    output: dict[str, Any] = Field(default_factory=dict)
    warnings: list[AgentWarning] = Field(default_factory=list)
    next_agent: str | None = None


# ---------------------------------------------------------------------------
# Excel Understanding Agent output
# ---------------------------------------------------------------------------
class ColumnProfile(BaseModel):
    column_name: str
    detected_type: str
    sample_values: list[str] = Field(default_factory=list)
    unique_categorical_values: list[str] | None = None
    missing_count: int = 0
    invalid_count: int = 0
    possible_date_format: str | None = None
    duplicate_count: int | None = None


class SheetInspection(BaseModel):
    sheet_name: str
    role: Literal["cover_page", "data_table", "unknown"] = "unknown"
    header_row: int | None = None
    data_start_row: int | None = None
    data_end_row: int | None = None
    footer_rows: list[int] = Field(default_factory=list)
    row_count: int | None = None
    columns: list[str] = Field(default_factory=list)
    column_profiles: list[ColumnProfile] = Field(default_factory=list)
    detection_evidence: list[str] = Field(default_factory=list)


class CoverPageCriterion(BaseModel):
    criterion_type: CriterionType = CriterionType.UNKNOWN
    criterion_value: str | None = None
    raw_fields: dict[str, str] = Field(default_factory=dict)


class ColumnMapping(BaseModel):
    raw_column: str
    canonical_field: CanonicalField | None = None
    confidence: float = 0.0
    evidence: str = ""
    needs_review: bool = False


class WorkbookInventoryEntry(BaseModel):
    file_name: str
    file_path: str
    workbook_type: WorkbookType = WorkbookType.UNCLASSIFIED
    classification_confidence: float = 0.0
    classification_evidence: list[str] = Field(default_factory=list)
    sheets: list[SheetInspection] = Field(default_factory=list)
    cover_page_criteria: CoverPageCriterion | None = None
    data_grain: DataGrain = DataGrain.UNKNOWN
    column_mappings: list[ColumnMapping] = Field(default_factory=list)
    linked_workbook: str | None = None  # matched case<->drug-event partner
    warnings: list[AgentWarning] = Field(default_factory=list)


class WorkbookInventory(BaseModel):
    run_id: str
    generated_at: datetime
    workbooks: list[WorkbookInventoryEntry] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Document Understanding Agent output
# ---------------------------------------------------------------------------
class DocumentTopic(BaseModel):
    section_number: str | None = None  # reconstructed, may be None if undeterminable
    section_number_confidence: float = 0.0
    title: str
    level: int
    historical_metrics: dict[str, Any] = Field(default_factory=dict)
    raw_table_rows: list[dict[str, str]] = Field(default_factory=list)
    source_paragraph_index: int | None = None


class DocumentStructure(BaseModel):
    run_id: str
    generated_at: datetime
    document_file_name: str
    target_section_title: str
    target_section_located: bool
    heading_style_strategy: str = ""  # "style_name" | "outline_level" | "bold_heuristic"
    topics: list[DocumentTopic] = Field(default_factory=list)
    warnings: list[AgentWarning] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Topic Mapping Agent output
# ---------------------------------------------------------------------------
class TopicMappingEntry(BaseModel):
    pbrer_section_number: str | None
    pbrer_heading: str
    excel_criterion_type: CriterionType = CriterionType.UNKNOWN
    excel_criterion_value: str | None = None
    case_workbook: str | None = None
    drug_event_workbook: str | None = None
    confidence: float = 0.0
    needs_review: bool = False
    warnings: list[AgentWarning] = Field(default_factory=list)


class TopicMappingResult(BaseModel):
    run_id: str
    generated_at: datetime
    mappings: list[TopicMappingEntry] = Field(default_factory=list)
    unmatched_workbooks: list[str] = Field(default_factory=list)
    unmatched_document_topics: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Calculation Planning Agent output
# ---------------------------------------------------------------------------
class ExecutionPlanStep(BaseModel):
    metric_id: str
    pbrer_section_number: str | None
    topic_heading: str
    source_workbook: str
    source_sheet: str
    canonical_fields: list[CanonicalField]
    mapped_columns: dict[str, str]  # canonical_field -> actual column name
    date_field: str | None
    date_format: str | None
    reporting_start: str
    reporting_end: str
    applies_clinical_trials_exclusion: bool = True
    grain: DataGrain
    distinct_by: CanonicalField | None
    join_requirements: str | None = None
    percentage_formula: str | None = None
    header_row: int | None = None
    data_end_row: int | None = None
    validated: bool = False
    validation_notes: list[str] = Field(default_factory=list)


class ExecutionPlan(BaseModel):
    run_id: str
    generated_at: datetime
    reporting_start: str
    reporting_end: str
    steps: list[ExecutionPlanStep] = Field(default_factory=list)
    warnings: list[AgentWarning] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Calculation results + validation/audit
# ---------------------------------------------------------------------------
class CalculationEvidence(BaseModel):
    source_workbook: str
    source_sheet: str
    header_row: int | None
    case_id_column: str | None
    date_column: str | None
    date_format: str | None
    reporting_start: str
    reporting_end: str
    source_exclusion_applied: bool
    source_exclusion_values_matched: list[str] = Field(default_factory=list)
    rows_before_filter: int
    rows_after_filter: int
    distinct_case_count: int | None = None
    event_row_count: int | None = None
    calculation_function: str
    extra: dict[str, Any] = Field(default_factory=dict)


class MetricResult(BaseModel):
    metric_id: str
    pbrer_section_number: str | None
    topic_heading: str
    calculated_value: Any
    historical_value: Any = None
    difference: Any = None
    unit: str = "count"
    evidence: CalculationEvidence
    validation_status: Literal["verified", "warning", "failed", "unverified"] = "unverified"
    validation_messages: list[str] = Field(default_factory=list)


class ValidationCheckResult(BaseModel):
    check_name: str
    status: Literal["pass", "warning", "fail"]
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class ValidationReport(BaseModel):
    run_id: str
    generated_at: datetime
    checks: list[ValidationCheckResult] = Field(default_factory=list)
    metric_results: list[MetricResult] = Field(default_factory=list)
    overall_status: Literal["verified", "warning", "failed"] = "warning"


class BenchmarkRow(BaseModel):
    metric_label: str
    expected: Any
    calculated: Any
    difference: Any
    status: Literal["match", "mismatch", "unverified"]


class BenchmarkReport(BaseModel):
    run_id: str
    generated_at: datetime
    rows: list[BenchmarkRow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Independent topic reconstruction / cross-validation (prompt.md Part 2
# Agent 3 lines 378-394; Part 5 mandatory check #13)
# ---------------------------------------------------------------------------
class TopicReconstructionResult(BaseModel):
    pbrer_section_number: str | None
    topic_heading: str
    feasible: bool
    reason: str = ""
    criterion_type: CriterionType = CriterionType.UNKNOWN
    criterion_value: str | None = None
    reconstructed_case_count: int | None = None
    reconstructed_event_row_count: int | None = None
    topic_export_case_count: int | None = None
    comparison: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Traceability / observability
# ---------------------------------------------------------------------------
class TraceEvent(BaseModel):
    run_id: str
    timestamp: datetime
    agent_name: str
    event_type: str
    tool_name: str | None = None
    arguments_redacted: dict[str, Any] = Field(default_factory=dict)
    result_summary: str | None = None
    structured_output: dict[str, Any] | None = None
    status: Literal["info", "success", "warning", "error"] = "info"
    message: str | None = None
