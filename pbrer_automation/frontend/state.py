"""Shared Streamlit session-state helpers."""
from __future__ import annotations

import streamlit as st


def get_pipeline_result():
    return st.session_state.get("pipeline_result")


def get_run_id() -> str | None:
    result = get_pipeline_result()
    return result["run_id"] if result else None


def has_run() -> bool:
    return get_pipeline_result() is not None
