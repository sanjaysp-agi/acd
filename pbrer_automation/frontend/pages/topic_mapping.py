"""Topic Mapping page: matched topics, criteria, confidence."""
from __future__ import annotations

import streamlit as st

from frontend.state import get_pipeline_result, has_run


def render():
    st.title("Topic Mapping")
    if not has_run():
        st.info("Run the pipeline first (Upload Documents).")
        return

    mapping = get_pipeline_result()["topic_mapping"]

    rows = []
    for m in mapping.mappings:
        rows.append({
            "Section": m.pbrer_section_number, "Heading": m.pbrer_heading,
            "Criterion type": m.excel_criterion_type.value, "Case workbook": m.case_workbook,
            "Drug-event workbook": m.drug_event_workbook, "Confidence": round(m.confidence, 2),
            "Needs review": m.needs_review,
        })
    st.dataframe(rows, width='stretch')

    if mapping.unmatched_document_topics:
        st.warning(f"**Unmatched PBRER topics** (no Excel export provided): "
                   f"{', '.join(mapping.unmatched_document_topics)}")
    if mapping.unmatched_workbooks:
        st.warning(f"**Unmatched workbooks** (no corresponding PBRER topic found): "
                   f"{', '.join(mapping.unmatched_workbooks)}")

    st.caption("Confidence is term-overlap between the PBRER's own search-criteria text and the "
               "Excel cover page's criterion value -- not a guess from the heading's number or filename.")
