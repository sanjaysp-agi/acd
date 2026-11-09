"""
Generates the report-ready Section 16.3 numerical output and the
benchmark comparison report, as Excel workbooks (simple, reviewable,
no clinical narrative -- purely numerical, per prompt.md's restriction
against generating clinical conclusions).
"""
from __future__ import annotations

from pathlib import Path

import openpyxl
from openpyxl.styles import Font

from models.schemas import BenchmarkReport, MetricResult


def _cell_safe(value):
    """openpyxl cells accept scalars only -- a metric's calculated value
    can be a dict (source_breakdown) or list (event_pt_frequency), which
    must be stringified before writing rather than crashing the whole
    workbook generation."""
    if isinstance(value, dict):
        return "; ".join(f"{k}={v}" for k, v in value.items())
    if isinstance(value, list):
        return "; ".join(str(v) for v in value[:10])
    return value


def generate_report_ready_output(metric_results: list[MetricResult], output_path: str | Path) -> str:
    by_topic: dict[str, dict] = {}
    for mr in metric_results:
        key = mr.pbrer_section_number or "total"
        entry = by_topic.setdefault(key, {"heading": mr.topic_heading, "metrics": {}})
        entry["metrics"][mr.metric_id] = mr.calculated_value

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Section 16.3 Figures"
    headers = ["Section", "Topic", "Total Cases", "Spontaneous", "Other Studies", "Serious Cases",
               "Serious %", "Fatal Cases", "Fatal %"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for section, entry in sorted(by_topic.items()):
        m = entry["metrics"]
        breakdown = m.get("source_breakdown") or {}
        topic_count = m.get("topic_case_count") or m.get("total_case_count")
        serious = m.get("serious_case_count")
        fatal = m.get("fatal_case_count")
        serious_pct = round(100 * serious / topic_count, 1) if serious is not None and topic_count else None
        fatal_pct = round(100 * fatal / topic_count, 1) if fatal is not None and topic_count else None
        ws.append([
            section, entry["heading"], topic_count,
            next((v for k, v in breakdown.items() if "spontaneous" in str(k).lower()), None),
            next((v for k, v in breakdown.items() if "other" in str(k).lower()), None),
            serious, serious_pct, fatal, fatal_pct,
        ])

    for col_cells in ws.columns:
        max_len = max((len(str(c.value)) for c in col_cells if c.value is not None), default=10)
        ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 2, 40)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return str(output_path)


def generate_benchmark_workbook(benchmark_report: BenchmarkReport, output_path: str | Path) -> str:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Benchmark Comparison"
    ws.append(["Metric", "Expected", "Calculated", "Difference", "Status"])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in benchmark_report.rows:
        expected = _cell_safe(row.expected)
        calculated = _cell_safe(row.calculated)
        ws.append([row.metric_label, expected, calculated, row.difference, row.status])

    for col_cells in ws.columns:
        max_len = max((len(str(c.value)) for c in col_cells if c.value is not None), default=10)
        ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 2, 60)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return str(output_path)
