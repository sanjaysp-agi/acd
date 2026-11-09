"""Upload Documents page: the ONLY place real inputs enter the app.

Per prompt.md: only the previous/approved PBRER, multiple Excel exports,
and the reporting start/end dates. No traceability-HTML upload field, no
AWS/Bedrock configuration exposed here.
"""
from __future__ import annotations

import tempfile
import uuid
from datetime import date
from pathlib import Path

import streamlit as st

from observability.run_manager import execute_run

# Windows MAX_PATH is 260 chars. These CSMR export filenames are long on
# their own (e.g. "02_drugevent_Impulse control disorders such as
# compulsive shopping_..._CSMR.xlsx" is ~150 chars); nesting the upload
# scratch dir inside this project's own (already long, OneDrive-synced)
# path pushed several real filenames over the limit -- Windows reports
# that as FileNotFoundError, not a path-length error, which is what was
# actually hit. Saving under the system temp dir instead keeps the base
# short regardless of where this project lives on disk.
_MAX_SAFE_PATH_LEN = 240


def _safe_filename(directory: Path, name: str) -> str:
    """Shorten a filename if directory/name would still risk exceeding
    MAX_PATH even under the short temp-dir base (e.g. a very deep temp
    path on some systems, or an even longer real-world export name)."""
    candidate_len = len(str(directory / name))
    if candidate_len <= _MAX_SAFE_PATH_LEN:
        return name
    stem, ext = Path(name).stem, Path(name).suffix
    overflow = candidate_len - _MAX_SAFE_PATH_LEN
    truncated_stem = stem[: max(10, len(stem) - overflow)]
    return f"{truncated_stem}{ext}"


def _save_uploads(run_dir: Path, docx_file, excel_files) -> tuple[str, str]:
    input_dir = run_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    docx_path = input_dir / _safe_filename(input_dir, docx_file.name)
    docx_path.write_bytes(docx_file.getvalue())

    for f in excel_files:
        (input_dir / _safe_filename(input_dir, f.name)).write_bytes(f.getvalue())

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
        run_dir = Path(tempfile.gettempdir()) / "pbrer_uploads" / run_uid
        docx_path, excel_dir = _save_uploads(run_dir, docx_file, excel_files)

        with st.spinner("Running Document, Excel, Topic Mapping and Calculation Planning agents... "
                         "this can take a few minutes for large exports."):
            result = execute_run(docx_path, excel_dir, str(start), str(end))

        st.session_state["pipeline_result"] = result
        st.success(f"Run complete: {result['run_id']}")
        st.rerun()

    if not (docx_file and excel_files):
        st.warning("Upload both the PBRER document and at least one Excel export to enable the run.")
