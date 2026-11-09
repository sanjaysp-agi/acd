"""Validation & Audit page: pass/warn/fail checks and benchmark comparison."""
from __future__ import annotations

import streamlit as st

from frontend.state import get_pipeline_result, has_run


def _display_value(value):
    """A metric's calculated value can be a dict (source_breakdown) or
    list (event_pt_frequency) in one row and a plain int in another --
    mixing those in one dataframe column breaks pyarrow's Arrow
    conversion (Streamlit auto-recovers, but with a console warning).
    Stringify non-scalars so the column has a single, consistent type."""
    if isinstance(value, dict):
        return "; ".join(f"{k}={v}" for k, v in value.items())
    if isinstance(value, list):
        return "; ".join(str(v) for v in value[:10])
    return value


def render():
    st.title("Validation & Audit")
    if not has_run():
        st.info("Run the pipeline first (Upload Documents).")
        return

    result = get_pipeline_result()
    results = result["metric_results"]
    bench = result["benchmark_report"]

    st.subheader("Validation status by metric")
    status_rows = [{"Section": mr.pbrer_section_number, "Topic": mr.topic_heading, "Metric": mr.metric_id,
                     "Status": mr.validation_status, "Messages": " | ".join(mr.validation_messages)}
                    for mr in results]
    st.dataframe(status_rows, width='stretch')

    failed = [mr for mr in results if mr.validation_status == "failed"]
    if failed:
        st.error(f"{len(failed)} metric(s) FAILED validation -- not marked verified.")

    st.subheader("Benchmark comparison")
    st.caption("A match does not alone prove methodological correctness -- see the Results page for "
               "the full filter/evidence trail behind each figure.")
    bench_rows = [{"Metric": r.metric_label, "Expected": _display_value(r.expected),
                    "Calculated": _display_value(r.calculated),
                    "Difference": r.difference, "Status": r.status} for r in bench.rows]
    st.dataframe(bench_rows, width='stretch')

    matches = sum(1 for r in bench.rows if r.status == "match")
    mismatches = sum(1 for r in bench.rows if r.status == "mismatch")
    unverified = sum(1 for r in bench.rows if r.status == "unverified")
    c1, c2, c3 = st.columns(3)
    c1.metric("Matches", matches)
    c2.metric("Mismatches", mismatches)
    c3.metric("Unverified (no historical figure)", unverified)
