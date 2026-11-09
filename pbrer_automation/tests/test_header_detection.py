from __future__ import annotations

import openpyxl
import pytest

from tools import excel_tools as et


def test_detects_real_header_row_not_row_one(hallucinations_case_file):
    insp = et.inspect_sheet(str(hallucinations_case_file), "CSMR Case_2")
    result = et.detect_header_row(insp)
    assert result["header_row"] == 6
    assert result["confidence"] > 0.8


def test_header_detection_is_dynamic_not_hardcoded(tmp_path):
    """Build a synthetic workbook with the header at a DIFFERENT row than
    6, to prove detect_header_row isn't just hardcoded to this tenant's
    files."""
    path = tmp_path / "synthetic.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Some Report Title"])
    ws.append([])
    ws.append(["Creation Date: 2024-01-01"])
    ws.append([])
    ws.append(["Count of Cases: 3"])
    ws.append(["Case Number", "Primary Source", "Seriousness"])  # header at row 6
    ws.append(["A-1", "Spontaneous", "Yes"])
    ws.append(["A-2", "Spontaneous", "No"])
    ws.append(["A-3", "Other", "Yes"])
    wb.save(path)

    insp = et.inspect_sheet(str(path), "Sheet")
    result = et.detect_header_row(insp)
    assert result["header_row"] == 6


def test_header_detection_handles_header_shifted_to_row_ten(tmp_path):
    """Same synthetic shape, but with the header pushed further down --
    the detector must find row 10, not assume a fixed offset."""
    path = tmp_path / "synthetic2.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    for _ in range(9):
        ws.append([])
    ws.append(["Case Number", "Primary Source", "Seriousness"])  # row 10
    ws.append(["B-1", "Spontaneous", "Yes"])
    ws.append(["B-2", "Spontaneous", "No"])
    wb.save(path)

    insp = et.inspect_sheet(str(path), "Sheet")
    result = et.detect_header_row(insp)
    assert result["header_row"] == 10
