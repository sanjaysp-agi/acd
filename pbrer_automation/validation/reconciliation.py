"""
Benchmark comparison: calculated figures vs. historical figures already
extracted from the previous/approved PBRER by the Document Agent. This
is a development/QA aid, NOT a substitute for methodological review -- a
match does not prove the methodology is correct (prompt.md Part 6), and
if a topic has no historical figures (e.g. Cardiac failure, downgraded
and no longer reported) the comparison is marked "unverified", never
fabricated.
"""
from __future__ import annotations

from datetime import datetime, UTC

from models.schemas import BenchmarkReport, BenchmarkRow, MetricResult


def build_benchmark_report(run_id: str, metric_results: list[MetricResult]) -> BenchmarkReport:
    rows = []
    for mr in metric_results:
        label = f"{mr.pbrer_section_number or '?'} {mr.topic_heading} -- {mr.metric_id}"
        if mr.historical_value is None:
            rows.append(BenchmarkRow(metric_label=label, expected=None, calculated=mr.calculated_value,
                                      difference=None, status="unverified"))
            continue
        status = "match" if mr.difference == 0 else "mismatch"
        rows.append(BenchmarkRow(metric_label=label, expected=mr.historical_value,
                                  calculated=mr.calculated_value, difference=mr.difference, status=status))
    return BenchmarkReport(run_id=run_id, generated_at=datetime.now(UTC), rows=rows)
