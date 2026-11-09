"""Upload Documents page: the ONLY place real inputs enter the app.

Per prompt.md: only the previous/approved PBRER, multiple Excel exports,
and the reporting start/end dates. No traceability-HTML upload field, no
AWS/Bedrock configuration exposed here.
"""
from __future__ import annotations

import shutil
import uuid
from datetime import date
from pathlib import Path

import streamlit as st

from config.settings import DATA_DIR
from observability.run_manager import execute_run


def _save_uploads(run_dir: Path, docx_file, excel_files) -> tuple[str, str]:
    input_dir = run_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    docx_path = input_dir / docx_file.name
    docx_path.write_bytes(docx_file.getvalue())

    for f in excel_files:
        (input_dir / f.name).write_bytes(f.getvalue())

    return str(docx_path), str(input_dir)


def render():
    st.title("Upload Documents")
    st.caption("Previous/approved PBRER, current Excel exports, and the reporting interval -- "
               "the only inputs this application needs.")

    docx_file = st.file_uploader("Previous/approved PBRER (.docx)", type=["docx"])
    excel_files = st.file_uploader("Excel exports (all-case, all-drug-event, topic-specific case/drug-event)",
                                     type=["xlsx"], accept_multiple_files=True)

    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("Reporting start date", value=date(2019, 4, 7))
    with col2:
        end = st.date_input("Reporting end date", value=date(2024, 4, 6))

    st.info("Both reporting-period boundaries are treated as inclusive.")

    run_clicked = st.button("Run pipeline", type="primary", disabled=not (docx_file and excel_files))

    if run_clicked:
        run_uid = uuid.uuid4().hex[:8]
        run_dir = DATA_DIR / "uploads" / run_uid
        docx_path, excel_dir = _save_uploads(run_dir, docx_file, excel_files)

        with st.spinner("Running Document, Excel, Topic Mapping and Calculation Planning agents... "
                         "this can take a few minutes for large exports."):
            result = execute_run(docx_path, excel_dir, str(start), str(end))

        st.session_state["pipeline_result"] = result
        st.success(f"Run complete: {result['run_id']}")
        st.rerun()

    if not (docx_file and excel_files):
        st.warning("Upload both the PBRER document and at least one Excel export to enable the run.")
