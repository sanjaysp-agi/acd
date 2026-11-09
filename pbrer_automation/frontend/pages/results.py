"""Results Dashboard: calculated figures with traceability per number."""
from __future__ import annotations

import streamlit as st

from frontend.state import get_pipeline_result, has_run


def render():
    st.title("Results Dashboard")
    if not has_run():
        st.info("Run the pipeline first (Upload Documents).")
        return

    results = get_pipeline_result()["metric_results"]

    by_topic: dict[str, list] = {}
    for mr in results:
        by_topic.setdefault(mr.pbrer_section_number or "Total", []).append(mr)

    for section, metrics in sorted(by_topic.items()):
        heading = metrics[0].topic_heading or "All post-marketing cases"
        st.subheader(f"{section} -- {heading}")
        cols = st.columns(len(metrics))
        for col, mr in zip(cols, metrics):
            value = mr.calculated_value
            display_value = value if isinstance(value, (int, float, str)) else f"{len(value)} items" if value else "—"
            delta = None
            if mr.historical_value is not None and isinstance(value, (int, float)):
                delta = f"{mr.difference:+} vs historical {mr.historical_value}"
            col.metric(mr.metric_id, display_value, delta=delta)

        for mr in metrics:
            with st.expander(f"Traceability -- {mr.metric_id}"):
                e = mr.evidence
                st.write(f"**Validation status:** {mr.validation_status}")
                st.write(f"**Source:** `{e.source_workbook}` / sheet `{e.source_sheet}` / header row {e.header_row}")
                st.write(f"**Case ID column:** {e.case_id_column} -- **Date column:** {e.date_column} "
                         f"({e.date_format})")
                st.write(f"**Reporting period:** {e.reporting_start} to {e.reporting_end} (inclusive)")
                st.write(f"**Clinical Trials exclusion:** applied, matched values {e.source_exclusion_values_matched}")
                st.write(f"**Rows before filter:** {e.rows_before_filter} -- **after filter:** {e.rows_after_filter}")
                if e.distinct_case_count is not None:
                    st.write(f"**Distinct case count:** {e.distinct_case_count}")
                if e.event_row_count is not None:
                    st.write(f"**Event row count:** {e.event_row_count}")
                st.write(f"**Calculation function:** `{e.calculation_function}`")
                if mr.validation_messages:
                    st.caption(" | ".join(mr.validation_messages))
                if isinstance(mr.calculated_value, (dict, list)):
                    st.json(mr.calculated_value)
