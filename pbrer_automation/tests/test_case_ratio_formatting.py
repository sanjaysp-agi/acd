"""
Fast unit tests for generation/formatting.py -- the "numerator/denominator"
case-count display rule (e.g. "55/242") shared by the Word report and both
Excel exports.
"""
from __future__ import annotations

from generation.formatting import case_ratio_denominator, format_case_ratio


def test_format_case_ratio_uses_topic_case_count_as_denominator():
    topic_metrics = {"topic_case_count": 242, "serious_case_count": 55}
    assert format_case_ratio("serious_case_count", 55, topic_metrics) == "55/242"


def test_format_case_ratio_uses_total_case_count_for_the_all_case_grouping():
    topic_metrics = {"total_case_count": 3651, "serious_case_count": 7}
    assert format_case_ratio("serious_case_count", 7, topic_metrics) == "7/3651"


def test_format_case_ratio_leaves_value_unchanged_without_a_denominator():
    assert format_case_ratio("serious_case_count", 55, {}) == 55


def test_format_case_ratio_leaves_non_ratio_metrics_unchanged():
    topic_metrics = {"topic_case_count": 242}
    assert format_case_ratio("topic_case_count", 242, topic_metrics) == 242


def test_case_ratio_denominator_prefers_topic_over_total():
    topic_metrics = {"topic_case_count": 242, "total_case_count": 3651}
    assert case_ratio_denominator(topic_metrics) == 242
