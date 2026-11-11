"""
Fast unit tests for the extraction-completeness escalation added to
tools/review_tools.check_extraction_completeness: a topic with no
extracted table rows is a much stronger signal of a genuine extraction
failure when the document's headings were detected via a weaker,
non-format-backed strategy (e.g. .pdf's font_size_heuristic) than when
detected via a format-backed one (numbered_heading / docx style_name /
outline_level).
"""
from __future__ import annotations

from tools.review_tools import check_extraction_completeness

_TOPIC_WITH_NO_TABLE_ROWS = [{
    "section_number": "16.3.1.1", "title": "Cardiac failure",
    "historical_metrics": {}, "raw_table_rows": [],
}]


def _find_missing_table_finding(findings: list[dict]) -> dict:
    return next(f for f in findings if "No data table rows" in f["message"])


def test_missing_table_rows_escalates_to_warning_under_weaker_heading_strategy():
    out = check_extraction_completeness(_TOPIC_WITH_NO_TABLE_ROWS, [], [],
                                          heading_style_strategy="font_size_heuristic")
    assert _find_missing_table_finding(out["findings"])["severity"] == "warning"


def test_missing_table_rows_stays_info_under_a_format_backed_strategy():
    out = check_extraction_completeness(_TOPIC_WITH_NO_TABLE_ROWS, [], [],
                                          heading_style_strategy="numbered_heading")
    assert _find_missing_table_finding(out["findings"])["severity"] == "info"


def test_missing_table_rows_defaults_to_info_when_strategy_not_provided():
    out = check_extraction_completeness(_TOPIC_WITH_NO_TABLE_ROWS, [], [])
    assert _find_missing_table_finding(out["findings"])["severity"] == "info"


def test_escalation_never_happens_when_table_rows_are_present():
    topic = [{**_TOPIC_WITH_NO_TABLE_ROWS[0], "raw_table_rows": [{"label": "x", "value": "1"}]}]
    out = check_extraction_completeness(topic, [], [], heading_style_strategy="font_size_heuristic")
    assert not any("No data table rows" in f["message"] for f in out["findings"])
