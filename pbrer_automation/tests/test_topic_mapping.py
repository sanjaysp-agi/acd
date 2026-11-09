from __future__ import annotations

from tools.topic_tools import score_topic_workbook_match


def test_correct_pairs_score_high():
    cases = [
        ("MedDRA HLTs 'Hallucinations (excl sleep-related)' and 'Confusion and disorientation'",
         "Hallucinations (excl sleep-related), Confusion and disorientation"),
        ("Narrow SMQ 'Cardiac failure'", "Cardiac failure (SMQ) (Narrow)"),
        ("MedDRA PTs Rebound effect; Restless legs syndrome, Restless leg augmentation syndrome",
         "Rebound effect, Restless legs syndrome, Restless leg augmentation syndrome"),
    ]
    for doc_text, excel_text in cases:
        result = score_topic_workbook_match(doc_text, excel_text)
        assert result["score"] >= 0.7, f"expected high score for matching pair, got {result}"


def test_unrelated_pairs_score_low():
    doc_text = "MedDRA HLTs 'Hallucinations (excl sleep-related)' and 'Confusion and disorientation'"
    unrelated_excel_text = "Cardiac failure (SMQ) (Narrow)"
    result = score_topic_workbook_match(doc_text, unrelated_excel_text)
    assert result["score"] < 0.3
