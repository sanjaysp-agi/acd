"""Excel Analysis page: discovered workbooks, classification, mappings."""
from __future__ import annotations

import streamlit as st

from frontend.state import get_pipeline_result, has_run


def render():
    st.title("Excel Analysis")
    if not has_run():
        st.info("Run the pipeline first (Upload Documents).")
        return

    inv = get_pipeline_result()["workbook_inventory"]

    for wb in inv.workbooks:
        label = f"{wb.file_name}  --  {wb.workbook_type.value}  (confidence {wb.classification_confidence:.2f})"
        with st.expander(label):
            st.write(f"**Linked workbook:** {wb.linked_workbook or '—'}")
            st.write(f"**Data grain:** {wb.data_grain.value}")
            st.write("**Classification evidence:**")
            for e in wb.classification_evidence:
                st.caption(f"- {e}")

            if wb.cover_page_criteria and wb.cover_page_criteria.criterion_value:
                st.write(f"**Cover-page criterion:** {wb.cover_page_criteria.criterion_type.value} = "
                         f"{wb.cover_page_criteria.criterion_value}")

            for sheet in wb.sheets:
                if sheet.role != "data_table":
                    continue
                st.write(f"**Sheet `{sheet.sheet_name}`** -- header row {sheet.header_row}, "
                         f"{sheet.row_count} data rows, footer rows {sheet.footer_rows}")

            st.write("**Column mappings:**")
            rows = [{"raw_column": m.raw_column, "canonical_field": m.canonical_field,
                     "confidence": m.confidence, "needs_review": m.needs_review}
                    for m in wb.column_mappings]
            st.table(rows)

            if wb.warnings:
                for w in wb.warnings:
                    st.caption(f"⚠️ {w.message}")
