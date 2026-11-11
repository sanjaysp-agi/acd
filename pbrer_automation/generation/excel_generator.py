"""
Generates the downloadable calculation-results Excel workbook. Pure
openpyxl, deterministic -- a presentation step, not a source of truth.
"""
from __future__ import annotations

from pathlib import Path

import openpyxl
from openpyxl.styles import Font

from generation.formatting import format_case_ratio
from models.schemas import MetricResult


def generate_results_workbook(metric_results: list[MetricResult], output_path: str | Path) -> str:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Calculated Metrics"
    headers = ["Section", "Topic", "Metric", "Calculated Value", "Historical Value", "Difference",
               "Validation Status", "Source Workbook", "Source Sheet"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    # Grouped by topic first (metric_id -> calculated_value) so
    # serious_case_count/fatal_case_count rows can look up their sibling
    # topic_case_count/total_case_count denominator -- see
    # generation.formatting.format_case_ratio.
    topic_metrics_by_key: dict[str, dict] = {}
    for mr in metric_results:
        key = mr.pbrer_section_number or "total"
        topic_metrics_by_key.setdefault(key, {})[mr.metric_id] = mr.calculated_value

    for mr in metric_results:
        value = mr.calculated_value
        if isinstance(value, dict):
            value = "; ".join(f"{k}={v}" for k, v in value.items())
        elif isinstance(value, list):
            value = "; ".join(str(v) for v in value[:10])
        else:
            topic_metrics = topic_metrics_by_key.get(mr.pbrer_section_number or "total", {})
            value = format_case_ratio(mr.metric_id, value, topic_metrics)
        ws.append([
            mr.pbrer_section_number or "", mr.topic_heading, mr.metric_id, value,
            mr.historical_value, mr.difference, mr.validation_status,
            mr.evidence.source_workbook, mr.evidence.source_sheet,
        ])

    for col_cells in ws.columns:
        max_len = max((len(str(c.value)) for c in col_cells if c.value is not None), default=10)
        ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 2, 60)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return str(output_path)
