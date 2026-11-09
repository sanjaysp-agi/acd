"""
Application settings. All values are overridable via environment variables
(see .env.example). Nothing here hardcodes a tenant-specific file shape --
only global, non-configurable business rules (see metric_registry.py for why
CLINICAL_TRIALS_SOURCE_VALUE lives there, not here).
"""
from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
INPUT_DIR = DATA_DIR / "input"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = DATA_DIR / "output"
RUNS_DIR = DATA_DIR / "runs"

for _d in (INPUT_DIR, CACHE_DIR, OUTPUT_DIR, RUNS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


@dataclass(frozen=True)
class LLMSettings:
    provider: str = os.environ.get("PBRER_LLM_PROVIDER", "local")  # "local" | "bedrock"
    aws_profile: str | None = os.environ.get("AWS_PROFILE")
    aws_region: str = os.environ.get("AWS_REGION", "eu-west-1")
    bedrock_model_id: str = os.environ.get(
        "BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0"
    )
    # Safety ceiling on tool-calling round trips within a SINGLE agent run
    # (prompt.md Part 8) -- not a tight per-run budget (that's
    # max_invocations_per_run below); sized generously enough that the
    # Document Agent's paragraph-by-paragraph investigation of a large
    # PBRER never hits it in normal operation, while still guaranteeing a
    # runaway tool-calling loop terminates rather than running unbounded.
    max_tool_iterations: int = _env_int("PBRER_MAX_TOOL_ITERATIONS", 200)
    max_invocations_per_run: int = _env_int("PBRER_MAX_INVOCATIONS_PER_RUN", 40)
    max_output_tokens: int = _env_int("PBRER_MAX_OUTPUT_TOKENS", 2048)
    temperature: float = 0.0
    enable_cache: bool = _env_bool("PBRER_ENABLE_LLM_CACHE", True)


@dataclass(frozen=True)
class AppSettings:
    llm: LLMSettings = field(default_factory=LLMSettings)
    rounding_decimals: int = _env_int("PBRER_ROUNDING_DECIMALS", 1)
    low_confidence_threshold: float = float(os.environ.get("PBRER_LOW_CONFIDENCE_THRESHOLD", "0.6"))


settings = AppSettings()
