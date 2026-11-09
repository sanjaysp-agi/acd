"""
PBRER Section 16.3 Automation -- Streamlit entry point.

No AWS/Bedrock configuration, credentials, or model IDs are exposed here
(prompt.md Part 7/8). The only end-user inputs are on the Upload
Documents page: the previous PBRER, the current Excel exports, and the
reporting interval.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

from frontend.pages import calculation_review, dashboard, document_analysis, downloads, excel_analysis
from frontend.pages import results as results_page
from frontend.pages import topic_mapping, traceability, upload, validation

st.set_page_config(page_title="PBRER Section 16.3 Automation", layout="wide")

PAGES = {
    "Dashboard": dashboard.render,
    "Upload Documents": upload.render,
    "Document Analysis": document_analysis.render,
    "Excel Analysis": excel_analysis.render,
    "Topic Mapping": topic_mapping.render,
    "Agent Execution & Traceability": traceability.render,
    "Calculation Review": calculation_review.render,
    "Results Dashboard": results_page.render,
    "Validation & Audit": validation.render,
    "Downloads": downloads.render,
}

st.sidebar.title("PBRER Automation")
choice = st.sidebar.radio("Navigate", list(PAGES.keys()))
PAGES[choice]()
