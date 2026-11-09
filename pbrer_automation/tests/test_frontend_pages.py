"""
Headless verification that all 10 Streamlit pages (prompt.md Part 7)
actually render without exceptions -- both before any run (empty
session state) and against a real, completed pipeline result. No
browser is available in this environment; streamlit.testing.v1.AppTest
drives the real Streamlit script-running machinery (widgets, session
state, layout) without a browser, which is the closest verification
possible here short of a manual click-through.

Marked slow: depends on the `pipeline_result` fixture, which runs the
real pipeline against the real development fixtures.
"""
from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.slow


def _run_dashboard():
    from frontend.pages import dashboard
    dashboard.render()


def _run_upload():
    from frontend.pages import upload
    upload.render()


def _run_document_analysis():
    from frontend.pages import document_analysis
    document_analysis.render()


def _run_excel_analysis():
    from frontend.pages import excel_analysis
    excel_analysis.render()


def _run_topic_mapping():
    from frontend.pages import topic_mapping
    topic_mapping.render()


def _run_traceability():
    from frontend.pages import traceability
    traceability.render()


def _run_calculation_review():
    from frontend.pages import calculation_review
    calculation_review.render()


def _run_results():
    from frontend.pages import results
    results.render()


def _run_validation():
    from frontend.pages import validation
    validation.render()


def _run_downloads():
    from frontend.pages import downloads
    downloads.render()


ALL_PAGES = [
    _run_dashboard, _run_upload, _run_document_analysis, _run_excel_analysis, _run_topic_mapping,
    _run_traceability, _run_calculation_review, _run_results, _run_validation, _run_downloads,
]


@pytest.mark.parametrize("page_fn", ALL_PAGES, ids=[f.__name__ for f in ALL_PAGES])
def test_page_renders_with_no_run_yet(page_fn):
    at = AppTest.from_function(page_fn)
    at.run()
    assert not at.exception, f"{page_fn.__name__} raised with no pipeline run yet: {at.exception}"


@pytest.mark.parametrize("page_fn", ALL_PAGES, ids=[f.__name__ for f in ALL_PAGES])
def test_page_renders_with_real_completed_run(page_fn, pipeline_result):
    at = AppTest.from_function(page_fn)
    at.session_state["pipeline_result"] = pipeline_result
    at.run()
    assert not at.exception, f"{page_fn.__name__} raised with a real completed run: {at.exception}"


def test_topic_mapping_page_shows_editable_mapping_table(pipeline_result):
    """prompt.md line 881: Topic Mapping page must support manual
    correction/approval, not just a read-only table."""
    at = AppTest.from_function(_run_topic_mapping)
    at.session_state["pipeline_result"] = pipeline_result
    at.run()
    assert not at.exception
    assert len(at.get("data_editor")) >= 1, "expected an editable (st.data_editor) mapping table"
    assert any(b.label.startswith("Apply corrections") for b in at.button)


def test_validation_page_shows_mandatory_checks_and_reconstruction(pipeline_result):
    at = AppTest.from_function(_run_validation)
    at.session_state["pipeline_result"] = pipeline_result
    at.run()
    assert not at.exception
    headers = [h.value for h in at.subheader]
    assert any("Mandatory checks" in h for h in headers)
    assert any("reconstruction" in h.lower() for h in headers)
