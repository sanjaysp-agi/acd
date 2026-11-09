"""
Predefined, typed Python tools for autonomous Word-document investigation
(the previous/approved PBRER). No tool here assumes a specific heading
style name, that section numbers are literal text, or that "16.3" is the
right prefix for this tenant's document -- a different tenant's PBRER
could use real Word "Heading 1/2/3" styles, a different custom style
family, or no reliable style at all. Everything is discovered from the
document's own content and formatting at call time.

Library: python-docx throughout (PyMuPDF only if/when PDF support is
needed -- not required for the current .docx input).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import docx
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph


# ===========================================================================
# Shared: true document-order iteration (paragraphs AND tables interleaved)
# ===========================================================================
def _iter_block_items(document) -> list[tuple[str, Any]]:
    """Yield (kind, object) for every paragraph/table in true document
    order. python-docx's own `document.paragraphs` / `document.tables`
    lose interleaving order, which matters here because a topic's data
    table sits physically between two headings and extract_tables_near_heading
    needs to know that."""
    body = document.element.body
    items = []
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            items.append(("paragraph", Paragraph(child, document)))
        elif child.tag == qn("w:tbl"):
            items.append(("table", Table(child, document)))
    return items


def _get_outline_level(paragraph: Paragraph) -> int | None:
    pPr = paragraph._p.find(qn("w:pPr"))
    if pPr is None:
        return None
    lvl = pPr.find(qn("w:outlineLvl"))
    if lvl is None:
        return None
    val = lvl.get(qn("w:val"))
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _is_bold_paragraph(paragraph: Paragraph) -> bool:
    runs = [r for r in paragraph.runs if r.text.strip()]
    if not runs:
        return False
    return all(r.bold for r in runs)


# ===========================================================================
# 1. inspect_document_metadata
# ===========================================================================
def inspect_document_metadata(file_path: str | Path) -> dict[str, Any]:
    document = docx.Document(str(file_path))
    blocks = _iter_block_items(document)
    paragraphs = [b for k, b in blocks if k == "paragraph"]
    tables = [b for k, b in blocks if k == "table"]
    style_usage: dict[str, int] = {}
    total_words = 0
    for p in paragraphs:
        style_usage[p.style.name] = style_usage.get(p.style.name, 0) + 1
        total_words += len(p.text.split())
    return {
        "file_path": str(file_path),
        "block_count": len(blocks),
        "paragraph_count": len(paragraphs),
        "table_count": len(tables),
        "style_usage": style_usage,
        "total_word_count_estimate": total_words,
    }


# ===========================================================================
# 2. sample_paragraph_styles
# ===========================================================================
def sample_paragraph_styles(file_path: str | Path, max_samples: int = 3) -> list[dict[str, Any]]:
    document = docx.Document(str(file_path))
    blocks = _iter_block_items(document)
    by_style: dict[str, list[str]] = {}
    for kind, b in blocks:
        if kind != "paragraph":
            continue
        text = b.text.strip()
        if not text:
            continue
        by_style.setdefault(b.style.name, []).append(text)

    out = []
    for style_name, texts in by_style.items():
        out.append(
            {
                "style_name": style_name,
                "count": len(texts),
                "avg_text_length": round(sum(len(t) for t in texts) / len(texts), 1),
                "sample_texts": texts[:max_samples],
            }
        )
    out.sort(key=lambda d: -d["count"])
    return out


# ===========================================================================
# 3. detect_headings
# ===========================================================================
_HEADING_STYLE_NAME_PATTERN = re.compile(r"heading|title|level|outline", re.IGNORECASE)
_ORDINAL_TOKEN_PATTERN = re.compile(
    r"\b(\d+)(?:st|nd|rd|th)?\b|\b(first|second|third|fourth|fifth|sixth|seventh)\b", re.IGNORECASE
)
_ORDINAL_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7}


def _extract_level_from_style_name(style_name: str) -> int | None:
    m = _ORDINAL_TOKEN_PATTERN.search(style_name)
    if not m:
        return None
    if m.group(1):
        return int(m.group(1))
    return _ORDINAL_WORDS.get(m.group(2).lower())


def detect_headings(file_path: str | Path) -> dict[str, Any]:
    """Three strategies, tried in order of reliability:
      1. style_name: a cluster of distinct, moderately-frequent styles
         whose names look heading-like (contain "heading"/"level"/"title"/
         "outline"), with a level number recovered from each style name.
      2. outline_level: Word's own w:outlineLvl paragraph property, when
         present, independent of style naming.
      3. bold_heuristic: short, fully-bold paragraphs with no run style
         evidence at all -- last resort, lower confidence.
    Returns every heading found, in document order, each tagged with the
    strategy that identified it."""
    document = docx.Document(str(file_path))
    blocks = _iter_block_items(document)
    paragraphs = [(i, b) for i, (kind, b) in enumerate(blocks) if kind == "paragraph"]

    style_counts: dict[str, int] = {}
    for _, p in paragraphs:
        if p.text.strip():
            style_counts[p.style.name] = style_counts.get(p.style.name, 0) + 1

    heading_like_styles = {
        name: count for name, count in style_counts.items()
        if _HEADING_STYLE_NAME_PATTERN.search(name) and 0 < count <= max(500, len(paragraphs) * 0.3)
    }

    headings = []
    strategy = None

    if len(heading_like_styles) >= 2:
        strategy = "style_name"
        level_by_style: dict[str, int] = {}
        next_fallback_level = 1
        seen_order: list[str] = []
        for block_idx, p in paragraphs:
            if p.style.name not in heading_like_styles or not p.text.strip():
                continue
            style_name = p.style.name
            if style_name not in level_by_style:
                extracted = _extract_level_from_style_name(style_name)
                if extracted is not None:
                    level_by_style[style_name] = extracted
                else:
                    if style_name not in seen_order:
                        seen_order.append(style_name)
                    level_by_style[style_name] = next_fallback_level + seen_order.index(style_name)
            headings.append(
                {
                    "block_index": block_idx,
                    "text": p.text.strip(),
                    "style_name": style_name,
                    "level": level_by_style[style_name],
                    "strategy": "style_name",
                }
            )
    else:
        outline_hits = [(i, p, _get_outline_level(p)) for i, p in paragraphs]
        outline_hits = [(i, p, lvl) for i, p, lvl in outline_hits if lvl is not None and p.text.strip()]
        if outline_hits:
            strategy = "outline_level"
            for block_idx, p, lvl in outline_hits:
                headings.append(
                    {
                        "block_index": block_idx,
                        "text": p.text.strip(),
                        "style_name": p.style.name,
                        "level": lvl + 1,  # outlineLvl is 0-based
                        "strategy": "outline_level",
                    }
                )
        else:
            strategy = "bold_heuristic"
            for block_idx, p in paragraphs:
                text = p.text.strip()
                if not text or len(text) > 120 or text.endswith((".", ",", ";")):
                    continue
                if _is_bold_paragraph(p):
                    headings.append(
                        {
                            "block_index": block_idx,
                            "text": text,
                            "style_name": p.style.name,
                            "level": 1,  # cannot distinguish depth reliably from bold alone
                            "strategy": "bold_heuristic",
                        }
                    )

    return {"strategy": strategy, "headings": headings, "total_blocks": len(blocks)}


# ===========================================================================
# 3b. exclude_front_matter_headings
# ===========================================================================
# Regulatory documents built on the ICH/CTD template family (PBRER, PSUR,
# clinical study reports, ...) conventionally have unnumbered front matter
# -- Abbreviations, Table of Contents, List of Tables/Figures, Glossary --
# that often shares the SAME heading style as the real numbered body
# sections. If left in, sibling-counting silently shifts every section
# number by however many front-matter headings precede the real Section 1
# (observed here: "ABBREVIATIONS" before "INTRODUCTION" shifted every
# number by +1, turning "16.3" into "17.3"). This is a structural/template
# convention, not a fact about THIS tenant's wording -- it is not an
# assumption about what a specific section is called.
_FRONT_MATTER_TITLE_PATTERN = re.compile(
    r"^(abbreviations|table of contents|list of tables|list of figures|glossary|"
    r"title page|signature page|copyright)\s*$",
    re.IGNORECASE,
)


def exclude_front_matter_headings(headings: list[dict[str, Any]]) -> dict[str, Any]:
    """Drop leading top-level headings that match known unnumbered
    front-matter titles, so numbering starts at the real Section 1. Only
    strips from the START of the list (a front-matter-looking title deep
    in the body, e.g. an appendix called "Glossary", is left alone)."""
    excluded = []
    kept = list(headings)
    min_level = min((h["level"] for h in headings), default=1)
    while kept and kept[0]["level"] == min_level and _FRONT_MATTER_TITLE_PATTERN.match(kept[0]["text"].strip()):
        excluded.append(kept.pop(0))
    return {"headings": kept, "excluded_front_matter": excluded}


# ===========================================================================
# 4. reconstruct_section_numbers
# ===========================================================================
def reconstruct_section_numbers(headings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assign RELATIVE dotted numbers by counting siblings per level in
    document order (Word auto-numbers headings; the number is not literal
    text in most templates, so it must be computed). These numbers are
    relative to wherever this heading set starts -- e.g. the first
    top-level heading becomes "1", not necessarily "16". Absolute
    calibration (recovering the real "16.3" prefix) happens separately in
    calibrate_section_numbers, using citations found in the document's own
    prose, and is NOT guaranteed to succeed."""
    counters: dict[int, int] = {}
    out = []
    for h in headings:
        level = h["level"]
        for deeper in list(counters.keys()):
            if deeper > level:
                del counters[deeper]
        counters[level] = counters.get(level, 0) + 1
        relative_number = ".".join(str(counters[lv]) for lv in sorted(counters) if lv <= level)
        out.append({**h, "relative_number": relative_number})
    return out


# ===========================================================================
# 5. calibrate_section_numbers (best-effort absolute numbering)
# ===========================================================================
_SECTION_CITATION_PATTERN = re.compile(r"Section\s+(\d{1,2}(?:\.\d{1,2}){0,4})", re.IGNORECASE)


def calibrate_section_numbers(file_path: str | Path, target_heading_text: str,
                               target_relative_number: str) -> dict[str, Any]:
    """Scan the document's own prose for manually-typed cross-reference
    citations like "see Section 16.3.1.4" and check whether any citation's
    TRAILING segments -- ALL of them, not just the last one -- match this
    heading's full relative sibling chain (e.g. relative_number "2.3" only
    counts as a match against a citation ending "...16.2.3", not just
    "...16.9.3"). A single-segment match is far too easy to hit by
    coincidence (observed in testing: it confidently proposed the wrong
    absolute number). Requiring the whole relative chain to match as a
    trailing subsequence is real, falsifiable evidence; if it still can't
    be confirmed, say so rather than guessing -- an uncalibrated number is
    a review flag, not a reported fact."""
    document = docx.Document(str(file_path))
    full_text = "\n".join(p.text for p in document.paragraphs)
    citations = _SECTION_CITATION_PATTERN.findall(full_text)
    if not citations:
        return {"absolute_number": None, "confidence": 0.0, "evidence": "no 'Section x.y.z' citations found in document text"}

    target_segments = target_relative_number.split(".")
    n = len(target_segments)
    matches = [c for c in citations if c.split(".")[-n:] == target_segments]
    if not matches:
        return {"absolute_number": None, "confidence": 0.0,
                "evidence": f"no citation's trailing {n} segment(s) match relative chain '{target_relative_number}'"}

    from collections import Counter

    best, count = Counter(matches).most_common(1)[0]
    # Multi-segment agreement is much stronger evidence than a single
    # trailing digit; scale confidence with both match count and chain
    # length, but never claim certainty -- this is still inference from
    # manually-typed prose, not a parsed numbering definition.
    confidence = min(0.85, 0.25 + 0.15 * count + 0.1 * (n - 1))
    return {
        "absolute_number": best,
        "confidence": round(confidence, 2),
        "evidence": f"citation '{best}' found {count}x with trailing {n} segment(s) matching '{target_relative_number}'",
    }


# ===========================================================================
# 6. locate_target_section
# ===========================================================================
def locate_target_section(headings_with_numbers: list[dict[str, Any]],
                            candidate_title_patterns: list[str]) -> dict[str, Any]:
    """Find the heading whose TEXT matches one of the candidate title
    patterns (e.g. "Evaluation of Risks and New Information"), rather than
    assuming its number is "16.3". Patterns are matched case-insensitively
    as substrings; the first match in document order wins."""
    for pattern in candidate_title_patterns:
        pat = re.compile(re.escape(pattern), re.IGNORECASE)
        for h in headings_with_numbers:
            if pat.search(h["text"]):
                return {"found": True, "heading": h, "matched_pattern": pattern}
    return {"found": False, "heading": None, "matched_pattern": None}


# ===========================================================================
# 7. extract_topic_subtree
# ===========================================================================
def extract_topic_subtree(headings_with_numbers: list[dict[str, Any]], target_block_index: int) -> list[dict[str, Any]]:
    """Return every heading that is a descendant of the target heading:
    all headings after it in document order, up until (not including) the
    next heading at the SAME OR SHALLOWER level."""
    target = next((h for h in headings_with_numbers if h["block_index"] == target_block_index), None)
    if target is None:
        return []
    target_level = target["level"]
    subtree = []
    started = False
    for h in headings_with_numbers:
        if h["block_index"] == target_block_index:
            started = True
            continue
        if not started:
            continue
        if h["level"] <= target_level:
            break
        subtree.append(h)
    return subtree


# ===========================================================================
# 8. extract_tables_near_heading
# ===========================================================================
def extract_tables_near_heading(file_path: str | Path, heading_block_index: int,
                                 next_heading_block_index: int | None) -> dict[str, Any]:
    """Collect every table AND every non-empty paragraph physically
    located between this heading and the next one (or end of document),
    using true document order. Word PBRER tables used for topic data are
    typically simple 2-column label/value tables -- parsed generically as
    a list of {label, value} rows, not assuming a fixed row count.

    Vertically-merged cells are a real hazard here: python-docx's
    `row.cells` re-exposes a merged cell's content for EVERY row it spans
    (same underlying <w:tc> element, read multiple times), so a naive
    per-row join double-counts merged content into unrelated label rows
    (observed on the Impulse Control Disorders table: "Spontaneous" and
    "Report from other studies" ended up concatenated). Fixed by comparing
    each cell to the one directly above it in the same column by identity
    (`is`, not text equality) -- a repeat means "this is a merge
    continuation of the row above", not new content for the current row."""
    document = docx.Document(str(file_path))
    blocks = _iter_block_items(document)

    end = next_heading_block_index if next_heading_block_index is not None else len(blocks)
    tables_out = []
    paragraphs_out = []
    for idx, (kind, b) in enumerate(blocks):
        if idx <= heading_block_index or idx >= end:
            continue
        if kind == "table":
            rows = []
            prev_cells = None
            for row in b.rows:
                cells = row.cells
                is_continuation = [
                    prev_cells is not None and i < len(prev_cells) and cell._tc is prev_cells[i]._tc
                    for i, cell in enumerate(cells)
                ]
                texts = [c.text.strip() for c in cells]
                if len(cells) >= 2:
                    label = texts[0] if not is_continuation[0] else ""
                    value_parts = [texts[i] for i in range(1, len(cells)) if not is_continuation[i] and texts[i]]
                    if label or value_parts:
                        rows.append({"label": label, "value": " | ".join(value_parts)})
                elif cells and not is_continuation[0]:
                    rows.append({"label": texts[0], "value": ""})
                prev_cells = cells
            tables_out.append({"block_index": idx, "rows": rows})
        elif kind == "paragraph" and b.text.strip():
            paragraphs_out.append({"block_index": idx, "text": b.text.strip()})

    return {"tables": tables_out, "paragraphs": paragraphs_out}


# ===========================================================================
# 9. parse_topic_historical_metrics
# ===========================================================================
# These regexes target the PBRER/ICH E2C(R2) table convention itself (row
# labels like "Spontaneous:", "Report from other studies:", an
# "Evaluation:" sentence stating "N (X.X%) ... serious, M (Y.Y%) fatal") --
# that is the template's own natural-language structure, not a guess about
# this specific tenant's wording. A different PBRER built on the same
# template should phrase these the same way; if it doesn't, the affected
# figure simply comes back None and must be flagged, never guessed.
_TOPIC_TOTAL_PATTERN = re.compile(r"(\d[\d,]*)\s*/\s*(\d[\d,]*)")
_COUNT_IN_VALUE_PATTERN = re.compile(r"(\d[\d,]*)")
_BARE_CASES_PATTERN = re.compile(r"^\s*(\d[\d,]*)\s*cases?\s*$", re.IGNORECASE)
_SERIOUS_PATTERN = re.compile(r"(\d[\d,]*)\s*\(([\d.]+)\s*%\)[^.]*?serious", re.IGNORECASE)
_FATAL_PATTERN = re.compile(r"(\d[\d,]*)\s*\(([\d.]+)\s*%\)[^.]*?fatal", re.IGNORECASE)
_NONE_FATAL_PATTERN = re.compile(r"\bnone\s+(?:were\s+)?fatal\b|\bno\s+fatal\s+cases\b", re.IGNORECASE)


def _to_number(s: str) -> float | int | None:
    if s is None:
        return None
    s = s.replace(",", "")
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return None


def parse_topic_historical_metrics(table_rows: list[dict[str, str]], paragraphs: list[dict[str, str]]) -> dict[str, Any]:
    """Extract structured historical figures from a topic's raw table rows
    (+ nearby paragraph text, in case the Evaluation sentence spilled into
    a following paragraph). Every field is independently optional -- a
    missing field is reported as None, never fabricated."""
    metrics: dict[str, Any] = {
        "topic_count": None, "total_count": None, "spontaneous_count": None,
        "other_studies_count": None, "serious_count": None, "serious_pct": None,
        "fatal_count": None, "fatal_pct": None, "search_criteria_text": None,
        "raw_evaluation_text": None,
    }
    full_text_blob = " ".join(r.get("value", "") for r in table_rows) + " " + " ".join(p.get("text", "") for p in paragraphs)

    # Spontaneous/Other-studies counts: NOT extracted by label-matching a
    # specific row, because Word tables in this template sometimes merge
    # the Spontaneous/Other-studies/Evaluation rows' VALUE cells into one
    # (observed on the ICD table) -- python-docx then reports the
    # "Spontaneous" row's own value as containing ALL of that merged
    # content, with "Report from other studies" left as an empty-value
    # row. Label-matching breaks in that case. Instead: scan every row's
    # value, split on its own internal newlines (a merged cell's multiple
    # stacked lines, or a clean table's single line -- same handling
    # either way), and collect every line that is JUST "<number> cases"
    # with nothing else on it, in document order. Per the ICH/PBRER
    # template, the Spontaneous count always appears before the
    # Report-from-other-studies count, so position 0/1 in that ordered
    # list map onto them reliably in both table-authoring variants.
    bare_case_counts: list[int | float | None] = []
    for row in table_rows:
        for line in row.get("value", "").split("\n"):
            m = _BARE_CASES_PATTERN.match(line.strip())
            if m:
                bare_case_counts.append(_to_number(m.group(1)))
    if len(bare_case_counts) >= 1:
        metrics["spontaneous_count"] = bare_case_counts[0]
    if len(bare_case_counts) >= 2:
        metrics["other_studies_count"] = bare_case_counts[1]

    for row in table_rows:
        label = row.get("label", "").lower()
        value = row.get("value", "")
        if "post-marketing" in label or "number of initial cases" in label:
            m = _TOPIC_TOTAL_PATTERN.search(value)
            if m:
                metrics["topic_count"] = _to_number(m.group(1))
                metrics["total_count"] = _to_number(m.group(2))
        elif "search criteria" in label:
            metrics["search_criteria_text"] = value
        elif label.strip().rstrip(":") == "evaluation":
            metrics["raw_evaluation_text"] = value

    serious_m = _SERIOUS_PATTERN.search(full_text_blob)
    if serious_m:
        metrics["serious_count"] = _to_number(serious_m.group(1))
        metrics["serious_pct"] = _to_number(serious_m.group(2))

    # Check the explicit "none fatal" / "no fatal cases" phrase FIRST and
    # treat it as authoritative. The numeric fatal pattern below is a lazy
    # "<number> (<pct>%) ... fatal" search with no sentence-boundary
    # anchor other than a period; on text like "18 (40.9%) of the cases
    # were serious, none fatal." (no period before "fatal") it would
    # otherwise re-capture the SERIOUS clause's own number as if it were
    # the fatal count -- which is exactly what happened on DAWS before
    # this check was reordered (serious=18 got reported as fatal=18 too).
    if _NONE_FATAL_PATTERN.search(full_text_blob):
        metrics["fatal_count"] = 0
        metrics["fatal_pct"] = 0.0
    else:
        fatal_m = _FATAL_PATTERN.search(full_text_blob)
        if fatal_m:
            metrics["fatal_count"] = _to_number(fatal_m.group(1))
            metrics["fatal_pct"] = _to_number(fatal_m.group(2))

    return metrics
