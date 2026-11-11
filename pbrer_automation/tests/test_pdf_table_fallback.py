"""
Regression test for tools.document_tools._find_tables_on_page.

A whitespace/text-alignment fallback strategy (retried when the default
"lines" strategy finds zero tables on a page) was tried here and
REVERTED: validated against a real multi-page PBRER PDF export, it was
found to misclassify a page's own heading line as part of a false-
positive "table" on an otherwise plain-text page, which silently dropped
that heading from the paragraph stream and broke target-section location
entirely (the real failure mode behind the PDF-upload ticket this file
was added for: 0 topics found with the fallback enabled, vs. 1 without
it -- and ultimately 7, the correct count, once the real root cause --
tools.document_tools._numbered_heading_headings' false-positive numbered-
heading matches, see test_pdf_heading_false_positives.py -- was fixed
instead). This test locks in the reverted (single-strategy) behavior so
a future attempt at a borderless-table fallback is a deliberate, tested
change rather than an accidental regression.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from tools.document_tools import _find_tables_on_page


def test_uses_only_the_default_line_based_strategy():
    page = MagicMock()
    page.find_tables.return_value = ["real_table"]

    result = _find_tables_on_page(page)

    assert result == ["real_table"]
    page.find_tables.assert_called_once_with()


def test_returns_empty_when_the_default_strategy_finds_nothing_rather_than_guessing():
    page = MagicMock()
    page.find_tables.return_value = []

    result = _find_tables_on_page(page)

    assert result == []
    page.find_tables.assert_called_once_with()
