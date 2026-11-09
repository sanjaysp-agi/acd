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
from models.schemas import (
    ExecutionPlan,
    TopicMappingResult,
    TopicReconstructionResult,
    WorkbookInventory,
)
from processing.topic_calculator import calculate_percentages, calculate_topic_case_metrics, calculate_topic_event_metrics
from processing.topic_reconstruction import (
    check_case_event_population_alignment,
    compare_reconstruction_with_topic_export,
    reconstruct_topic_from_all_events,
    reconstruction_feasible,
)
from tools.excel_tools import discover_excel_files
from validation.calculation_validator import assemble_validation_report, build_metric_result
from validation.input_validator import check_footer_detection, check_header_detection, check_input_files_present, check_workbook_identification
from validation.mapping_validator import check_case_event_join, check_independent_topic_reconstruction, check_topic_criteria_matching
from validation.reconciliation import build_benchmark_report


def _wb_lookup(workbook_inventory: WorkbookInventory) -> dict[str, Any]:
    return {wb.file_name: wb for wb in workbook_inventory.workbooks}


def _wb_path(workbook_inventory: WorkbookInventory, input_dir: str | Path, file_name: str) -> str:
    return str(Path(input_dir) / file_name)


def _mapped_columns_of(workbook_entry) -> dict[str, str]:
    return {m.canonical_field.value: m.raw_column for m in workbook_entry.column_mappings if m.canonical_field}


def _data_sheet_of(workbook_entry):
    return next((s for s in workbook_entry.sheets if s.role == "data_table"), None)


def run_topic_reconstruction(workbook_inventory: WorkbookInventory, topic_mapping: TopicMappingResult,
                                reporting_start: str, reporting_end: str, input_dir: str | Path,
                                topic_case_counts: dict[str, dict[str, Any]]) -> list[TopicReconstructionResult]:
    """Independent cross-validation (prompt.md Part 2 Agent 3, lines
    378-394): re-applies each topic's own Excel search criterion to the
    all-drug-event workbook and compares the reconstructed case set
    against the topic-specific export's own eligible case set.
    `topic_case_counts` maps pbrer_section_number -> {"case_count", "eligible_case_ids"}
    already computed by the primary calculation path."""
    all_event_wb = next((wb for wb in workbook_inventory.workbooks if wb.workbook_type == WorkbookType.ALL_DRUG_EVENT), None)
    results: list[TopicReconstructionResult] = []
    if all_event_wb is None:
        for m in topic_mapping.mappings:
            if m.case_workbook is None:
                continue
            results.append(TopicReconstructionResult(
                pbrer_section_number=m.pbrer_section_number, topic_heading=m.pbrer_heading,
                feasible=False, reason="No all-drug-event workbook was discovered -- independent "
                "reconstruction requires one.", criterion_type=m.excel_criterion_type,
                criterion_value=m.excel_criterion_value,
            ))
        return results

    all_event_sheet = _data_sheet_of(all_event_wb)
    all_event_mapped = _mapped_columns_of(all_event_wb)
    if all_event_sheet is None or all_event_sheet.header_row is None:
        for m in topic_mapping.mappings:
            if m.case_workbook is None:
                continue
            results.append(TopicReconstructionResult(
                pbrer_section_number=m.pbrer_section_number, topic_heading=m.pbrer_heading,
                feasible=False, reason="The all-drug-event workbook's data table / header row could "
                "not be identified -- independent reconstruction requires it.",
                criterion_type=m.excel_criterion_type, criterion_value=m.excel_criterion_value,
            ))
        return results

    for m in topic_mapping.mappings:
        if m.case_workbook is None or m.pbrer_section_number not in topic_case_counts:
            continue
        feasible, reason, field = reconstruction_feasible(m.excel_criterion_type, all_event_mapped)
        base_fields_present = all(f.value in all_event_mapped for f in
                                    (CanonicalField.CASE_ID, CanonicalField.INITIAL_APPROVAL_DATE, CanonicalField.PRIMARY_SOURCE))
        if not feasible or not base_fields_present:
            if feasible and not base_fields_present:
                reason = "All-drug-event workbook is missing a mapped case ID, date, or primary-source " \
                          "column -- reconstruction requires all three in addition to the MedDRA column."
            results.append(TopicReconstructionResult(
                pbrer_section_number=m.pbrer_section_number, topic_heading=m.pbrer_heading,
                feasible=False, reason=reason, criterion_type=m.excel_criterion_type,
                criterion_value=m.excel_criterion_value,
            ))
            continue

        topic_info = topic_case_counts[m.pbrer_section_number]
        recon = reconstruct_topic_from_all_events(
            all_event_file_path=_wb_path(workbook_inventory, input_dir, all_event_wb.file_name),
            all_event_sheet=all_event_sheet.sheet_name, all_event_header_row=all_event_sheet.header_row,
            case_id_col=all_event_mapped[CanonicalField.CASE_ID.value],
            date_col=all_event_mapped[CanonicalField.INITIAL_APPROVAL_DATE.value],
            source_col=all_event_mapped[CanonicalField.PRIMARY_SOURCE.value],
            meddra_col=all_event_mapped[field.value],
            criterion_type=m.excel_criterion_type, criterion_value=m.excel_criterion_value,
            reporting_start=reporting_start, reporting_end=reporting_end,
            data_end_row=all_event_sheet.data_end_row,
        )
        comparison = compare_reconstruction_with_topic_export(
            reconstructed_case_count=recon["reconstructed_case_count"],
            reconstructed_case_ids=recon["reconstructed_case_ids"],
            topic_case_count=topic_info["case_count"], topic_case_ids=topic_info["eligible_case_ids"],
        )
        results.append(TopicReconstructionResult(
            pbrer_section_number=m.pbrer_section_number, topic_heading=m.pbrer_heading,
            feasible=True, criterion_type=m.excel_criterion_type, criterion_value=m.excel_criterion_value,
            reconstructed_case_count=recon["reconstructed_case_count"],
            reconstructed_event_row_count=recon["reconstructed_event_row_count"],
            topic_export_case_count=topic_info["case_count"], comparison=comparison, evidence=recon["evidence"],
        ))
    return results


def run_calculation_engine(execution_plan: ExecutionPlan, workbook_inventory: WorkbookInventory,
                             document_topics_by_section: dict[str, dict], input_dir: str | Path) -> dict[str, Any]:
    """Groups execution plan steps by topic (section number) and runs the
    actual pandas calculations, producing MetricResult objects with full
    audit evidence. Steps marked validated=False are skipped entirely --
    never executed with guessed columns. Also returns per-topic case-event
    join evidence (Part 3 Rule H) and the case-count/eligible-case-id
    context needed for independent topic reconstruction."""
    steps_by_topic: dict[str | None, list] = {}
    for step in execution_plan.steps:
        steps_by_topic.setdefault(step.pbrer_section_number, []).append(step)

    results = []
    join_checks = []
    topic_case_counts: dict[str, dict[str, Any]] = {}
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

            pct = calculate_percentages(event_metrics["serious_case_count"], event_metrics["fatal_case_count"],
                                          case_metrics["case_count"])
            results.append(build_metric_result(
                metric_id="serious_fatal_percentages", pbrer_section_number=section_number,
                topic_heading=event_step.topic_heading, calculated_value=pct,
                source_workbook=event_step.source_workbook, source_sheet=event_step.source_sheet,
                header_row=event_step.header_row, case_id_column=event_step.mapped_columns.get(CanonicalField.CASE_ID.value),
                date_column=event_step.mapped_columns.get(CanonicalField.INITIAL_APPROVAL_DATE.value),
                date_format=event_step.date_format, reporting_start=event_step.reporting_start,
                reporting_end=event_step.reporting_end,
                evidence={**event_metrics["evidence"], "serious_case_count": event_metrics["serious_case_count"],
                           "fatal_case_count": event_metrics["fatal_case_count"],
                           "topic_case_count": case_metrics["case_count"]},
                calculation_function="processing.topic_calculator.calculate_percentages",
                step_validated=True, historical_value=None,
            ))

            alignment = check_case_event_population_alignment(
                case_ids=case_metrics["eligible_case_ids"],
                event_case_ids=event_metrics["event_case_ids_before_restriction"],
            )
            join_checks.append(check_case_event_join(event_step.topic_heading, section_number, alignment))

        if section_number is not None and case_metrics is not None:
            topic_case_counts[section_number] = {
                "case_count": case_metrics["case_count"], "eligible_case_ids": case_metrics["eligible_case_ids"],
            }

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

    return {"metric_results": results, "case_event_join_checks": join_checks, "topic_case_counts": topic_case_counts}


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
    engine_output = run_calculation_engine(execution_plan, workbook_inventory, topics_by_section, excel_dir)
    metric_results = engine_output["metric_results"]

    benchmark_report = build_benchmark_report(run_id, metric_results)

    reconstruction_results = run_topic_reconstruction(
        workbook_inventory, topic_mapping, reporting_start, reporting_end, excel_dir,
        engine_output["topic_case_counts"],
    )

    discovered_excel_files = discover_excel_files(excel_dir)
    extra_checks = []
    extra_checks.append(check_input_files_present(docx_path, excel_dir, discovered_excel_files))
    extra_checks.extend(check_workbook_identification(workbook_inventory))
    extra_checks.extend(check_header_detection(workbook_inventory))
    extra_checks.extend(check_footer_detection(workbook_inventory))
    extra_checks.extend(check_topic_criteria_matching(topic_mapping.mappings))
    extra_checks.extend(engine_output["case_event_join_checks"])
    extra_checks.extend(check_independent_topic_reconstruction(r) for r in reconstruction_results)

    validation_report = assemble_validation_report(run_id, metric_results, extra_checks)

    return {
        "run_id": run_id,
        "generated_at": datetime.now(UTC),
        "document_structure": document_structure,
        "workbook_inventory": workbook_inventory,
        "topic_mapping": topic_mapping,
        "execution_plan": execution_plan,
        "metric_results": metric_results,
        "benchmark_report": benchmark_report,
        "topic_reconstruction": reconstruction_results,
        "validation_report": validation_report,
        # Retained so the frontend can re-run just the planning/calculation
        # stages (e.g. after a manual topic-mapping correction) without
        # re-running the Document/Excel Understanding Agents.
        "_excel_dir": str(excel_dir),
    }
