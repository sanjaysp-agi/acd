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
    validation_report = result.get("validation_report")

    if validation_report is not None:
        st.subheader("Overall validation status")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Overall status", validation_report.overall_status)
        c2.metric("Checks passed", sum(1 for c in validation_report.checks if c.status == "pass"))
        c3.metric("Warnings", sum(1 for c in validation_report.checks if c.status == "warning"))
        c4.metric("Failures", sum(1 for c in validation_report.checks if c.status == "fail"))

        st.subheader("Mandatory checks (prompt.md Part 5, #1-14)")
        st.caption("Input validation, workbook/sheet identification, header/footer detection, date "
                   "normalization, case ID checks, case/event join (Rule H), Clinical Trials exclusion, "
                   "seriousness/death classification, percentage calculation, topic-criteria matching, "
                   "independent topic reconstruction, and date-boundary inclusivity (covered by "
                   "tests/test_date_boundaries.py).")
        check_rows = [{"Check": c.check_name, "Status": c.status, "Message": c.message}
                       for c in validation_report.checks]
        st.dataframe(check_rows, width='stretch')

    st.subheader("Validation status by metric")
    status_rows = [{"Section": mr.pbrer_section_number, "Topic": mr.topic_heading, "Metric": mr.metric_id,
                     "Status": mr.validation_status, "Messages": " | ".join(mr.validation_messages)}
                    for mr in results]
    st.dataframe(status_rows, width='stretch')

    failed = [mr for mr in results if mr.validation_status == "failed"]
    if failed:
        st.error(f"{len(failed)} metric(s) FAILED validation -- not marked verified.")

    reconstruction = result.get("topic_reconstruction") or []
    if reconstruction:
        st.subheader("Independent topic reconstruction (cross-validation)")
        st.caption("Each topic's own Excel search criterion re-applied to the all-drug-event workbook, "
                   "independently of the topic-specific export -- a cross-check, never a substitute "
                   "(prompt.md Part 2 Agent 3, lines 378-394).")
        recon_rows = []
        for r in reconstruction:
            recon_rows.append({
                "Section": r.pbrer_section_number, "Topic": r.topic_heading,
                "Criterion type": r.criterion_type.value, "Feasible": r.feasible,
                "Reconstructed cases": r.reconstructed_case_count, "Topic export cases": r.topic_export_case_count,
                "Comparison status": (r.comparison or {}).get("status", "n/a") if r.feasible else "not attempted",
                "Reason/notes": r.reason,
            })
        st.dataframe(recon_rows, width='stretch')
        discrepancies = [r for r in reconstruction if r.feasible and (r.comparison or {}).get("status") == "discrepancy"]
        if discrepancies:
            st.warning(f"{len(discrepancies)} topic(s) show a discrepancy between the independent "
                       "reconstruction and the topic-specific export -- see evidence below.")
            for r in discrepancies:
                with st.expander(f"Discrepancy evidence -- {r.topic_heading}"):
                    st.json(r.comparison)

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
