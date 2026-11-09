from __future__ import annotations

import pandas as pd

from processing.date_normalizer import normalize_date_column
from tools.excel_tools import normalize_date_value


def test_normalize_numeric_yyyymmdd():
    series = pd.Series([20190407, 20200115, 20240325])
    out = normalize_date_column(series, "YYYYMMDD_numeric")
    assert list(out.dt.strftime("%Y-%m-%d")) == ["2019-04-07", "2020-01-15", "2024-03-25"]


def test_normalize_single_value_variants():
    assert normalize_date_value(20190407) == "2019-04-07"
    assert normalize_date_value("20190407.0") == "2019-04-07"
    assert normalize_date_value(None) is None
    assert normalize_date_value("not-a-date") is None


def test_unparseable_dates_become_nat_not_dropped_silently():
    series = pd.Series([20190407, None, "garbage"])
    out = normalize_date_column(series, "YYYYMMDD_numeric")
    assert out.isna().sum() == 2  # None and "garbage" both fail to parse
    assert len(out) == 3  # row count preserved -- nothing silently removed
