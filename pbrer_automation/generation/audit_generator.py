"""
Generates the calculation audit-trail workbook: one row per metric, with
the full CalculationEvidence fields that let a reviewer trace exactly
how each number was produced (prompt.md Part 5 / 4.D).
"""
from __future__ import annotations

from pathlib import Path

import openpyxl
from openpyxl.styles import Font

from models.schemas import MetricResult


def generate_audit_workbook(metric_results: list[MetricResult], output_path: str | Path) -> str:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Audit Trail"
    headers = ["Section", "Topic", "Metric", "Source Workbook", "Source Sheet", "Header Row",
               "Case ID Column", "Date Column", "Date Format", "Reporting Start", "Reporting End",
               "Source Exclusion Applied", "Source Exclusion Values Matched",
               "Rows Before Filter", "Rows After Filter", "Distinct Case Count", "Event Row Count",
               "Calculation Function", "Validation Status", "Validation Messages"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for mr in metric_results:
        e = mr.evidence
        ws.append([
            mr.pbrer_section_number or "", mr.topic_heading, mr.metric_id, e.source_workbook, e.source_sheet,
            e.header_row, e.case_id_column, e.date_column, e.date_format, e.reporting_start, e.reporting_end,
            e.source_exclusion_applied, ", ".join(e.source_exclusion_values_matched),
            e.rows_before_filter, e.rows_after_filter, e.distinct_case_count, e.event_row_count,
            e.calculation_function, mr.validation_status, " | ".join(mr.validation_messages),
        ])

    for col_cells in ws.columns:
        max_len = max((len(str(c.value)) for c in col_cells if c.value is not None), default=10)
        ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 2, 50)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return str(output_path)
