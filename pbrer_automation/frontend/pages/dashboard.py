"""Dashboard: application overview and latest run status."""
from __future__ import annotations

import streamlit as st

from frontend.state import get_pipeline_result, has_run


def render():
    st.title("PBRER Section 16.3 Automation")
    st.caption("AI-driven extraction, calculation and validation of Section 16.3 numerical figures.")

    if not has_run():
        st.info("No run yet. Go to **Upload Documents** to start.")
        return

    result = get_pipeline_result()
    doc = result["document_structure"]
    inv = result["workbook_inventory"]
    mapping = result["topic_mapping"]
    bench = result["benchmark_report"]

    st.subheader(f"Latest run: `{result['run_id']}`")
    st.caption(f"Generated at {result['generated_at']}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Topics detected", len(doc.topics))
    c2.metric("Workbooks discovered", len(inv.workbooks))
    c3.metric("Topics mapped", sum(1 for m in mapping.mappings if m.case_workbook))
    matches = sum(1 for r in bench.rows if r.status == "match")
    mismatches = sum(1 for r in bench.rows if r.status == "mismatch")
    c4.metric("Benchmark matches", f"{matches}", delta=f"-{mismatches} mismatch" if mismatches else None,
              delta_color="inverse" if mismatches else "off")

    st.subheader("Reporting interval")
    if result["execution_plan"].steps:
        step = result["execution_plan"].steps[0]
        st.write(f"**{step.reporting_start}** to **{step.reporting_end}** (both boundaries inclusive)")

    if mapping.unmatched_document_topics:
        st.warning(f"Topics with no matching Excel workbook: {', '.join(mapping.unmatched_document_topics)}")
    if mapping.unmatched_workbooks:
        st.warning(f"Workbooks with no matching PBRER topic: {', '.join(mapping.unmatched_workbooks)}")
