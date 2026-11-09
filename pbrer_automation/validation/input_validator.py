"""
Input-file and workbook-structure validation (prompt.md Part 5 mandatory
checks #1-4): input file validation, workbook/sheet identification,
dynamic header detection, footer detection. These run over the Excel
Agent's own structural findings (models.schemas.WorkbookInventory) --
they do not re-open the files; they check that the agent's investigation
actually produced usable structural evidence for every discovered
workbook, so a silently-failed inspection doesn't flow downstream as if
it had succeeded.
"""
from __future__ import annotations

from pathlib import Path

from models.schemas import ValidationCheckResult, WorkbookInventory
from config.metric_registry import WorkbookType


def check_input_files_present(docx_path: str | Path | None, excel_dir: str | Path,
                                 discovered_excel_files: list[dict]) -> ValidationCheckResult:
    """Mandatory check #1. The previous/approved PBRER and at least one
    Excel export must actually be present and discoverable before any
    agent runs -- a missing/unreadable input must be visible, not
    silently treated as "zero topics"."""
    issues = []
    if not docx_path or not Path(docx_path).exists():
        issues.append(f"Previous/approved PBRER not found at '{docx_path}'.")
    if not discovered_excel_files:
        issues.append(f"No Excel workbooks discovered in '{excel_dir}'.")
    return ValidationCheckResult(
        check_name="input_file_validation",
        status="pass" if not issues else "fail",
        message="Previous PBRER and at least one Excel export are present." if not issues
                else "; ".join(issues),
        evidence={"docx_path": str(docx_path) if docx_path else None,
                   "excel_file_count": len(discovered_excel_files)},
    )


def check_workbook_identification(workbook_inventory: WorkbookInventory) -> list[ValidationCheckResult]:
    """Mandatory check #2: every discovered workbook must have resolved to
    a known workbook type with at least one identified sheet. An
    UNCLASSIFIED workbook, or one with zero recognized sheets, cannot
    safely feed any calculation and must be surfaced for review."""
    checks = []
    for wb in workbook_inventory.workbooks:
        identified_sheets = [s for s in wb.sheets if s.role in ("cover_page", "data_table")]
        ok = wb.workbook_type != WorkbookType.UNCLASSIFIED and len(identified_sheets) > 0
        checks.append(ValidationCheckResult(
            check_name="workbook_sheet_identification",
            status="pass" if ok else "warning",
            message=f"'{wb.file_name}' classified as {wb.workbook_type.value} with "
                     f"{len(identified_sheets)} identified sheet(s)." if ok else
                     f"'{wb.file_name}' classified as {wb.workbook_type.value} with no sheet "
                     "confidently identified as a cover page or data table -- needs review.",
            evidence={"file_name": wb.file_name, "workbook_type": wb.workbook_type.value,
                       "sheet_count": len(wb.sheets), "identified_sheet_count": len(identified_sheets)},
        ))
    return checks


def check_header_detection(workbook_inventory: WorkbookInventory) -> list[ValidationCheckResult]:
    """Mandatory check #3: every data-table sheet must have an actual
    detected header row, not an assumed default -- never a silent
    fall-through to 'row 1' or 'row 6'."""
    checks = []
    for wb in workbook_inventory.workbooks:
        for sheet in wb.sheets:
            if sheet.role != "data_table":
                continue
            ok = sheet.header_row is not None
            checks.append(ValidationCheckResult(
                check_name="dynamic_header_detection",
                status="pass" if ok else "fail",
                message=f"'{wb.file_name}' / '{sheet.sheet_name}': header row detected at row "
                         f"{sheet.header_row}." if ok else
                         f"'{wb.file_name}' / '{sheet.sheet_name}': no header row could be detected "
                         "-- this sheet cannot be used for any calculation.",
                evidence={"file_name": wb.file_name, "sheet_name": sheet.sheet_name,
                           "header_row": sheet.header_row, "detection_evidence": sheet.detection_evidence},
            ))
    return checks


def check_footer_detection(workbook_inventory: WorkbookInventory) -> list[ValidationCheckResult]:
    """Mandatory check #4: footer/boilerplate rows must be explicitly
    accounted for (even if the answer is "none found") rather than left
    undetermined -- every removed row must be auditable, never silently
    dropped (prompt.md line 230)."""
    checks = []
    for wb in workbook_inventory.workbooks:
        for sheet in wb.sheets:
            if sheet.role != "data_table":
                continue
            # data_end_row is only ever set once detect_footer_rows actually ran
            # (agents/excel_agent.py); its absence means footer detection never
            # executed for this sheet, not that there was nothing to find.
            ok = sheet.data_end_row is not None
            checks.append(ValidationCheckResult(
                check_name="footer_detection",
                status="pass" if ok else "warning",
                message=f"'{wb.file_name}' / '{sheet.sheet_name}': footer detection ran, "
                         f"{len(sheet.footer_rows)} footer row(s) excluded, effective data end row "
                         f"{sheet.data_end_row}." if ok else
                         f"'{wb.file_name}' / '{sheet.sheet_name}': footer detection did not run "
                         "-- row count used for calculations is unverified.",
                evidence={"file_name": wb.file_name, "sheet_name": sheet.sheet_name,
                           "footer_rows": sheet.footer_rows, "data_end_row": sheet.data_end_row},
            ))
    return checks
