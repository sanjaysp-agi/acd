"""
Predefined, typed Python tools for autonomous Excel investigation.

These are the ONLY operations the Excel Understanding Agent may invoke. No
tool here assumes a fixed sheet count, a fixed header row, or a fixed
column set for any given workbook -- every file is inspected from raw cell
content at call time. The 8 Sifrol CSMR files used during development all
happen to share one template; that uniformity is a property of THESE
fixtures, not an assumption baked into the detectors below. A different
tenant's export can have a different sheet count, a header at a different
row, merged cells in different places, or extra columns, and these tools
must still work.

Library usage, per tool, matches prompt.md Part 2.A:
  - discover_excel_files   -> pathlib
  - inspect_workbook       -> openpyxl
  - inspect_sheet          -> openpyxl
  - detect_header_row      -> openpyxl + pandas
  - detect_data_region     -> pandas
  - detect_footer_rows     -> pandas + custom logic
  - profile_columns        -> pandas
  - detect_date_formats    -> pandas + custom logic
  - extract_cover_page_criteria -> openpyxl
  - classify_workbook      -> Python heuristics (AI agent interprets result)
  - map_columns_to_schema  -> Python heuristics (AI agent interprets result)
  - match_workbooks        -> Python heuristics (AI agent interprets result)
"""
from __future__ import annotations

import re
import unicodedata
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openpyxl
import pandas as pd
from openpyxl.utils import get_column_letter

from config.metric_registry import (
    CanonicalField,
    CriterionType,
    DataGrain,
    WorkbookType,
    is_affirmative,
    is_clinical_trial_source,
)


# ===========================================================================
# 1. discover_excel_files
# ===========================================================================
def discover_excel_files(input_dir: str | Path) -> list[dict[str, Any]]:
    """Discover uploaded Excel workbooks. No assumption about filenames."""
    input_dir = Path(input_dir)
    found = []
    for p in sorted(input_dir.glob("*.xlsx")):
        if p.name.startswith("~$"):  # Excel lock files
            continue
        found.append({"file_name": p.name, "file_path": str(p), "size_bytes": p.stat().st_size})
    return found


_MERGE_CELL_REF_PATTERN = re.compile(rb'<mergeCell ref="([^"]+)"')


def _fast_merged_ranges(file_path: str | Path, sheet_xml_name: str) -> list[str]:
    """Read merged-cell ranges straight from a sheet's XML part inside the
    .xlsx zip, via a plain byte regex -- NOT by loading the sheet through
    openpyxl at all. <mergeCells> is a small, separate element from
    <sheetData> (which holds the actual row cells), so this costs almost
    nothing regardless of row count -- unlike openpyxl's normal (non
    read_only) load, which must build a Cell object for every one of
    potentially 60k+ rows just to expose .merged_cells, and unlike
    read_only mode, which doesn't expose merged cells at all."""
    try:
        with zipfile.ZipFile(file_path) as zf:
            with zf.open(sheet_xml_name) as f:
                data = f.read()
    except (KeyError, zipfile.BadZipFile):
        return []
    return [m.decode("ascii") for m in _MERGE_CELL_REF_PATTERN.findall(data)]


def _sheet_name_to_xml_path(file_path: str | Path) -> dict[str, str]:
    """Map sheet display name -> internal worksheets/sheetN.xml path, by
    reading the small workbook.xml + relationships parts (not any sheet
    data)."""
    import xml.etree.ElementTree as ET

    ns = {
        "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    with zipfile.ZipFile(file_path) as zf:
        wb_xml = ET.fromstring(zf.read("xl/workbook.xml"))
        rels_xml = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))

    rid_to_target = {
        rel.get("Id"): rel.get("Target")
        for rel in rels_xml.findall("pr:Relationship", ns)
    }
    name_to_path = {}
    for sheet in wb_xml.findall("m:sheets/m:sheet", ns):
        rid = sheet.get(f"{{{ns['r']}}}id")
        target = rid_to_target.get(rid)
        if target:
            name_to_path[sheet.get("name")] = f"xl/{target}" if not target.startswith("xl/") else target
    return name_to_path


# ===========================================================================
# 2. inspect_workbook
# ===========================================================================
def inspect_workbook(file_path: str | Path) -> dict[str, Any]:
    """Open the workbook and report its raw structure: sheet names, sizes,
    and merged-cell presence per sheet. Makes no assumption about how many
    sheets exist or what they're named.

    Loaded read_only=True: this skips building a full in-memory Cell grid
    with styles for every row, which matters a lot once a sheet runs into
    tens of thousands of rows (the all-case/all-drug-event exports here
    are 28k/63k rows) -- read_only mode is openpyxl's own recommended mode
    for exactly this case. Merge ranges are read separately via
    _fast_merged_ranges since read_only worksheets don't expose them."""
    wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    sheet_xml_paths = _sheet_name_to_xml_path(file_path)
    sheets = []
    for name in wb.sheetnames:
        ws = wb[name]
        sheets.append(
            {
                "sheet_name": name,
                "max_row": ws.max_row,
                "max_col": ws.max_column,
                "merged_cell_ranges": (
                    _fast_merged_ranges(file_path, sheet_xml_paths[name]) if name in sheet_xml_paths else []
                ),
            }
        )
    wb.close()
    return {"file_path": str(file_path), "sheet_count": len(sheets), "sheets": sheets}


# ===========================================================================
# 3. inspect_sheet
# ===========================================================================
def inspect_sheet(file_path: str | Path, sheet_name: str, max_scan_rows: int = 60) -> dict[str, Any]:
    """Read raw cell values (and merge info) for the first `max_scan_rows`
    rows of a sheet, plus the last 10 rows, for structural analysis. Does
    NOT assume where the header or data region is -- that's for
    detect_header_row / detect_footer_rows to determine from this output.

    read_only=True + iter_rows(values_only=True): read_only worksheets do
    not support efficient random ws.cell(row=, column=) access (each call
    would re-scan from the start of the row stream), so the head/tail
    windows are read via bounded iter_rows() calls instead. This is the
    difference between ~1s and ~60s+ on the 28k/63k-row exports here."""
    wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    ws = wb[sheet_name]
    max_row, max_col = ws.max_row, ws.max_column

    head_limit = min(max_scan_rows, max_row)
    head_rows: dict[int, list[Any]] = {}
    for r, row in enumerate(ws.iter_rows(min_row=1, max_row=head_limit, values_only=True), start=1):
        head_rows[r] = list(row)

    tail_start = max(1, max_row - 9)
    tail_rows: dict[int, list[Any]] = {}
    if tail_start > head_limit:
        for r, row in enumerate(ws.iter_rows(min_row=tail_start, max_row=max_row, values_only=True), start=tail_start):
            tail_rows[r] = list(row)

    wb.close()

    from openpyxl.utils.cell import range_boundaries

    sheet_xml_paths = _sheet_name_to_xml_path(file_path)
    merge_by_row: dict[int, list[str]] = {}
    if sheet_name in sheet_xml_paths:
        for ref in _fast_merged_ranges(file_path, sheet_xml_paths[sheet_name]):
            _, min_row, _, max_row_m = range_boundaries(ref)
            for r in range(min_row, max_row_m + 1):
                merge_by_row.setdefault(r, []).append(ref)

    return {
        "file_path": str(file_path),
        "sheet_name": sheet_name,
        "max_row": max_row,
        "max_col": max_col,
        "head_rows": head_rows,
        "tail_rows": tail_rows,
        "merge_by_row": merge_by_row,
    }


# ===========================================================================
# 4. detect_header_row
# ===========================================================================
_HEADER_HINT_PATTERN = re.compile(r"count of|total\s|records?:|as of|creation date", re.IGNORECASE)


def _row_stats(values: list[Any]) -> dict[str, float]:
    non_null = [v for v in values if v is not None and str(v).strip() != ""]
    n_total = len(values) or 1
    n_non_null = len(non_null)
    n_strings = sum(1 for v in non_null if isinstance(v, str))
    unique = len(set(str(v).strip() for v in non_null))
    return {
        "non_null_frac": n_non_null / n_total,
        "string_frac": (n_strings / n_non_null) if n_non_null else 0.0,
        "uniqueness_frac": (unique / n_non_null) if n_non_null else 0.0,
        "non_null_count": n_non_null,
    }


def detect_header_row(sheet_inspection: dict[str, Any], min_columns: int = 2) -> dict[str, Any]:
    """Score candidate header rows using structural evidence, not a fixed
    offset. A header row is: mostly non-null, mostly strings, mostly unique
    values, NOT covered by a wide merge (which indicates a title banner),
    and followed by several rows that each populate a similar number of
    columns (indicating a real data region starts right after it)."""
    # Row-number keys survive a round trip through this process's own
    # memory as ints (local-deterministic mode), but a real LLM provider
    # only ever sees `sheet_inspection` after it's been through JSON (which
    # has no integer-key concept -- object keys are always strings), and
    # reconstructs it the same way when passing it back as this tool's
    # argument. Normalize defensively so both paths behave identically.
    head_rows = {int(k): v for k, v in sheet_inspection["head_rows"].items()}
    merge_by_row = {int(k): v for k, v in sheet_inspection.get("merge_by_row", {}).items()}
    max_col = sheet_inspection["max_col"]
    candidates = []

    sorted_rows = sorted(head_rows.keys())
    for r in sorted_rows:
        values = head_rows[r]
        stats = _row_stats(values)
        if stats["non_null_count"] < min_columns:
            continue

        # Penalize rows that are mostly one wide merge (title/banner rows).
        merges_this_row = merge_by_row.get(r, [])
        wide_merge_penalty = 0.0
        for rng in merges_this_row:
            # crude width estimate from the range string, e.g. "A1:AH4"
            m = re.match(r"([A-Z]+)\d+:([A-Z]+)\d+", rng)
            if m:
                from openpyxl.utils import column_index_from_string

                width = column_index_from_string(m.group(2)) - column_index_from_string(m.group(1)) + 1
                if width >= max_col * 0.5:
                    wide_merge_penalty = 0.6

        # Structural consistency: do the next up-to-5 rows populate a
        # similar number of columns as this candidate header row?
        following = [head_rows[rr] for rr in sorted_rows if r < rr <= r + 6 and rr in head_rows]
        consistency = 0.0
        if following:
            header_non_null = stats["non_null_count"]
            diffs = []
            for fv in following:
                fstats = _row_stats(fv)
                if fstats["non_null_count"] == 0:
                    continue
                diffs.append(abs(fstats["non_null_count"] - header_non_null) / max(header_non_null, 1))
            if diffs:
                consistency = max(0.0, 1.0 - (sum(diffs) / len(diffs)))

        score = (
            0.35 * stats["non_null_frac"]
            + 0.30 * stats["string_frac"]
            + 0.20 * stats["uniqueness_frac"]
            + 0.15 * consistency
            - wide_merge_penalty
        )
        candidates.append(
            {
                "row": r,
                "score": round(score, 4),
                "non_null_count": stats["non_null_count"],
                "string_frac": round(stats["string_frac"], 2),
                "uniqueness_frac": round(stats["uniqueness_frac"], 2),
                "consistency": round(consistency, 2),
                "wide_merge_penalty": wide_merge_penalty,
            }
        )

    if not candidates:
        return {"header_row": None, "confidence": 0.0, "candidates": [], "evidence": ["no viable candidate rows found"]}

    candidates.sort(key=lambda c: c["score"], reverse=True)
    best = candidates[0]
    evidence = [
        f"row {best['row']}: non_null={best['non_null_count']}, "
        f"string_frac={best['string_frac']}, uniqueness_frac={best['uniqueness_frac']}, "
        f"consistency={best['consistency']}"
    ]
    return {
        "header_row": best["row"],
        "confidence": max(0.0, min(1.0, best["score"])),
        "candidates": candidates[:5],
        "evidence": evidence,
    }


# ===========================================================================
# 5. detect_data_region
# ===========================================================================
def detect_data_region(file_path: str | Path, sheet_name: str, header_row: int) -> dict[str, Any]:
    """Load the sheet with pandas using the detected header row, report the
    resulting shape. Footer trimming happens separately in
    detect_footer_rows; this just establishes the raw data boundary."""
    df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row - 1)
    df = df.dropna(axis=1, how="all")
    return {
        "data_start_row": header_row + 1,
        "data_end_row": header_row + len(df),
        "row_count": len(df),
        "columns": [str(c) for c in df.columns],
    }


# ===========================================================================
# 6. detect_footer_rows
# ===========================================================================
_FOOTER_KEYWORD_PATTERN = re.compile(
    r"confidential|page\s*\d|report\b.*(v\d|version)|^total$|^grand total$", re.IGNORECASE
)


def detect_footer_rows(file_path: str | Path, sheet_name: str, header_row: int) -> dict[str, Any]:
    """Scan from the bottom of the sheet upward and classify trailing rows
    as footer if they are (a) fully blank, (b) sparsely populated with
    boilerplate keywords (page/confidential/report version), or (c) do not
    match the column-count profile of the real data rows directly above
    them. Every row removed is returned explicitly so nothing is silently
    dropped without being accounted for.

    read_only=True, and the whole trailing window is fetched in ONE
    iter_rows() call (not one call per row) -- on a 63k-row sheet, calling
    a per-row random-access helper 30+ times each re-scanning from the
    sheet start would dominate runtime."""
    wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    ws = wb[sheet_name]
    max_row, max_col = ws.max_row, ws.max_column

    window_start = max(header_row + 1, max_row - 30)
    rows_by_number: dict[int, list[Any]] = {}
    for r, row in enumerate(ws.iter_rows(min_row=window_start, max_row=max_row, values_only=True), start=window_start):
        rows_by_number[r] = list(row)
    wb.close()

    def row_values(r: int) -> list[Any]:
        return rows_by_number.get(r, [])

    # Establish the "normal data row" profile from a sample just above the
    # bottom (skipping the very last rows, which are the footer suspects).
    sample_rows = list(range(window_start, max_row - 2))
    sample_non_null_counts = [
        _row_stats(row_values(r))["non_null_count"] for r in sample_rows if r > header_row
    ]
    typical_non_null = (
        Counter(sample_non_null_counts).most_common(1)[0][0] if sample_non_null_counts else max_col
    )

    footer_rows: list[int] = []
    removed_row_samples: list[dict[str, Any]] = []
    r = max_row
    while r > header_row and r >= window_start:
        values = row_values(r)
        stats = _row_stats(values)
        text_blob = " ".join(str(v) for v in values if isinstance(v, str))
        is_blank = stats["non_null_count"] == 0
        is_boilerplate = bool(_FOOTER_KEYWORD_PATTERN.search(text_blob))
        is_sparse_vs_data = stats["non_null_count"] <= max(2, 0.25 * typical_non_null) and stats[
            "non_null_count"
        ] < typical_non_null
        if is_blank or is_boilerplate or is_sparse_vs_data:
            footer_rows.append(r)
            removed_row_samples.append({"row": r, "sample": text_blob[:120], "non_null_count": stats["non_null_count"]})
            r -= 1
            continue
        break
    return {
        "footer_rows": sorted(footer_rows),
        "typical_data_row_non_null_count": typical_non_null,
        "removed_row_evidence": removed_row_samples,
        "effective_last_data_row": r,
    }


# ===========================================================================
# 7. profile_columns
# ===========================================================================
def _detect_cell_type(series: pd.Series) -> str:
    non_null = series.dropna()
    if non_null.empty:
        return "empty"
    sample = non_null.head(200)
    if pd.api.types.is_bool_dtype(sample):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(sample):
        return "datetime"
    numeric_like = sample.apply(lambda v: isinstance(v, (int, float)) and not isinstance(v, bool))
    if numeric_like.mean() > 0.9:
        as_str = sample.astype(str)
        if as_str.str.match(r"^\d{8}(\.0)?$").mean() > 0.8:
            return "numeric_date"
        return "numeric"
    return "categorical_or_text"


def profile_columns(file_path: str | Path, sheet_name: str, header_row: int, data_end_row: int | None = None) -> list[dict[str, Any]]:
    """Profile every column: detected type, redacted sample values, unique
    categorical values (only for genuinely low-cardinality columns),
    missing/invalid counts, duplicate count, possible date format."""
    nrows = None
    if data_end_row is not None:
        nrows = data_end_row - header_row
    df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row - 1, nrows=nrows)
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]

    profiles = []
    n_rows = len(df)
    for col in df.columns:
        series = df[col]
        detected_type = _detect_cell_type(series)
        missing_count = int(series.isna().sum())
        non_null = series.dropna()

        sample_values = [str(v) for v in non_null.head(5).tolist()]
        unique_vals = None
        cardinality = non_null.nunique()
        if detected_type == "categorical_or_text" and 0 < cardinality <= 30:
            unique_vals = sorted(str(v) for v in non_null.unique().tolist())

        duplicate_count = None
        if cardinality > 0:
            duplicate_count = int(n_rows - missing_count - cardinality) if (n_rows - missing_count) >= cardinality else 0

        possible_date_format = None
        invalid_count = 0
        if detected_type == "numeric_date":
            as_str = non_null.astype("Int64").astype(str) if hasattr(non_null, "astype") else non_null.astype(str)
            possible_date_format = "YYYYMMDD"
            parsed = pd.to_datetime(as_str, format="%Y%m%d", errors="coerce")
            invalid_count = int(parsed.isna().sum())
        elif detected_type == "datetime":
            possible_date_format = "datetime64"

        profiles.append(
            {
                "column_name": str(col),
                "detected_type": detected_type,
                "sample_values": sample_values,
                "unique_categorical_values": unique_vals,
                "missing_count": missing_count,
                "invalid_count": invalid_count,
                "possible_date_format": possible_date_format,
                "duplicate_count": duplicate_count,
            }
        )
    return profiles


# ===========================================================================
# 8. detect_date_formats
# ===========================================================================
def detect_date_formats(sample_values: list[Any]) -> dict[str, Any]:
    """Given raw sample values from a candidate date column, determine the
    most likely format without assuming any single one."""
    non_null = [v for v in sample_values if v is not None and str(v).strip() != ""]
    if not non_null:
        return {"format": None, "confidence": 0.0}

    def looks_like_yyyymmdd_int(v: Any) -> bool:
        # Accepts raw ints/floats AND their stringified form -- callers
        # profiling a column (tools.excel_tools.profile_columns) always
        # stringify sample values before this function ever sees them
        # (ColumnProfile.sample_values is list[str]), so matching only
        # true Python int/float instances would never fire in practice.
        s = str(v)
        if s.endswith(".0"):
            s = s[:-2]
        return bool(re.match(r"^\d{8}$", s)) and 1900 <= int(s[:4]) <= 2100

    if all(looks_like_yyyymmdd_int(v) for v in non_null):
        return {"format": "YYYYMMDD_numeric", "confidence": 0.95}

    try:
        import datetime as _dt

        if all(isinstance(v, _dt.datetime) for v in non_null):
            return {"format": "datetime_object", "confidence": 0.95}
    except Exception:
        pass

    string_formats = {
        r"^\d{4}-\d{2}-\d{2}$": "YYYY-MM-DD",
        r"^\d{2}/\d{2}/\d{4}$": "DD/MM/YYYY_or_MM/DD/YYYY",
        r"^\d{2}-[A-Za-z]{3}-\d{4}$": "DD-Mon-YYYY",
    }
    for pattern, fmt in string_formats.items():
        if all(re.match(pattern, str(v)) for v in non_null):
            return {"format": fmt, "confidence": 0.85}

    return {"format": "unknown", "confidence": 0.1}


def normalize_date_value(value: Any, fmt_hint: str | None = None) -> str | None:
    """Normalize a single date cell to ISO 'YYYY-MM-DD'. Returns None if it
    cannot be validated as a real calendar date."""
    import datetime as _dt

    if value is None:
        return None
    try:
        if isinstance(value, _dt.datetime):
            return value.date().isoformat()
        if isinstance(value, _dt.date):
            return value.isoformat()
        s = str(value).strip()
        if s.endswith(".0"):
            s = s[:-2]
        if re.match(r"^\d{8}$", s):
            dt = _dt.datetime.strptime(s, "%Y%m%d")
            return dt.date().isoformat()
        for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y"):
            try:
                return _dt.datetime.strptime(s, pattern).date().isoformat()
            except ValueError:
                continue
    except (ValueError, TypeError):
        return None
    return None


# ===========================================================================
# 9. extract_cover_page_criteria
# ===========================================================================
#   Anchored (fullmatch), not substring search. A cover page's legend
# section explains these same abbreviations in prose ("HLT: High Level
# Term" -> "PPD: Preferred Product Description"), and a substring \bHLT\b
# search would wrongly match that legend-definition row as if it were the
# real HLT search-criterion row. Requiring the WHOLE label to be (close
# to) just the token itself excludes legend prose while still matching
# "PT", "PT Codes", "PT Decodes", "SMQ CMQ terms", etc.
_CRITERION_LABEL_MAP = [
    (re.compile(r"^PT(\s+(codes|decodes))?$", re.IGNORECASE), CriterionType.PT),
    (re.compile(r"^HLGT$", re.IGNORECASE), CriterionType.HLGT),
    (re.compile(r"^HLT$", re.IGNORECASE), CriterionType.HLT),
    (re.compile(r"^SOC$", re.IGNORECASE), CriterionType.SOC),
    (re.compile(r"^SMQ(\s+CMQ\s+terms)?$", re.IGNORECASE), CriterionType.SMQ),
    (re.compile(r"^CMQ$", re.IGNORECASE), CriterionType.CMQ),
]


def extract_cover_page_criteria(file_path: str | Path, sheet_name: str) -> dict[str, Any]:
    """Generic key/value scan of a 'cover page'-style sheet. A label does
    NOT have to end in ':' -- some rows are "Label: value" in one cell
    pair, others are a bare label cell ("HLT") followed by a bare value
    cell ("-" or the real term), with no colon at all. So: for every row,
    take the first non-null cell as the label (if it's a string) and the
    NEXT non-null cell on that row as its value. Rows with more than 2
    non-null string cells (e.g. the legend row) still get captured this
    way but simply won't match any known criterion-type label below."""
    wb = openpyxl.load_workbook(file_path, data_only=True, read_only=False)
    ws = wb[sheet_name]
    raw_fields: dict[str, str] = {}
    for row in ws.iter_rows():
        non_null = [c for c in row if c.value is not None]
        if len(non_null) < 2:
            continue
        label_cell, value_cell = non_null[0], non_null[1]
        if not isinstance(label_cell.value, str):
            continue
        label = label_cell.value.strip().rstrip(":").strip()
        if label:
            raw_fields[label] = str(value_cell.value)
    wb.close()

    criterion_type = CriterionType.UNKNOWN
    criterion_value = None
    for label, value in raw_fields.items():
        if value is None or str(value).strip() in ("-", ""):
            continue
        for pattern, ctype in _CRITERION_LABEL_MAP:
            if pattern.search(label):
                criterion_type = ctype
                criterion_value = value
                break
        if criterion_value:
            break

    return {"raw_fields": raw_fields, "criterion_type": criterion_type.value, "criterion_value": criterion_value}


# ===========================================================================
# 10. classify_workbook
# ===========================================================================
_CASE_ONLY_HINTS = {"patient race", "patient gender", "weight", "pregnant"}
_EVENT_ONLY_HINTS = {"event seriousness", "event outcome", "reporter causality", "dechallenge"}


def classify_workbook(columns: list[str], cover_page_criterion_value: str | None) -> dict[str, Any]:
    """Classify a workbook using column-content evidence (case-grain vs
    event-grain columns) plus whether the cover page carries a real
    (non-blank) search criterion. Filename is NOT used here -- it is only
    ever a weak supporting signal applied by the agent on top of this."""
    cols_lower = {c.lower().strip() for c in columns}
    is_event_grain = bool(cols_lower & _EVENT_ONLY_HINTS) or any("event pt" in c for c in cols_lower)
    is_case_grain = bool(cols_lower & _CASE_ONLY_HINTS) and not is_event_grain

    has_topic_criterion = bool(cover_page_criterion_value) and str(cover_page_criterion_value).strip() not in ("-", "")

    if is_event_grain:
        wtype = WorkbookType.TOPIC_DRUG_EVENT if has_topic_criterion else WorkbookType.ALL_DRUG_EVENT
    elif is_case_grain:
        wtype = WorkbookType.TOPIC_CASE if has_topic_criterion else WorkbookType.ALL_CASE
    else:
        wtype = WorkbookType.UNCLASSIFIED

    confidence = 0.85 if (is_event_grain or is_case_grain) else 0.2
    evidence = [
        f"event_grain_columns_present={is_event_grain}",
        f"case_grain_columns_present={is_case_grain}",
        f"has_topic_criterion={has_topic_criterion}",
    ]
    return {"workbook_type": wtype.value, "confidence": confidence, "evidence": evidence,
            "data_grain": (DataGrain.ONE_ROW_PER_CASE_EVENT if is_event_grain else
                            DataGrain.ONE_ROW_PER_CASE if is_case_grain else DataGrain.UNKNOWN).value}


# ===========================================================================
# 11. map_columns_to_schema
# ===========================================================================
def _normalize_header(name: str) -> str:
    """Normalize a raw header for synonym matching. Parenthetical content
    is KEPT (as plain words, punctuation stripped) rather than discarded --
    qualifiers like "(Event)" vs "(Case)" or "(Primary Path)" are often the
    ONLY thing that disambiguates two otherwise-identical labels (e.g.
    "Death (Case)" vs "Death (Event)"), so dropping them would silently
    collapse two distinct canonical fields into one."""
    name = unicodedata.normalize("NFKD", str(name))
    name = re.sub(r"[()]", " ", name)
    name = re.sub(r"[^a-z0-9]+", " ", name.lower())
    return name.strip()


_CANONICAL_SYNONYMS: dict[CanonicalField, list[str]] = {
    CanonicalField.CASE_ID: ["case number", "case id", "caseid"],
    CanonicalField.INITIAL_APPROVAL_DATE: ["derived initial approval date", "initial approval date"],
    CanonicalField.PRIMARY_SOURCE: ["derived primary source", "primary source"],
    CanonicalField.CASE_SERIOUSNESS: ["seriousness"],
    CanonicalField.CASE_DEATH: ["death case", "death"],
    CanonicalField.CASE_TYPE: ["derived case type", "case type"],
    CanonicalField.EVENT_PT: ["event pt", "event pt primary path"],
    CanonicalField.EVENT_HLT: ["event hlt", "event hlt primary path"],
    CanonicalField.EVENT_HLGT: ["event hlgt", "event hlgt primary path"],
    CanonicalField.EVENT_SOC: ["event soc", "event soc primary path"],
    CanonicalField.EVENT_SERIOUSNESS: ["event seriousness"],
    CanonicalField.EVENT_DEATH: ["death event"],
    CanonicalField.EVENT_RELATEDNESS: ["derived overall event relatedness", "overall event relatedness"],
}


_MIN_MAPPING_SCORE = 0.6


def _score_against_synonym(norm: str, syn: str) -> float:
    if norm == syn:
        return 1.0
    if norm.startswith(syn + " ") or norm.endswith(" " + syn) or norm.startswith(syn) or norm.endswith(syn):
        return 0.9
    if syn in norm or norm in syn:
        return 0.7
    return 0.0


def map_columns_to_schema(columns: list[str], column_profiles: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Map raw (unknown, possibly differently-worded) column headers onto
    the canonical schema using normalized name similarity, then validate
    against the column's profiled values/type where available, then
    resolve conflicts so each canonical field is claimed by at most ONE raw
    column (the highest-confidence candidate) -- a weak secondary match
    (e.g. "Primary Source Country Abbr" loosely matching "primary_source")
    must not sit alongside the real match and get used downstream."""
    profile_by_col = {p["column_name"]: p for p in (column_profiles or [])}

    candidates: dict[str, list[dict[str, Any]]] = {}  # raw_col -> list of (field, score, evidence)
    for raw_col in columns:
        norm = _normalize_header(raw_col)
        scored = []
        for field_enum, synonyms in _CANONICAL_SYNONYMS.items():
            best_syn_score = max((_score_against_synonym(norm, syn) for syn in synonyms), default=0.0)
            if best_syn_score > 0:
                scored.append((field_enum, best_syn_score))
        scored.sort(key=lambda t: t[1], reverse=True)
        candidates[raw_col] = scored

    # Pass 1: tentative best field per raw column (value-validated).
    tentative: dict[str, dict[str, Any]] = {}
    for raw_col in columns:
        scored = candidates[raw_col]
        if not scored:
            tentative[raw_col] = {"field": None, "score": 0.0, "evidence": "no synonym match"}
            continue
        best_field, best_score = scored[0]
        evidence = f"normalized '{_normalize_header(raw_col)}' matched '{best_field.value}', score={best_score}"

        profile = profile_by_col.get(raw_col)
        value_check_failed = False
        if profile:
            if best_field == CanonicalField.INITIAL_APPROVAL_DATE and profile["detected_type"] not in (
                "numeric_date", "datetime",
            ):
                value_check_failed = True
                evidence += "; value-check FAILED: column is not a date type"
            if best_field in (CanonicalField.CASE_SERIOUSNESS, CanonicalField.CASE_DEATH,
                               CanonicalField.EVENT_SERIOUSNESS, CanonicalField.EVENT_DEATH):
                vals = {v.strip().lower() for v in (profile.get("unique_categorical_values") or [])}
                if vals and not vals.issubset({"yes", "no", "no information", "not asked", "unknown", "masked", ""}):
                    value_check_failed = True
                    evidence += f"; value-check FAILED: unexpected categories {vals}"

        effective_score = best_score * 0.5 if value_check_failed else best_score
        tentative[raw_col] = {"field": best_field, "score": effective_score, "evidence": evidence,
                               "value_check_failed": value_check_failed}

    # Pass 2: resolve conflicts -- one raw column per canonical field, the
    # highest-scoring candidate wins; losers are demoted (kept visible for
    # audit, but not treated as the mapping) and flagged for review.
    winner_by_field: dict[CanonicalField, str] = {}
    for raw_col, info in tentative.items():
        field = info["field"]
        if field is None:
            continue
        current_winner = winner_by_field.get(field)
        if current_winner is None or info["score"] > tentative[current_winner]["score"]:
            winner_by_field[field] = raw_col

    mappings = []
    for raw_col in columns:
        info = tentative[raw_col]
        field, score, evidence = info["field"], info["score"], info["evidence"]
        is_winner = field is not None and winner_by_field.get(field) == raw_col
        meets_threshold = score >= _MIN_MAPPING_SCORE

        if field is not None and not is_winner:
            evidence += f"; demoted: '{winner_by_field[field]}' is the stronger match for {field.value}"

        final_field = field if (is_winner and meets_threshold) else None
        needs_review = (field is not None) and (not is_winner or not meets_threshold or info.get("value_check_failed"))

        mappings.append(
            {
                "raw_column": raw_col,
                "canonical_field": final_field.value if final_field else None,
                "confidence": round(score, 2),
                "evidence": evidence,
                "needs_review": needs_review,
            }
        )
    return mappings


# ===========================================================================
# 12. match_workbooks
# ===========================================================================
def match_workbooks(case_entries: list[dict[str, Any]], event_entries: list[dict[str, Any]],
                     case_number_overlap_fn=None) -> list[dict[str, Any]]:
    """Pair case workbooks with drug-event workbooks belonging to the same
    topic. Primary evidence: matching (non-blank) cover-page criterion
    type+value. Filename similarity is only a tiebreak hint. If
    case_number_overlap_fn(case_entry, event_entry) -> float is supplied,
    it's used as the authoritative cross-check (fraction of case numbers
    shared between the two files) and can override a criterion-only match."""
    pairs = []
    used_events = set()
    for case in case_entries:
        c_crit = (case.get("cover_page_criteria") or {}).get("criterion_value")
        best_event, best_score = None, 0.0
        for event in event_entries:
            if event["file_name"] in used_events:
                continue
            e_crit = (event.get("cover_page_criteria") or {}).get("criterion_value")
            score = 0.0
            if c_crit and e_crit and str(c_crit).strip() == str(e_crit).strip():
                score = 0.9
            elif not c_crit and not e_crit:
                score = 0.5  # both "all" workbooks, weak default match
            if case_number_overlap_fn:
                overlap = case_number_overlap_fn(case, event)
                score = max(score, overlap) if overlap and overlap > 0.5 else score
            if score > best_score:
                best_event, best_score = event, score
        if best_event and best_score >= 0.5:
            used_events.add(best_event["file_name"])
            pairs.append(
                {
                    "case_workbook": case["file_name"],
                    "drug_event_workbook": best_event["file_name"],
                    "confidence": round(best_score, 2),
                }
            )
        else:
            pairs.append({"case_workbook": case["file_name"], "drug_event_workbook": None, "confidence": 0.0})
    return pairs
