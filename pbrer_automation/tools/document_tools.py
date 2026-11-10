"""
Predefined, typed Python tools for autonomous document investigation
(the previous/approved PBRER). No tool here assumes a specific heading
style name, that section numbers are literal text, or that "16.3" is the
right prefix for this tenant's document -- a different tenant's PBRER
could use real Word "Heading 1/2/3" styles, a different custom style
family, numbered section headings typed directly into the prose, or no
reliable style at all. Everything is discovered from the document's own
content and formatting at call time.

Input formats: .docx, .pdf, and .txt. Every public function accepts any
of the three and dispatches internally on the file extension. To keep
that dispatch in exactly one place, every function works off a private
intermediate representation (IR) built by `_load_blocks`: a flat, ordered
list of block dicts, each either
  {"kind": "paragraph", "text": str, "style_name": str | None,
   "outline_level": int | None, "is_bold": bool}
or
  {"kind": "table", "rows": [[cell_text, ...], ...]}
in true document order (paragraphs and tables interleaved the way they
physically occur). A block's position in this list is its `block_index`,
and that index space is the same one every other tool call uses for the
same file -- it is what makes `extract_tables_near_heading`,
`extract_topic_subtree`, and `calibrate_section_numbers`'s caller context
all agree on "where" a heading or table sits.

Libraries: python-docx for .docx, pdfplumber for .pdf, the standard
library for .txt.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

import docx
import pdfplumber
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph


# ===========================================================================
# Shared IR: _load_blocks and its per-format loaders
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


def _resolve_docx_table_rows(table: Table) -> list[list[str]]:
    """Resolve a python-docx table into a plain 2D grid of cell text,
    handling vertically-merged cells before anything downstream ever sees
    them. python-docx's `row.cells` re-exposes a merged cell's content for
    EVERY row it spans (same underlying <w:tc> element, read multiple
    times), so a naive per-row join double-counts merged content into
    unrelated rows (observed on the Impulse Control Disorders table:
    "Spontaneous" and "Report from other studies" ended up concatenated).
    Fixed by comparing each cell to the one directly above it in the same
    column by identity (`is`, not text equality) -- a repeat means "this
    is a merge continuation of the row above", represented here as an
    empty string so every later consumer of the IR can treat a docx grid
    exactly like a pdf/txt grid with no further merge-awareness needed."""
    rows: list[list[str]] = []
    prev_cells = None
    for row in table.rows:
        cells = row.cells
        texts = []
        for i, cell in enumerate(cells):
            is_continuation = prev_cells is not None and i < len(prev_cells) and cell._tc is prev_cells[i]._tc
            texts.append("" if is_continuation else cell.text.strip())
        rows.append(texts)
        prev_cells = cells
    return rows


def _load_docx_blocks(file_path: str | Path) -> list[dict[str, Any]]:
    document = docx.Document(str(file_path))
    blocks: list[dict[str, Any]] = []
    for kind, obj in _iter_block_items(document):
        if kind == "paragraph":
            blocks.append({
                "kind": "paragraph",
                "text": obj.text,
                "style_name": obj.style.name,
                "outline_level": _get_outline_level(obj),
                "is_bold": _is_bold_paragraph(obj),
            })
        else:
            blocks.append({"kind": "table", "rows": _resolve_docx_table_rows(obj)})
    return blocks


_BOLD_FONT_HINT_PATTERN = re.compile(r"bold|black|heavy", re.IGNORECASE)
_LINE_Y_TOLERANCE = 3.0


def _word_in_bbox(word: dict[str, Any], bbox: tuple[float, float, float, float]) -> bool:
    """True if a word's center falls inside a table's bounding box. Needed
    because pdfplumber's `extract_words` returns every word on the page,
    including the ones sitting inside table cells -- without this filter
    a table's own text would be double-counted as ordinary paragraph lines
    AND as table rows."""
    x0, top, x1, bottom = bbox
    center_x = (word["x0"] + word["x1"]) / 2
    center_y = (word["top"] + word["bottom"]) / 2
    return x0 <= center_x <= x1 and top <= center_y <= bottom


def _group_words_into_lines(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Reconstruct reading-order text lines from pdfplumber's flat word
    list by clustering words whose vertical position agrees within a
    small tolerance, then ordering each line's words left-to-right and
    the lines themselves top-to-bottom."""
    lines: list[list[dict[str, Any]]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        for line in lines:
            if abs(line[0]["top"] - word["top"]) <= _LINE_Y_TOLERANCE:
                line.append(word)
                break
        else:
            lines.append([word])
    for line in lines:
        line.sort(key=lambda w: w["x0"])
    lines.sort(key=lambda line: line[0]["top"])
    return lines


def _line_is_bold(words: list[dict[str, Any]]) -> bool:
    bold_count = sum(1 for w in words if _BOLD_FONT_HINT_PATTERN.search(w.get("fontname") or ""))
    return bold_count * 2 >= len(words)


def _line_font_size(words: list[dict[str, Any]]) -> float | None:
    sizes = [round(w["size"], 1) for w in words if w.get("size") is not None]
    if not sizes:
        return None
    return Counter(sizes).most_common(1)[0][0]


def _load_pdf_blocks(file_path: str | Path) -> list[dict[str, Any]]:
    """Build paragraph/table IR blocks per page, keeping tables roughly
    where they visually occur relative to the surrounding text the same
    way `_iter_block_items` keeps docx paragraphs/tables in document
    order -- exact pixel-perfect interleaving is not required, only that
    a table doesn't end up miles away from the heading it belongs under.
    Paragraph blocks carry an extra, IR-internal `font_size` hint (not
    part of the documented IR shape, since neither docx nor txt have an
    equivalent) that the pdf-specific heading heuristic and the
    diagnostic tools' synthetic style naming use."""
    blocks: list[dict[str, Any]] = []
    with pdfplumber.open(str(file_path)) as pdf:
        for page in pdf.pages:
            tables = page.find_tables()
            table_bboxes = [t.bbox for t in tables]

            words = page.extract_words(extra_attrs=["size", "fontname"])
            text_words = [w for w in words if not any(_word_in_bbox(w, bbox) for bbox in table_bboxes)]
            lines = _group_words_into_lines(text_words)

            page_items: list[tuple[float, dict[str, Any]]] = []
            for line in lines:
                text = " ".join(w["text"] for w in line).strip()
                if not text:
                    continue
                page_items.append((line[0]["top"], {
                    "kind": "paragraph",
                    "text": text,
                    "style_name": None,
                    "outline_level": None,
                    "is_bold": _line_is_bold(line),
                    "font_size": _line_font_size(line),
                }))
            for table in tables:
                rows = [[(cell or "").strip() for cell in row] for row in table.extract()]
                page_items.append((table.bbox[1], {"kind": "table", "rows": rows}))

            page_items.sort(key=lambda item: item[0])
            blocks.extend(item for _, item in page_items)
    return blocks


def _load_txt_blocks(file_path: str | Path) -> list[dict[str, Any]]:
    """Split a plain-text document into paragraph blocks on blank-line
    boundaries. Plain text carries no style, outline, or bold signal at
    all, so heading detection for .txt relies entirely on the
    numbered-heading and all-caps strategies in `detect_headings`."""
    path = Path(file_path)
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = path.read_text(encoding="latin-1")

    blocks: list[dict[str, Any]] = []
    for chunk in re.split(r"\n\s*\n", raw):
        text = chunk.strip()
        if not text:
            continue
        blocks.append({
            "kind": "paragraph",
            "text": text,
            "style_name": None,
            "outline_level": None,
            "is_bold": False,
        })
    return blocks


def _load_blocks(file_path: str | Path) -> list[dict[str, Any]]:
    """The single place that decides, by file extension, how to turn a
    document into the shared IR block list. Every other function in this
    module reads blocks through here so that `block_index` means the same
    thing everywhere for a given file."""
    suffix = Path(file_path).suffix.lower()
    if suffix == ".docx":
        return _load_docx_blocks(file_path)
    if suffix == ".pdf":
        return _load_pdf_blocks(file_path)
    if suffix == ".txt":
        return _load_txt_blocks(file_path)
    raise ValueError(f"Unsupported document format '{suffix}' (expected .docx, .pdf, or .txt)")


def _resolve_style_label(block: dict[str, Any]) -> str:
    """Diagnostic-only style label used by inspect_document_metadata and
    sample_paragraph_styles. docx paragraphs already carry a real style
    name; pdf has no style concept at all, so distinct font sizes are
    treated as a synthetic style family (a same-size line is, in effect,
    the same "style") rather than reporting nothing useful."""
    if block.get("style_name"):
        return block["style_name"]
    font_size = block.get("font_size")
    if font_size is not None:
        return f"pdf_font_{font_size}pt"
    return "(no style)"


# ===========================================================================
# 1. inspect_document_metadata
# ===========================================================================
def inspect_document_metadata(file_path: str | Path) -> dict[str, Any]:
    blocks = _load_blocks(file_path)
    paragraphs = [b for b in blocks if b["kind"] == "paragraph"]
    tables = [b for b in blocks if b["kind"] == "table"]
    style_usage: dict[str, int] = {}
    total_words = 0
    for p in paragraphs:
        label = _resolve_style_label(p)
        style_usage[label] = style_usage.get(label, 0) + 1
        total_words += len(p["text"].split())
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
    blocks = _load_blocks(file_path)
    by_style: dict[str, list[str]] = {}
    for b in blocks:
        if b["kind"] != "paragraph":
            continue
        text = b["text"].strip()
        if not text:
            continue
        by_style.setdefault(_resolve_style_label(b), []).append(text)

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
_NUMBERED_HEADING_PATTERN = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,4})\.?\s+\S")
_MAX_HEADING_TEXT_LENGTH = 150


def _extract_level_from_style_name(style_name: str) -> int | None:
    m = _ORDINAL_TOKEN_PATTERN.search(style_name)
    if not m:
        return None
    if m.group(1):
        return int(m.group(1))
    return _ORDINAL_WORDS.get(m.group(2).lower())


def _numbered_heading_headings(paragraphs: list[tuple[int, dict[str, Any]]]) -> tuple[list[dict[str, Any]], str | None]:
    """A line counts as a heading if its text starts with a dotted
    numeral like "16.3" or "16.3.1.2" (optionally followed by a period),
    then a space and more text -- exactly how most PBRER/regulatory
    documents actually type their section headings, and the strongest
    signal available when present, since it works identically regardless
    of format. The level is simply how many dot-separated segments the
    number has. Only adopted if it finds at least 2 headings spanning
    more than one distinct level -- the same quality bar the style_name
    strategy uses -- so a single body sentence that happens to start with
    a number doesn't get mistaken for a whole numbering scheme."""
    candidates = []
    for block_idx, p in paragraphs:
        text = p["text"].strip()
        if not text or len(text) > _MAX_HEADING_TEXT_LENGTH:
            continue
        m = _NUMBERED_HEADING_PATTERN.match(text)
        if not m:
            continue
        number = m.group(1)
        level = number.count(".") + 1
        # Strip the typed number back off -- it's recovered independently
        # via reconstruct_section_numbers/calibrate_section_numbers, so
        # leaving it in `text` would show it twice (once as the literal
        # prefix, once as the reconstructed section_number) wherever a
        # topic's title is displayed.
        title_text = text[m.end(1):].lstrip(". ").strip() or text
        candidates.append({
            "block_index": block_idx,
            "text": title_text,
            "style_name": p.get("style_name"),
            "level": level,
            "strategy": "numbered_heading",
        })
    distinct_levels = {h["level"] for h in candidates}
    if len(candidates) >= 2 and len(distinct_levels) >= 2:
        return candidates, "numbered_heading"
    return [], None


def _docx_fallback_headings(paragraphs: list[tuple[int, dict[str, Any]]]) -> tuple[list[dict[str, Any]], str]:
    """Three strategies, tried in order of reliability, for documents
    with no usable numbered-heading convention:
      1. style_name: a cluster of distinct, moderately-frequent styles
         whose names look heading-like (contain "heading"/"level"/"title"/
         "outline"), with a level number recovered from each style name.
      2. outline_level: Word's own w:outlineLvl paragraph property, when
         present, independent of style naming.
      3. bold_heuristic: short, fully-bold paragraphs with no run style
         evidence at all -- last resort, lower confidence."""
    style_counts: dict[str, int] = {}
    for _, p in paragraphs:
        if p["text"].strip():
            style_counts[p["style_name"]] = style_counts.get(p["style_name"], 0) + 1

    heading_like_styles = {
        name: count for name, count in style_counts.items()
        if name and _HEADING_STYLE_NAME_PATTERN.search(name) and 0 < count <= max(500, len(paragraphs) * 0.3)
    }

    if len(heading_like_styles) >= 2:
        headings = []
        level_by_style: dict[str, int] = {}
        next_fallback_level = 1
        seen_order: list[str] = []
        for block_idx, p in paragraphs:
            style_name = p["style_name"]
            if style_name not in heading_like_styles or not p["text"].strip():
                continue
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
                    "text": p["text"].strip(),
                    "style_name": style_name,
                    "level": level_by_style[style_name],
                    "strategy": "style_name",
                }
            )
        return headings, "style_name"

    outline_hits = [(i, p) for i, p in paragraphs if p["outline_level"] is not None and p["text"].strip()]
    if outline_hits:
        headings = [
            {
                "block_index": i,
                "text": p["text"].strip(),
                "style_name": p["style_name"],
                "level": p["outline_level"] + 1,  # outlineLvl is 0-based
                "strategy": "outline_level",
            }
            for i, p in outline_hits
        ]
        return headings, "outline_level"

    headings = []
    for block_idx, p in paragraphs:
        text = p["text"].strip()
        if not text or len(text) > 120 or text.endswith((".", ",", ";")):
            continue
        if p["is_bold"]:
            headings.append(
                {
                    "block_index": block_idx,
                    "text": text,
                    "style_name": p["style_name"],
                    "level": 1,  # cannot distinguish depth reliably from bold alone
                    "strategy": "bold_heuristic",
                }
            )
    return headings, "bold_heuristic"


def _font_size_heuristic_headings(paragraphs: list[tuple[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    """pdf fallback when there is no numbered-heading convention: a line
    qualifies as a heading if its dominant font size is meaningfully
    larger than the page's most common (body-text) size, or if it is
    bold. Distinct larger sizes are ranked into levels, biggest = level 1;
    bold-but-body-sized lines (no size signal to rank by) are bundled
    into one additional, deepest level."""
    sized = [(i, p) for i, p in paragraphs if p.get("font_size") is not None]
    if not sized:
        return []

    size_counts = Counter(p["font_size"] for _, p in sized)
    body_size, _ = size_counts.most_common(1)[0]
    larger_sizes = sorted({s for s in size_counts if s > body_size + 0.5}, reverse=True)
    if not larger_sizes:
        return []
    level_by_size = {size: level + 1 for level, size in enumerate(larger_sizes)}
    bold_fallback_level = len(larger_sizes) + 1

    headings = []
    for block_idx, p in sized:
        text = p["text"].strip()
        if not text or len(text) > _MAX_HEADING_TEXT_LENGTH:
            continue
        size = p["font_size"]
        if size in level_by_size:
            level = level_by_size[size]
        elif p["is_bold"]:
            level = bold_fallback_level
        else:
            continue
        headings.append({
            "block_index": block_idx,
            "text": text,
            "style_name": None,
            "level": level,
            "strategy": "font_size_heuristic",
        })
    return headings


def _all_caps_heading_fallback(paragraphs: list[tuple[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    """txt last resort when no numbered-heading convention is found:
    plain text has no bold/style/size signal at all, so a short,
    fully-upper-case line is the only remaining clue -- lower confidence,
    mirroring the role the bold_heuristic plays for docx."""
    headings = []
    for block_idx, p in paragraphs:
        text = p["text"].strip()
        if not text or len(text) >= 100:
            continue
        if text.isupper():
            headings.append({
                "block_index": block_idx,
                "text": text,
                "style_name": None,
                "level": 1,
                "strategy": "all_caps_heuristic",
            })
    return headings


def detect_headings(file_path: str | Path) -> dict[str, Any]:
    """Tries the numbered-heading strategy first (works identically
    across .docx/.pdf/.txt and is the strongest signal when present),
    then falls through to a format-specific chain: style_name ->
    outline_level -> bold_heuristic for .docx, font_size_heuristic for
    .pdf, all_caps_heuristic for .txt. Returns every heading found, in
    document order, each tagged with the strategy that identified it, or
    `strategy: None, headings: []` if nothing is found at all -- this
    never raises on a document with no detectable heading convention,
    since the calling agent already treats an empty heading list as a
    critical warning rather than a crash."""
    blocks = _load_blocks(file_path)
    paragraphs = [(i, b) for i, b in enumerate(blocks) if b["kind"] == "paragraph"]

    headings, strategy = _numbered_heading_headings(paragraphs)

    if strategy is None:
        suffix = Path(file_path).suffix.lower()
        if suffix == ".docx":
            headings, strategy = _docx_fallback_headings(paragraphs)
        elif suffix == ".pdf":
            headings = _font_size_heuristic_headings(paragraphs)
            strategy = "font_size_heuristic" if headings else None
        else:
            headings = _all_caps_heading_fallback(paragraphs)
            strategy = "all_caps_heuristic" if headings else None

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
    blocks = _load_blocks(file_path)
    full_text = "\n".join(b["text"] for b in blocks if b["kind"] == "paragraph")
    citations = _SECTION_CITATION_PATTERN.findall(full_text)
    if not citations:
        return {"absolute_number": None, "confidence": 0.0, "evidence": "no 'Section x.y.z' citations found in document text"}

    target_segments = target_relative_number.split(".")
    n = len(target_segments)
    matches = [c for c in citations if c.split(".")[-n:] == target_segments]
    if not matches:
        return {"absolute_number": None, "confidence": 0.0,
                "evidence": f"no citation's trailing {n} segment(s) match relative chain '{target_relative_number}'"}

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
def _reshape_table_rows(raw_rows: list[list[str]]) -> list[dict[str, str]]:
    """Generic 2-column label/value reshaping, applied uniformly to every
    format's raw table grid. docx grids have already had merge
    continuations collapsed to empty strings by `_load_blocks`, so a
    continuation cell behaves exactly like a genuinely empty one here --
    there is nothing format-specific left to handle at this point."""
    rows = []
    for texts in raw_rows:
        if len(texts) >= 2:
            label = texts[0]
            value_parts = [t for t in texts[1:] if t]
            if label or value_parts:
                rows.append({"label": label, "value": " | ".join(value_parts)})
        elif texts and texts[0]:
            rows.append({"label": texts[0], "value": ""})
    return rows


def extract_tables_near_heading(file_path: str | Path, heading_block_index: int,
                                 next_heading_block_index: int | None) -> dict[str, Any]:
    """Collect every table AND every non-empty paragraph physically
    located between this heading and the next one (or end of document),
    using true document order. PBRER tables used for topic data are
    typically simple 2-column label/value tables -- parsed generically as
    a list of {label, value} rows, not assuming a fixed row count."""
    blocks = _load_blocks(file_path)

    end = next_heading_block_index if next_heading_block_index is not None else len(blocks)
    tables_out = []
    paragraphs_out = []
    for idx, block in enumerate(blocks):
        if idx <= heading_block_index or idx >= end:
            continue
        if block["kind"] == "table":
            tables_out.append({"block_index": idx, "rows": _reshape_table_rows(block["rows"])})
        else:
            text = block["text"].strip()
            if text:
                paragraphs_out.append({"block_index": idx, "text": text})

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
