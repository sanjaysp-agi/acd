"""Calculation Review page: the proposed execution plan before/after validation."""
from __future__ import annotations

import streamlit as st

from frontend.state import get_pipeline_result, has_run


def render():
    st.title("Calculation Review")
    if not has_run():
        st.info("Run the pipeline first (Upload Documents).")
        return

    plan = get_pipeline_result()["execution_plan"]
    st.write(f"**Reporting interval:** {plan.reporting_start} to {plan.reporting_end} (inclusive)")

    if plan.warnings:
        for w in plan.warnings:
            st.warning(w.message)

    rows = []
    for s in plan.steps:
        rows.append({
            "Section": s.pbrer_section_number, "Topic": s.topic_heading, "Metric": s.metric_id,
            "Source workbook": s.source_workbook, "Date field": s.date_field,
            "CT exclusion": s.applies_clinical_trials_exclusion, "Grain": s.grain.value,
            "Distinct by": s.distinct_by.value if s.distinct_by else "(event rows)",
            "Validated": s.validated,
            "Notes": "; ".join(s.validation_notes),
        })
    st.dataframe(rows, width='stretch')

    st.caption("A step marked Validated=False was NOT executed by the calculation engine -- "
               "required column mappings were missing or low-confidence.")

    st.subheader("Join and percentage-formula logic per metric")
    st.caption("Approved, controlled definitions from the metric registry -- never invented per-run by an agent.")
    seen_metrics: set[str] = set()
    detail_rows = []
    for s in plan.steps:
        if s.metric_id in seen_metrics:
            continue
        seen_metrics.add(s.metric_id)
        detail_rows.append({
            "Metric": s.metric_id,
            "Join requirements": s.join_requirements or "(none recorded)",
            "Percentage formula": s.percentage_formula or "(not a percentage metric)",
            "Deduplication": f"Distinct by {s.distinct_by.value}" if s.distinct_by else "None -- event-row counts, not deduplicated",
        })
    st.dataframe(detail_rows, width='stretch')
