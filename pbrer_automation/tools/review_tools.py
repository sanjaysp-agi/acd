"""
Predefined Python tool for the deterministic half of the Extraction
Completeness Review Agent.

This computes a baseline set of completeness findings purely from the
structured output already produced by the Document/Excel Understanding
Agents and the calculation engine -- no re-reading of source files, no
guessed numbers. It exists so local-deterministic mode has a genuine,
rule-based review to run (the same honest-fallback pattern as every other
agent's local policy), and so a real LLM provider has a reliable floor to
build on rather than reviewing raw evidence from nothing.
"""
from __future__ import annotations

from typing import Any

from config.metric_registry import METRIC_REGISTRY

# Heading-detection strategies that do NOT rely on real paragraph-level
# structure (python-docx style names / outlineLvl) -- the numbered-heading
# and docx style_name/outline_level strategies are strong, format-backed
# signals; font_size_heuristic (.pdf) and bold_heuristic/all_caps_heuristic
# (.docx/.txt last resorts) are visual guesses with materially weaker
# precision, and a PDF export in particular loses paragraph style metadata
# entirely on conversion from Word. A document extracted under one of
# these is more likely to have missed a table/section than one extracted
# under a format-backed strategy.
_WEAKER_HEADING_STRATEGIES = {"font_size_heuristic", "bold_heuristic", "all_caps_heuristic"}


def check_extraction_completeness(document_topics: list[dict[str, Any]],
                                    workbook_entries: list[dict[str, Any]],
                                    metric_results: list[dict[str, Any]],
                                    heading_style_strategy: str | None = None) -> dict[str, Any]:
    """Flags three independent classes of "extraction may have missed
    something": a topic whose historical PBRER figures imply a metric that
    never got calculated; a canonical field no uploaded workbook ever
    mapped, silently disabling every metric that requires it; and a
    workbook that was discovered but never resolved to a usable type.
    Every finding is advisory (severity 'info' or 'warning', never
    'critical') -- this review informs a human reviewer, it never blocks
    the pipeline on its own.

    `heading_style_strategy` (DocumentStructure.heading_style_strategy) is
    used only to decide whether a "no table rows extracted" finding is
    worth a 'warning' instead of a quiet 'info': under a weaker,
    non-format-backed heading strategy (see _WEAKER_HEADING_STRATEGIES)
    that same finding is much more likely to mean "extraction actually
    failed" than "this topic genuinely has no table" -- never escalates
    anything else, and never fabricates a finding that the deterministic
    checks below didn't already produce."""
    findings: list[dict[str, Any]] = []
    uses_weaker_strategy = heading_style_strategy in _WEAKER_HEADING_STRATEGIES

    metric_ids_by_section: dict[str | None, set[str]] = {}
    for mr in metric_results:
        metric_ids_by_section.setdefault(mr.get("pbrer_section_number"), set()).add(mr.get("metric_id"))

    for topic in document_topics:
        section = topic.get("section_number")
        title = topic.get("title")
        historical = topic.get("historical_metrics") or {}
        have = metric_ids_by_section.get(section, set())

        if (historical.get("topic_count") is not None or historical.get("total_count") is not None) and not (
            {"topic_case_count", "total_case_count"} & have
        ):
            findings.append({
                "severity": "warning", "pbrer_section_number": section, "topic_heading": title,
                "message": f"'{title}' has a historical case count in the source document but no "
                           "calculated case count for the current period -- confirm its workbook mapping "
                           "is not missing.",
            })
        if historical.get("serious_count") is not None and "serious_case_count" not in have:
            findings.append({
                "severity": "warning", "pbrer_section_number": section, "topic_heading": title,
                "message": f"'{title}' has a historical serious-case figure but no calculated serious "
                           "case count for the current period.",
            })
        if historical.get("fatal_count") is not None and "fatal_case_count" not in have:
            findings.append({
                "severity": "warning", "pbrer_section_number": section, "topic_heading": title,
                "message": f"'{title}' has a historical fatal-case figure but no calculated fatal case "
                           "count for the current period.",
            })
        if not topic.get("raw_table_rows"):
            if uses_weaker_strategy:
                findings.append({
                    "severity": "warning", "pbrer_section_number": section, "topic_heading": title,
                    "message": f"No data table rows were extracted near '{title}' in the source document, AND "
                               f"the document's headings were detected via the weaker '{heading_style_strategy}' "
                               "strategy (common for PDF/scanned input, which loses Word's real paragraph-style "
                               "metadata) -- this combination is a much stronger signal of a genuine extraction "
                               "problem than a missing table alone. Re-check this topic's source document "
                               "against the original .docx if available.",
                })
            else:
                findings.append({
                    "severity": "info", "pbrer_section_number": section, "topic_heading": title,
                    "message": f"No data table rows were extracted near '{title}' in the source document -- "
                               "its historical figures may be incomplete.",
                })

    required_fields = {f.value for m in METRIC_REGISTRY.values() for f in m.required_fields}
    mapped_fields = {
        cm.get("canonical_field")
        for wb in workbook_entries
        for cm in wb.get("column_mappings", [])
        if cm.get("canonical_field")
    }
    for field in sorted(required_fields - mapped_fields):
        findings.append({
            "severity": "warning", "pbrer_section_number": None, "topic_heading": None,
            "message": f"Canonical field '{field}' was never mapped in any uploaded workbook -- every "
                       "metric that requires it could not be calculated.",
        })

    for wb in workbook_entries:
        if wb.get("workbook_type") == "unclassified":
            findings.append({
                "severity": "warning", "pbrer_section_number": None, "topic_heading": None,
                "message": f"Workbook '{wb.get('file_name')}' could not be classified as a case or "
                           "drug-event export -- its data was not used in any calculation.",
            })

    return {"findings": findings}
