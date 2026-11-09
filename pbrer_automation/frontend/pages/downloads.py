"""Downloads page: generate and serve the output workbooks."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from config.settings import OUTPUT_DIR
from frontend.state import get_pipeline_result, get_run_id, has_run
from generation.audit_generator import generate_audit_workbook
from generation.excel_generator import generate_results_workbook
from generation.report_generator import generate_benchmark_workbook, generate_report_ready_output


def _download_button(label: str, path: str):
    data = Path(path).read_bytes()
    st.download_button(label, data=data, file_name=Path(path).name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def render():
    st.title("Downloads")
    if not has_run():
        st.info("Run the pipeline first (Upload Documents).")
        return

    result = get_pipeline_result()
    run_id = get_run_id()
    run_output_dir = OUTPUT_DIR / run_id
    run_output_dir.mkdir(parents=True, exist_ok=True)

    results_path = generate_results_workbook(result["metric_results"], run_output_dir / "calculation_results.xlsx")
    audit_path = generate_audit_workbook(result["metric_results"], run_output_dir / "audit_trail.xlsx")
    report_path = generate_report_ready_output(result["metric_results"], run_output_dir / "section_16_3_figures.xlsx")
    benchmark_path = generate_benchmark_workbook(result["benchmark_report"], run_output_dir / "benchmark_comparison.xlsx")

    st.write("**Calculation results workbook** -- every calculated metric with its value and status.")
    _download_button("Download calculation_results.xlsx", results_path)

    st.write("**Audit-trail workbook** -- full filter/evidence trail per metric.")
    _download_button("Download audit_trail.xlsx", audit_path)

    st.write("**Report-ready Section 16.3 numerical output** -- figures laid out per topic.")
    _download_button("Download section_16_3_figures.xlsx", report_path)

    st.write("**Benchmark comparison report** -- calculated vs. historical PBRER figures.")
    _download_button("Download benchmark_comparison.xlsx", benchmark_path)
