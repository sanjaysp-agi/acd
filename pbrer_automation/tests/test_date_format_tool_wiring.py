from __future__ import annotations

import openpyxl

from agents.excel_agent import ExcelUnderstandingAgent


def _build_data_workbook(path, salt: str):
    """7 columns / 45 rows so tools.excel_tools._guess_sheet_role's
    structural heuristic classifies this as a data table, not a cover
    page -- forcing the agent down the header-detection/profiling path
    where detect_date_formats should be invoked. `salt` (a value unique
    to the calling test) keeps each test's file content -- and therefore
    its analysis-cache content hash -- from colliding with another
    test's otherwise-identical synthetic workbook."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Case Number", "Initial Approval Date", "Primary Source", "Patient Race",
               "Filler 1", "Filler 2", "Filler 3"])
    for i in range(44):
        ws.append([f"C-{i}", 20200101 + i, "Spontaneous", "Unknown", "x", "y", salt])
    wb.save(path)


def test_excel_agent_invokes_detect_date_formats_tool(tmp_path):
    path = tmp_path / "synthetic_data.xlsx"
    _build_data_workbook(path, salt=f"date_format_tool_wiring_{tmp_path.name}")

    agent = ExcelUnderstandingAgent()
    outcome = agent.investigate_workbook("test-run", str(path), path.name)

    tool_names = [c.tool_name for c in outcome["agent_result"].tool_calls]
    assert "detect_date_formats" in tool_names, (
        f"detect_date_formats should be invoked once a column maps to the initial-approval-date "
        f"canonical field, but the actual tool calls were: {tool_names}")

    entry = outcome["entry"]
    date_mapping = next(m for m in entry["column_mappings"] if m.get("canonical_field") == "initial_approval_date")
    data_sheet = next(s for s in entry["sheets"] if s["role"] == "data_table")
    profile = next(p for p in data_sheet["column_profiles"] if p["column_name"] == date_mapping["raw_column"])
    assert profile["possible_date_format"] == "YYYYMMDD_numeric"


def test_excel_agent_analysis_cache_hit_skips_second_investigation(tmp_path):
    from config.settings import settings

    assert settings.llm.enable_cache, "test assumes the default (cache enabled) -- see .env.example"
    path = tmp_path / "cached_workbook.xlsx"
    _build_data_workbook(path, salt=f"cache_hit_test_{tmp_path.name}")

    agent = ExcelUnderstandingAgent()
    first = agent.investigate_workbook("run-1", str(path), path.name)
    assert first["agent_result"] is not None
    assert len(first["agent_result"].tool_calls) > 0

    second = agent.investigate_workbook("run-2", str(path), path.name)
    # A cache hit short-circuits before any ToolCallingAgent runs at all.
    assert second["agent_result"] is None
    assert second["entry"]["file_name"] == first["entry"]["file_name"]
