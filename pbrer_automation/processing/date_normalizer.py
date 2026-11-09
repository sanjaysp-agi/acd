"""
Deterministic date normalization and reporting-period filtering.
No AI involved -- this is the calculation engine, not an understanding
agent. Both reporting-period boundaries are inclusive (per the
development-only traceability HTML's documented methodology).
"""
from __future__ import annotations

import pandas as pd


def normalize_date_column(series: pd.Series, date_format_hint: str | None = None) -> pd.Series:
    """Normalize a raw date column to pandas Timestamps. Handles the
    numeric-YYYYMMDD format observed in these CSMR exports, plain
    datetimes, and common string formats. Unparseable values become NaT
    (never silently dropped or coerced to a default date)."""
    if date_format_hint == "YYYYMMDD_numeric" or pd.api.types.is_numeric_dtype(series):
        # pd.to_numeric with errors="coerce" first: a column that is
        # MOSTLY numeric-YYYYMMDD can still contain stray non-numeric
        # garbage (bad export, manual edit). astype("Int64") directly
        # would raise on that instead of reporting it as an unparseable
        # date -- coercing to NaN first keeps this a reporting case, not
        # a crash.
        numeric = pd.to_numeric(series, errors="coerce").astype("Int64")
        as_str = numeric.astype(str)
        return pd.to_datetime(as_str, format="%Y%m%d", errors="coerce")
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, errors="coerce")
    return pd.to_datetime(series, errors="coerce")


def filter_by_reporting_period(df: pd.DataFrame, date_column: str, start: str, end: str,
                                 date_format_hint: str | None = None) -> dict:
    """Apply the INCLUSIVE reporting-period filter. Returns the filtered
    dataframe plus counts needed for audit evidence (never silently drop
    rows without accounting for them)."""
    dates = normalize_date_column(df[date_column], date_format_hint)
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    in_period = (dates >= start_ts) & (dates <= end_ts)
    unparseable = dates.isna() & df[date_column].notna()
    return {
        "filtered_df": df[in_period],
        "rows_before": len(df),
        "rows_in_period": int(in_period.sum()),
        "rows_outside_period": int((~in_period & dates.notna()).sum()),
        "rows_unparseable_date": int(unparseable.sum()),
    }
