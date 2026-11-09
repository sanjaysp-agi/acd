"""
Synthetic date-boundary tests (prompt.md Part 5, mandatory check #14):
records immediately before, on, and after both reporting boundaries.
Both boundaries are inclusive.
"""
from __future__ import annotations

import pandas as pd

from processing.date_normalizer import filter_by_reporting_period

REPORTING_START = "2019-04-07"
REPORTING_END = "2024-04-06"


def _df(dates: list[int]) -> pd.DataFrame:
    return pd.DataFrame({"case_id": [f"C{i}" for i in range(len(dates))], "date": dates})


def test_start_boundary_day_before_is_excluded():
    df = _df([20190406])  # one day before start
    result = filter_by_reporting_period(df, "date", REPORTING_START, REPORTING_END, "YYYYMMDD_numeric")
    assert result["rows_in_period"] == 0


def test_start_boundary_exact_day_is_included():
    df = _df([20190407])  # exactly on start boundary
    result = filter_by_reporting_period(df, "date", REPORTING_START, REPORTING_END, "YYYYMMDD_numeric")
    assert result["rows_in_period"] == 1


def test_start_boundary_day_after_is_included():
    df = _df([20190408])
    result = filter_by_reporting_period(df, "date", REPORTING_START, REPORTING_END, "YYYYMMDD_numeric")
    assert result["rows_in_period"] == 1


def test_end_boundary_day_before_is_included():
    df = _df([20240405])
    result = filter_by_reporting_period(df, "date", REPORTING_START, REPORTING_END, "YYYYMMDD_numeric")
    assert result["rows_in_period"] == 1


def test_end_boundary_exact_day_is_included():
    df = _df([20240406])  # exactly on end boundary
    result = filter_by_reporting_period(df, "date", REPORTING_START, REPORTING_END, "YYYYMMDD_numeric")
    assert result["rows_in_period"] == 1


def test_end_boundary_day_after_is_excluded():
    df = _df([20240407])  # one day after end
    result = filter_by_reporting_period(df, "date", REPORTING_START, REPORTING_END, "YYYYMMDD_numeric")
    assert result["rows_in_period"] == 0


def test_all_boundary_cases_together():
    df = _df([20190406, 20190407, 20190408, 20240405, 20240406, 20240407])
    result = filter_by_reporting_period(df, "date", REPORTING_START, REPORTING_END, "YYYYMMDD_numeric")
    assert result["rows_in_period"] == 4  # excludes the two outside-boundary rows
    assert result["rows_outside_period"] == 2
