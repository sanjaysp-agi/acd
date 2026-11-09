"""Document Analysis page: extracted Section 16.3 structure."""
from __future__ import annotations

import streamlit as st

from frontend.state import get_pipeline_result, has_run


def render():
    st.title("Document Analysis")
    if not has_run():
        st.info("Run the pipeline first (Upload Documents).")
        return

    doc = get_pipeline_result()["document_structure"]

    st.write(f"**Document:** {doc.document_file_name}")
    st.write(f"**Heading detection strategy:** `{doc.heading_style_strategy}`")
    st.write(f"**Target section located:** {doc.target_section_located} -- "
             f"**{doc.target_section_title}**" if doc.target_section_located else "**Target section NOT located**")

    if doc.warnings:
        with st.expander(f"Warnings ({len(doc.warnings)})", expanded=False):
            for w in doc.warnings:
                icon = {"info": "ℹ️", "warning": "⚠️", "critical": "🛑"}.get(w.severity, "")
                st.write(f"{icon} **{w.code}**: {w.message}")

    st.subheader("Topic catalogue")
    for t in doc.topics:
        conf_label = f"confidence {t.section_number_confidence:.2f}" if t.section_number_confidence else "unconfirmed"
        with st.expander(f"{t.section_number} -- {t.title}  ({conf_label})"):
            if t.historical_metrics:
                st.json(t.historical_metrics)
            else:
                st.caption("No historical figures extracted for this topic (no data table found in the document).")
            if t.raw_table_rows:
                st.caption("Raw table rows:")
                st.table(t.raw_table_rows)
