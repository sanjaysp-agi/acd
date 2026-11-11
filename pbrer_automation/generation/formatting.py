"""
Shared display-formatting helpers for generated reports/exports.

Kept in one place so the Word report (docx_generator), the two Excel
exports (excel_generator, report_generator) and the frontend
(web/js/lib/businessMetrics.js -- same rule, reimplemented in JS since the
frontend reads the API's JSON directly rather than this module) all render
a case count the same way: a serious/fatal case count is always shown as
"numerator/denominator" (e.g. "55/242") against its topic's total case
count, never a bare number a reviewer has to cross-reference a second row
to make sense of.
"""
from __future__ import annotations

from typing import Any

# A serious/fatal case count is only ever a fraction of the topic's (or,
# for the "total" grouping, the all-case) distinct case count -- never
# invented against an unrelated denominator.
RATIO_NUMERATOR_METRIC_IDS: tuple[str, ...] = ("serious_case_count", "fatal_case_count")
RATIO_DENOMINATOR_METRIC_IDS: tuple[str, ...] = ("topic_case_count", "total_case_count")


def case_ratio_denominator(topic_metrics: dict[str, Any]) -> int | None:
    """`topic_metrics`: metric_id -> calculated_value, scoped to ONE topic/
    section grouping. Returns the first integer-valued case-count metric
    present, or None if neither exists -- never fabricates a denominator."""
    for key in RATIO_DENOMINATOR_METRIC_IDS:
        value = topic_metrics.get(key)
        if isinstance(value, int):
            return value
    return None


def format_case_ratio(metric_id: str, value: Any, topic_metrics: dict[str, Any]) -> Any:
    """Returns "numerator/denominator" for serious_case_count/fatal_case_count
    when a sibling topic_case_count/total_case_count is available in the
    same topic grouping; otherwise returns `value` unchanged."""
    if metric_id not in RATIO_NUMERATOR_METRIC_IDS or not isinstance(value, int):
        return value
    denominator = case_ratio_denominator(topic_metrics)
    if denominator is None:
        return value
    return f"{value}/{denominator}"
