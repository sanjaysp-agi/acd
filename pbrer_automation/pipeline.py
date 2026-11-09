"""
Top-level pipeline: ties the four understanding/planning agents to the
deterministic calculation engine and the validation/benchmark modules.
This is what the Streamlit frontend (and tests) call -- a single place
that reflects the real run order from prompt.md Part 10.
"""
from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from agents.calculation_planner import CalculationPlanningAgent
from agents.document_agent import DocumentUnderstandingAgent
from agents.excel_agent import ExcelUnderstandingAgent
from agents.topic_mapping_agent import TopicMappingAgent
from config.metric_registry import CanonicalField, WorkbookType
from models.schemas import DocumentStructure, ExecutionPlan, TopicMappingResult, WorkbookInventory
from processing.topic_calculator import calculate_percentages, calculate_topic_case_metrics, calculate_topic_event_metrics
from validation.calculation_validator import build_metric_result
from validation.reconciliation import build_benchmark_report


def _wb_lookup(workbook_inventory: WorkbookInventory) -> dict[str, Any]:
    return {wb.file_name: wb for wb in workbook_inventory.workbooks}


def _wb_path(workbook_inventory: WorkbookInventory, input_dir: str | Path, file_name: str) -> str:
    return str(Path(input_dir) / file_name)


def run_calculation_engine(execution_plan: ExecutionPlan, workbook_inventory: WorkbookInventory,
                             document_topics_by_section: dict[str, dict], input_dir: str | Path) -> list:
    """Groups execution plan steps by topic (section number) and runs the
    actual pandas calculations, producing MetricResult objects with full
    audit evidence. Steps marked validated=False are skipped entirely --
    never executed with guessed columns."""
    wb_lookup = _wb_lookup(workbook_inventory)
    steps_by_topic: dict[str | None, list] = {}
    for step in execution_plan.steps:
        steps_by_topic.setdefault(step.pbrer_section_number, []).append(step)

    results = []
    for section_number, steps in steps_by_topic.items():
        by_metric = {s.metric_id: s for s in steps}
        case_metrics = None
        case_step = by_metric.get("topic_case_count") or by_metric.get("total_case_count")
        if case_step and case_step.validated:
            case_metrics = calculate_topic_case_metrics(
                case_file_path=_wb_path(workbook_inventory, input_dir, case_step.source_workbook),
                case_sheet=case_step.source_sheet, case_header_row=case_step.header_row,
                case_id_col=case_step.mapped_columns[CanonicalField.CASE_ID.value],
                date_col=case_step.mapped_columns[CanonicalField.INITIAL_APPROVAL_DATE.value],
                source_col=case_step.mapped_columns[CanonicalField.PRIMARY_SOURCE.value],
                reporting_start=case_step.reporting_start, reporting_end=case_step.reporting_end,
                data_end_row=case_step.data_end_row,
            )
            historical = (document_topics_by_section.get(section_number) or {}).get("historical_metrics", {})
            historical_count = historical.get("topic_count") if section_number else historical.get("total_count")
            results.append(build_metric_result(
                metric_id=case_step.metric_id, pbrer_section_number=section_number,
                topic_heading=case_step.topic_heading, calculated_value=case_metrics["case_count"],
                source_workbook=case_step.source_workbook, source_sheet=case_step.source_sheet,
                header_row=case_step.header_row, case_id_column=case_step.mapped_columns.get(CanonicalField.CASE_ID.value),
                date_column=case_step.mapped_columns.get(CanonicalField.INITIAL_APPROVAL_DATE.value),
                date_format=case_step.date_format, reporting_start=case_step.reporting_start,
                reporting_end=case_step.reporting_end, evidence={**case_metrics["evidence"],
                                                                    "distinct_case_count": case_metrics["case_count"]},
                calculation_function="processing.topic_calculator.calculate_topic_case_metrics",
                step_validated=True, historical_value=historical_count,
            ))

        event_metrics = None
        event_step = by_metric.get("serious_case_count")
        if event_step and event_step.validated and case_metrics is not None:
            event_metrics = calculate_topic_event_metrics(
                event_file_path=_wb_path(workbook_inventory, input_dir, event_step.source_workbook),
                event_sheet=event_step.source_sheet, event_header_row=event_step.header_row,
                case_id_col=event_step.mapped_columns[CanonicalField.CASE_ID.value],
                date_col=event_step.mapped_columns[CanonicalField.INITIAL_APPROVAL_DATE.value],
                source_col=event_step.mapped_columns[CanonicalField.PRIMARY_SOURCE.value],
                event_seriousness_col=event_step.mapped_columns[CanonicalField.EVENT_SERIOUSNESS.value],
                event_death_col=event_step.mapped_columns[CanonicalField.EVENT_DEATH.value],
                event_pt_col=event_step.mapped_columns[CanonicalField.EVENT_PT.value],
                reporting_start=event_step.reporting_start, reporting_end=event_step.reporting_end,
                eligible_case_ids=case_metrics["eligible_case_ids"], data_end_row=event_step.data_end_row,
            )
            historical = (document_topics_by_section.get(section_number) or {}).get("historical_metrics", {})

            results.append(build_metric_result(
                metric_id="serious_case_count", pbrer_section_number=section_number,
                topic_heading=event_step.topic_heading, calculated_value=event_metrics["serious_case_count"],
                source_workbook=event_step.source_workbook, source_sheet=event_step.source_sheet,
                header_row=event_step.header_row, case_id_column=event_step.mapped_columns.get(CanonicalField.CASE_ID.value),
                date_column=event_step.mapped_columns.get(CanonicalField.INITIAL_APPROVAL_DATE.value),
                date_format=event_step.date_format, reporting_start=event_step.reporting_start,
                reporting_end=event_step.reporting_end,
                evidence={**event_metrics["evidence"], "event_row_count": event_metrics["serious_event_row_count"]},
                calculation_function="processing.event_calculator.compute_serious_case_count",
                step_validated=True, historical_value=historical.get("serious_count"),
            ))
            results.append(build_metric_result(
                metric_id="fatal_case_count", pbrer_section_number=section_number,
                topic_heading=event_step.topic_heading, calculated_value=event_metrics["fatal_case_count"],
                source_workbook=event_step.source_workbook, source_sheet=event_step.source_sheet,
                header_row=event_step.header_row, case_id_column=event_step.mapped_columns.get(CanonicalField.CASE_ID.value),
                date_column=event_step.mapped_columns.get(CanonicalField.INITIAL_APPROVAL_DATE.value),
                date_format=event_step.date_format, reporting_start=event_step.reporting_start,
                reporting_end=event_step.reporting_end,
                evidence={**event_metrics["evidence"], "event_row_count": event_metrics["fatal_event_row_count"]},
                calculation_function="processing.event_calculator.compute_fatal_case_count",
                step_validated=True, historical_value=historical.get("fatal_count"),
            ))

        if case_metrics is not None:
            results.append(build_metric_result(
                metric_id="source_breakdown", pbrer_section_number=section_number,
                topic_heading=case_step.topic_heading, calculated_value=case_metrics["source_breakdown"],
                source_workbook=case_step.source_workbook, source_sheet=case_step.source_sheet,
                header_row=case_step.header_row, case_id_column=case_step.mapped_columns.get(CanonicalField.CASE_ID.value),
                date_column=case_step.mapped_columns.get(CanonicalField.INITIAL_APPROVAL_DATE.value),
                date_format=case_step.date_format, reporting_start=case_step.reporting_start,
                reporting_end=case_step.reporting_end, evidence=case_metrics["evidence"],
                calculation_function="processing.case_calculator.compute_case_source_breakdown",
                step_validated=True, historical_value=None,
            ))

        if event_metrics is not None:
            results.append(build_metric_result(
                metric_id="event_pt_frequency", pbrer_section_number=section_number,
                topic_heading=event_step.topic_heading, calculated_value=event_metrics["event_pt_frequency"],
                source_workbook=event_step.source_workbook, source_sheet=event_step.source_sheet,
                header_row=event_step.header_row, case_id_column=event_step.mapped_columns.get(CanonicalField.CASE_ID.value),
                date_column=event_step.mapped_columns.get(CanonicalField.INITIAL_APPROVAL_DATE.value),
                date_format=event_step.date_format, reporting_start=event_step.reporting_start,
                reporting_end=event_step.reporting_end, evidence=event_metrics["evidence"],
                calculation_function="processing.event_calculator.compute_event_pt_frequency",
                step_validated=True, historical_value=None,
            ))

    return results


def run_full_pipeline(run_id: str, docx_path: str | Path, excel_dir: str | Path,
                        reporting_start: str, reporting_end: str, trace_sink=None) -> dict[str, Any]:
    """Runs Document Agent -> Excel Agent -> Topic Mapping Agent ->
    Calculation Planning Agent -> deterministic calculation engine ->
    validation/benchmark, and returns every stage's output for the
    frontend's traceability page."""
    doc_agent = DocumentUnderstandingAgent(trace_sink=trace_sink)
    document_structure = doc_agent.run(run_id, docx_path)

    excel_agent = ExcelUnderstandingAgent(trace_sink=trace_sink, max_workers=10)
    workbook_inventory = excel_agent.run(run_id, excel_dir)

    topic_agent = TopicMappingAgent(trace_sink=trace_sink)
    topic_mapping = topic_agent.run(run_id, document_structure, workbook_inventory)

    planner = CalculationPlanningAgent(trace_sink=trace_sink)
    doc_topics = [t.model_dump(mode="json") for t in document_structure.topics]
    execution_plan = planner.run(run_id, doc_topics, workbook_inventory, topic_mapping, reporting_start, reporting_end)

    topics_by_section = {t.section_number: t.model_dump(mode="json") for t in document_structure.topics}
    metric_results = run_calculation_engine(execution_plan, workbook_inventory, topics_by_section, excel_dir)

    benchmark_report = build_benchmark_report(run_id, metric_results)

    return {
        "run_id": run_id,
        "generated_at": datetime.now(UTC),
        "document_structure": document_structure,
        "workbook_inventory": workbook_inventory,
        "topic_mapping": topic_mapping,
        "execution_plan": execution_plan,
        "metric_results": metric_results,
        "benchmark_report": benchmark_report,
    }
