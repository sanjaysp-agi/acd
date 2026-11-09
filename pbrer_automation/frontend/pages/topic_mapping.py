"""Topic Mapping page: matched topics, criteria, confidence, and manual
correction/approval (prompt.md Part 7, line 881) for low-confidence or
unmatched mappings."""
from __future__ import annotations

from datetime import datetime, UTC

import streamlit as st

from agents.calculation_planner import CalculationPlanningAgent
from config.metric_registry import WorkbookType
from frontend.state import get_pipeline_result, has_run
from models.schemas import TopicMappingEntry, TopicMappingResult
from pipeline import run_calculation_engine, run_topic_reconstruction
from validation.calculation_validator import assemble_validation_report
from validation.input_validator import check_footer_detection, check_header_detection, check_workbook_identification
from validation.mapping_validator import check_independent_topic_reconstruction, check_topic_criteria_matching
from validation.reconciliation import build_benchmark_report


def _recompute_downstream(result: dict) -> dict:
    """Re-runs Calculation Planning + the calculation engine + benchmark +
    reconstruction + validation using the (possibly just-overridden) topic
    mapping already in `result`, WITHOUT re-running the Document/Excel
    Understanding Agents -- their output doesn't change when a human
    corrects a topic<->workbook pairing."""
    run_id = result["run_id"]
    workbook_inventory = result["workbook_inventory"]
    topic_mapping = result["topic_mapping"]
    document_structure = result["document_structure"]
    reporting_start = result["execution_plan"].reporting_start
    reporting_end = result["execution_plan"].reporting_end
    excel_dir = result["_excel_dir"]

    planner = CalculationPlanningAgent()
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

    extra_checks = []
    extra_checks.extend(check_workbook_identification(workbook_inventory))
    extra_checks.extend(check_header_detection(workbook_inventory))
    extra_checks.extend(check_footer_detection(workbook_inventory))
    extra_checks.extend(check_topic_criteria_matching(topic_mapping.mappings))
    extra_checks.extend(engine_output["case_event_join_checks"])
    extra_checks.extend(check_independent_topic_reconstruction(r) for r in reconstruction_results)
    validation_report = assemble_validation_report(run_id, metric_results, extra_checks)

    result = dict(result)
    result.update({
        "execution_plan": execution_plan, "metric_results": metric_results,
        "benchmark_report": benchmark_report, "topic_reconstruction": reconstruction_results,
        "validation_report": validation_report, "generated_at": datetime.now(UTC),
    })
    return result


def render():
    st.title("Topic Mapping")
    if not has_run():
        st.info("Run the pipeline first (Upload Documents).")
        return

    result = get_pipeline_result()
    mapping: TopicMappingResult = result["topic_mapping"]
    workbook_inventory = result["workbook_inventory"]
    case_workbook_names = ["(none)"] + [wb.file_name for wb in workbook_inventory.workbooks
                                          if wb.workbook_type in (WorkbookType.TOPIC_CASE, WorkbookType.ALL_CASE)]
    event_workbook_names = ["(none)"] + [wb.file_name for wb in workbook_inventory.workbooks
                                           if wb.workbook_type in (WorkbookType.TOPIC_DRUG_EVENT, WorkbookType.ALL_DRUG_EVENT)]

    rows = []
    for m in mapping.mappings:
        rows.append({
            "Section": m.pbrer_section_number, "Heading": m.pbrer_heading,
            "Criterion type": m.excel_criterion_type.value, "Case workbook": m.case_workbook or "(none)",
            "Drug-event workbook": m.drug_event_workbook or "(none)",
            "Confidence": round(m.confidence, 2), "Needs review": m.needs_review,
            "Approved": not m.needs_review and m.case_workbook is not None,
        })

    st.caption("Confidence is term-overlap between the PBRER's own search-criteria text and the "
               "Excel cover page's criterion value -- not a guess from the heading's number or filename. "
               "Edit the Case/Drug-event workbook or Approved columns below to manually correct a mapping, "
               "then re-run the calculation stages with the correction applied.")

    edited = st.data_editor(
        rows, width="stretch", key="topic_mapping_editor",
        column_config={
            "Case workbook": st.column_config.SelectboxColumn(options=case_workbook_names),
            "Drug-event workbook": st.column_config.SelectboxColumn(options=event_workbook_names),
            "Approved": st.column_config.CheckboxColumn(),
            "Section": st.column_config.TextColumn(disabled=True),
            "Heading": st.column_config.TextColumn(disabled=True),
            "Criterion type": st.column_config.TextColumn(disabled=True),
            "Confidence": st.column_config.NumberColumn(disabled=True),
            "Needs review": st.column_config.CheckboxColumn(disabled=True),
        },
    )

    if mapping.unmatched_document_topics:
        st.warning(f"**Unmatched PBRER topics** (no Excel export provided): "
                   f"{', '.join(mapping.unmatched_document_topics)}")
    if mapping.unmatched_workbooks:
        st.warning(f"**Unmatched workbooks** (no corresponding PBRER topic found): "
                   f"{', '.join(mapping.unmatched_workbooks)}")

    if st.button("Apply corrections and re-run calculations", type="primary"):
        new_mappings = []
        for original, edited_row in zip(mapping.mappings, edited):
            case_wb = edited_row["Case workbook"] if edited_row["Case workbook"] != "(none)" else None
            event_wb = edited_row["Drug-event workbook"] if edited_row["Drug-event workbook"] != "(none)" else None
            approved = bool(edited_row["Approved"])
            new_mappings.append(TopicMappingEntry(
                pbrer_section_number=original.pbrer_section_number, pbrer_heading=original.pbrer_heading,
                excel_criterion_type=original.excel_criterion_type, excel_criterion_value=original.excel_criterion_value,
                case_workbook=case_wb, drug_event_workbook=event_wb,
                confidence=1.0 if approved else original.confidence,
                needs_review=not approved,
                warnings=[] if (case_wb != original.case_workbook or event_wb != original.drug_event_workbook or approved)
                else original.warnings,
            ))
        result["topic_mapping"] = TopicMappingResult(
            run_id=mapping.run_id, generated_at=datetime.now(UTC), mappings=new_mappings,
            unmatched_workbooks=mapping.unmatched_workbooks, unmatched_document_topics=mapping.unmatched_document_topics,
        )
        with st.spinner("Re-running Calculation Planning Agent + calculation engine with the corrected mapping..."):
            new_result = _recompute_downstream(result)
        st.session_state["pipeline_result"] = new_result
        st.success("Corrections applied -- execution plan, calculations and validation re-run.")
        st.rerun()
