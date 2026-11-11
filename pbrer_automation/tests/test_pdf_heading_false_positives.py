"""
Regression tests for tools.document_tools._numbered_heading_headings'
quality filter, built directly from real false-positive/true-positive
heading candidates observed in production against an actual PBRER PDF
export (the same source document as the .docx fixture, re-uploaded as
.pdf): PDF reconstructs paragraphs line-by-line (see
_group_words_into_lines), unlike python-docx's real paragraph objects,
so a sentence's own line-wrap boundary can coincidentally start with a
digit and get misdetected as a "16.3"-style numbered section heading.
Before this filter, that PDF upload located only 1 of the 7 real Section
16.3 topics (a shallow false-positive heading prematurely terminated
extract_topic_subtree's boundary search); after it, all 7 are found
(verified against the real file).
"""
from __future__ import annotations

from tools.document_tools import _numbered_heading_headings

# Real false positives observed in production (paragraph text, synthetic
# block index) -- none of these are real PBRER section headings.
_REAL_FALSE_POSITIVES = [
    "2.25 mg, or 3.15 mg pramipexole, corresponding to 0.375 mg, 0.75 mg, 1.5 mg, 2.25 mg,",
    "14",
    "74",
    "10 \u2013 20 0 0",
    "30 \u2013 30 5 1",
    "2 4",
    "3% Prospective studies are warranted to confirm",
]

# Real true positives observed in the same document -- every one of
# these must keep being detected.
_REAL_TRUE_POSITIVES = [
    "16.3.1.1 Cardiac failure",
    "16.3.1.2 Impulse control disorders such as compulsive shopping, pathological gambling,",
    "16.3.1.3 Hallucinations and confusion",
    "16.3.1.4 Dopamine agonist withdrawal syndrome",
    "16.3.1.5 Augmentation, post-treatment worsening after withdrawal, and rebound in",
    "16.3.2.1 Dystonia (such as antecollis, camptocormia, pleurothotonus)",
    "16.3.2.2 Suicide-related behaviour",
    "16.3 EVALUATION OF RISKS AND NEW INFORMATION",
    "1 INTRODUCTION",
    "2 WORLDWIDE MARKETING AUTHORISATION STATUS",
]


def _candidates_for(texts: list[str]) -> list[dict]:
    paragraphs = [(i, {"text": t}) for i, t in enumerate(texts)]
    candidates, strategy = _numbered_heading_headings(paragraphs)
    return candidates


def test_real_false_positives_from_production_pdf_are_rejected():
    candidates = _candidates_for(_REAL_FALSE_POSITIVES)
    assert candidates == []


def test_real_true_positives_from_production_pdf_are_all_detected():
    candidates = _candidates_for(_REAL_TRUE_POSITIVES)
    assert len(candidates) == len(_REAL_TRUE_POSITIVES)
    titles = {c["text"] for c in candidates}
    assert "Cardiac failure" in titles
    assert "Hallucinations and confusion" in titles
    assert "Dystonia (such as antecollis, camptocormia, pleurothotonus)" in titles
    assert "Suicide-related behaviour" in titles
    assert "INTRODUCTION" in titles


def test_mixed_real_and_false_candidates_only_keeps_the_real_ones():
    mixed = _REAL_TRUE_POSITIVES + _REAL_FALSE_POSITIVES
    candidates = _candidates_for(mixed)
    assert len(candidates) == len(_REAL_TRUE_POSITIVES)
