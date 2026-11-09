"""
Full end-to-end pipeline test against the real development fixtures,
reproducing prompt.md Part 6's benchmark table exactly. Marked slow since
it runs all four agents + the calculation engine against real files
(several minutes, dominated by the 28k/63k-row all-case/all-drug-event
exports).
"""
from __future__ import annotations

import pytest

from pipeline import run_full_pipeline


@pytest.mark.slow
def test_full_pipeline_reproduces_benchmark(docx_path, input_dir):
    result = run_full_pipeline("pytest-e2e", str(docx_path), str(input_dir), "2019-04-07", "2024-04-06")

    by_key = {(mr.pbrer_section_number, mr.metric_id): mr.calculated_value for mr in result["metric_results"]}

    assert by_key[(None, "total_case_count")] == 3651
    assert by_key[("16.3.1.2", "topic_case_count")] == 242
    assert by_key[("16.3.1.2", "serious_case_count")] == 55
    assert by_key[("16.3.1.2", "fatal_case_count")] == 1
    assert by_key[("16.3.1.3", "topic_case_count")] == 270
    assert by_key[("16.3.1.3", "serious_case_count")] == 98
    assert by_key[("16.3.1.3", "fatal_case_count")] == 1

    all_breakdown = by_key[(None, "source_breakdown")]
    assert all_breakdown["Spontaneous"] == 3272
    assert all_breakdown["Report from study-Other Studies"] == 379

    # No metric should fail validation on these known-good fixtures.
    failed = [mr for mr in result["metric_results"] if mr.validation_status == "failed"]
    assert not failed, f"unexpected validation failures: {[(f.metric_id, f.validation_messages) for f in failed]}"
