from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = PROJECT_ROOT.parent / "input"


@pytest.fixture(scope="session")
def input_dir() -> Path:
    if not INPUT_DIR.exists():
        pytest.skip(f"Real input fixtures not found at {INPUT_DIR}")
    return INPUT_DIR


@pytest.fixture(scope="session")
def docx_path(input_dir) -> Path:
    candidates = list(input_dir.glob("*.docx"))
    if not candidates:
        pytest.skip("No .docx fixture found")
    return candidates[0]


@pytest.fixture(scope="session")
def hallucinations_case_file(input_dir) -> Path:
    return input_dir / "04_case_Hallucinations and confusion_CSMR.xlsx"


@pytest.fixture(scope="session")
def hallucinations_event_file(input_dir) -> Path:
    return input_dir / "04_drugevent_Hallucinations and confusion_CSMR.xlsx"


@pytest.fixture(scope="session")
def pipeline_result(docx_path, input_dir):
    """One real end-to-end pipeline run, reused across every frontend
    AppTest so each page renders against genuine agent/calculation
    output rather than hand-built fixtures that could silently drift
    from the real schema. Session-scoped + the file-hash analysis cache
    (llm/cache.py) keep this fast after the first slow-marked run."""
    from pipeline import run_full_pipeline

    return run_full_pipeline("pytest-frontend", str(docx_path), str(input_dir), "2019-04-07", "2024-04-06")
