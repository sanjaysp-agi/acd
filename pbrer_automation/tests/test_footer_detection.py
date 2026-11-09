from __future__ import annotations

from tools import excel_tools as et


def test_footer_rows_excluded_without_losing_valid_records(hallucinations_case_file):
    insp = et.inspect_sheet(str(hallucinations_case_file), "CSMR Case_2")
    header_row = et.detect_header_row(insp)["header_row"]
    footer = et.detect_footer_rows(str(hallucinations_case_file), "CSMR Case_2", header_row)

    # Known from manual inspection: 2 trailing footer rows, real data ends at 2474.
    assert footer["footer_rows"] == [2475, 2476]
    assert footer["effective_last_data_row"] == 2474
    # Every removed row must be accounted for in evidence (prompt.md Part 2.B).
    assert len(footer["removed_row_evidence"]) == len(footer["footer_rows"])
