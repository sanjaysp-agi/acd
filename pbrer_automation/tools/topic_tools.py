"""
Predefined Python tools for connecting the Document Agent's topic
catalogue to the Excel Agent's workbook inventory.

The PBRER heading's prose description of its search criteria ("MedDRA
HLTs 'Hallucinations (excl sleep-related)' and 'Confusion and
disorientation'") and the Excel cover page's own criterion value
("Hallucinations (excl sleep-related), Confusion and disorientation")
are never guaranteed to be worded identically -- different punctuation,
conjunctions, quoting. Matching is done by extracting the underlying set
of individual MedDRA terms from each and scoring their overlap, not by
assuming the two strings are equal or that a heading's number tells you
which workbook belongs to it.
"""
from __future__ import annotations

import re
from typing import Any

# Prefixes/criterion-type words that appear in the document's prose
# description but not in the Excel cover page's own value -- stripped
# before splitting into terms so they don't get treated as spurious terms.
_CRITERION_TYPE_PREFIX_PATTERN = re.compile(
    r"^(broad|narrow)?\s*(meddra\s+)?(pts?|hlts?|hlgts?|socs?|smqs?|cmqs?)\b\s*:?\s*", re.IGNORECASE
)


def extract_criterion_terms(text: str | None) -> list[str]:
    """Normalize a criteria string (Excel cover-page style, comma-
    separated; or prose style with semicolons/'and'/quotes) into a clean
    list of individual term strings for overlap scoring."""
    if not text:
        return []
    cleaned = _CRITERION_TYPE_PREFIX_PATTERN.sub("", text)
    cleaned = cleaned.replace('"', "").replace("'", "").replace("‘", "").replace("’", "")
    cleaned = cleaned.replace("“", "").replace("”", "")
    cleaned = re.sub(r"\(SMQ\)|\(Narrow\)|\(Broad\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+and\s+", ";", cleaned, flags=re.IGNORECASE)
    parts = re.split(r"[;,]", cleaned)
    terms = [p.strip().lower() for p in parts if p.strip()]
    return terms


def extract_excel_criterion_terms(excel_criterion_value: str | None) -> list[str]:
    """Split an Excel cover-page criterion VALUE (already a clean,
    comma-separated list of exact MedDRA terms, e.g. 'Hallucinations
    (excl sleep-related), Confusion and disorientation') into individual
    terms for EXACT matching against a MedDRA classification column
    (processing.topic_reconstruction).

    Deliberately simpler than extract_criterion_terms above: this does
    NOT treat the word 'and' as a conjunction between two separate
    criteria -- a real MedDRA HLT can itself contain the word 'and'
    (e.g. 'Confusion and disorientation'), and extract_criterion_terms'
    "\\s+and\\s+" -> ";" rule (tuned for scoring loosely-worded PROSE
    document text, where some over-splitting only costs Jaccard-score
    precision) would silently fragment that single term into two and
    make exact reconstruction undercount real matching rows."""
    if not excel_criterion_value:
        return []
    cleaned = excel_criterion_value.replace('"', "").replace("'", "").replace("‘", "").replace("’", "")
    cleaned = cleaned.replace("“", "").replace("”", "")
    parts = cleaned.split(",")
    return [p.strip().lower() for p in parts if p.strip()]


def score_topic_workbook_match(doc_search_criteria_text: str | None, excel_criterion_value: str | None) -> dict[str, Any]:
    """Jaccard-style overlap between the term set implied by the
    document's prose criteria and the Excel cover page's own criterion
    value. 1.0 = identical term sets; 0.0 = no shared terms."""
    doc_terms = set(extract_criterion_terms(doc_search_criteria_text))
    excel_terms = set(extract_criterion_terms(excel_criterion_value))
    if not doc_terms or not excel_terms:
        return {"score": 0.0, "doc_terms": sorted(doc_terms), "excel_terms": sorted(excel_terms)}
    intersection = doc_terms & excel_terms
    union = doc_terms | excel_terms
    score = len(intersection) / len(union) if union else 0.0
    return {"score": round(score, 3), "doc_terms": sorted(doc_terms), "excel_terms": sorted(excel_terms),
            "shared_terms": sorted(intersection)}


def match_topics_to_workbooks(document_topics: list[dict[str, Any]],
                               case_workbooks: list[dict[str, Any]]) -> dict[str, Any]:
    """Greedy best-match assignment: each document topic is paired with
    the topic-specific case workbook whose cover-page criterion has the
    highest term overlap with the topic's own search-criteria text.
    Workbooks are matched at most once. Topics/workbooks below a minimum
    score are left unmatched rather than forced -- a wrong pairing would
    silently route the wrong numbers to a PBRER heading, which is worse
    than admitting no match was found."""
    MIN_SCORE = 0.3
    used_workbooks: set[str] = set()
    mappings = []
    for topic in document_topics:
        doc_criteria = (topic.get("historical_metrics") or {}).get("search_criteria_text")
        best_wb, best_score, best_detail, used_fallback = None, 0.0, None, False
        for wb in case_workbooks:
            if wb["file_name"] in used_workbooks:
                continue
            cpc = wb.get("cover_page_criteria") or {}
            detail = score_topic_workbook_match(doc_criteria, cpc.get("criterion_value"))
            is_fallback = False
            if detail["score"] == 0.0 and not doc_criteria:
                # The document has no search-criteria text for this topic
                # at all (e.g. Cardiac failure has no data table in the
                # current PBRER -- downgraded risk, nothing to extract).
                # Fall back to comparing the topic's own HEADING TITLE
                # against the workbook's criterion value -- weaker
                # evidence (a title isn't a formal criteria list), so it
                # is capped and always flagged for review, but it's
                # better than leaving a workbook we DO have unmatched
                # when the title match is unambiguous (e.g. "Cardiac
                # failure" title vs "Cardiac failure (SMQ) (Narrow)").
                title = (topic.get("title") or "").strip().lower()
                criterion_value = (cpc.get("criterion_value") or "").strip().lower()
                if title and criterion_value and title in criterion_value:
                    detail = {"score": 0.5, "doc_terms": [title], "excel_terms": [criterion_value],
                              "shared_terms": [title], "fallback": "heading_title_substring_match"}
                    is_fallback = True
            if detail["score"] > best_score:
                best_wb, best_score, best_detail, used_fallback = wb, detail["score"], detail, is_fallback

        if best_wb is not None and best_score >= MIN_SCORE:
            used_workbooks.add(best_wb["file_name"])
            mappings.append({
                "pbrer_section_number": topic.get("section_number"),
                "pbrer_heading": topic.get("title"),
                "excel_criterion_type": (best_wb.get("cover_page_criteria") or {}).get("criterion_type", "unknown"),
                "excel_criterion_value": (best_wb.get("cover_page_criteria") or {}).get("criterion_value"),
                "case_workbook": best_wb["file_name"],
                "drug_event_workbook": best_wb.get("linked_workbook"),
                "confidence": best_score,
                "needs_review": used_fallback or best_score < 0.7,
                "match_evidence": best_detail,
            })
        else:
            mappings.append({
                "pbrer_section_number": topic.get("section_number"),
                "pbrer_heading": topic.get("title"),
                "excel_criterion_type": "unknown",
                "excel_criterion_value": None,
                "case_workbook": None,
                "drug_event_workbook": None,
                "confidence": 0.0,
                "needs_review": True,
                "match_evidence": {"reason": "no workbook met the minimum overlap score",
                                    "best_score_seen": best_score},
            })

    unmatched_workbooks = [wb["file_name"] for wb in case_workbooks if wb["file_name"] not in used_workbooks]
    return {"mappings": mappings, "unmatched_workbooks": unmatched_workbooks}
