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

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Explicit path, not the default search-upward behavior: this repo's .env
# lives in the project root, but uvicorn's cwd isn't guaranteed to be there.
# Real environment variables (e.g. already-exported AWS creds) still win --
# load_dotenv() never overrides an existing os.environ entry.
load_dotenv(PROJECT_ROOT / ".env")

# AWS_PROFILE= (blank, meaning "no profile") is valid in .env, but boto3
# reads AWS_PROFILE straight from os.environ itself -- a blank string isn't
# "unset" to boto3, it tries to load a profile literally named "" and fails
# with "The config profile () could not be found". Strip it so an empty
# value behaves like the var was never set.
if not os.environ.get("AWS_PROFILE"):
    os.environ.pop("AWS_PROFILE", None)

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


def _env_list(name: str, default: tuple[str, ...], sep: str = "|") -> tuple[str, ...]:
    val = os.environ.get(name)
    if val is None:
        return default
    items = tuple(item.strip() for item in val.split(sep) if item.strip())
    return items or default


# Narrative-document and tabular-data formats this pipeline can ingest.
# Overridable per deployment (e.g. a tenant whose exporter only ever
# produces .csv) without a code change -- these are capability lists, not
# facts about any one tenant's file shape.
NARRATIVE_DOCUMENT_EXTENSIONS: tuple[str, ...] = _env_list(
    "PBRER_NARRATIVE_EXTENSIONS", (".docx", ".pdf", ".txt")
)
TABULAR_DATA_EXTENSIONS: tuple[str, ...] = _env_list(
    "PBRER_TABULAR_EXTENSIONS", (".xlsx", ".xls", ".csv")
)


@dataclass(frozen=True)
class LLMSettings:
    provider: str = os.environ.get("PBRER_LLM_PROVIDER", "local")  # "local" | "bedrock"
    aws_profile: str | None = os.environ.get("AWS_PROFILE")
    aws_region: str = os.environ.get("AWS_REGION", "eu-west-1")
    # Cross-region inference profile ID, not a plain on-demand model ID --
    # newer Claude models on Bedrock are only available this way in most
    # accounts (confirmed via `aws bedrock list-inference-profiles`).
    bedrock_model_id: str = os.environ.get(
        "BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"
    )
    # Safety ceiling on tool-calling round trips within a SINGLE agent run
    # (prompt.md Part 8) -- not a tight per-run budget (that's
    # max_invocations_per_run below); sized generously enough that the
    # Document Agent's paragraph-by-paragraph investigation of a large
    # PBRER never hits it in normal operation, while still guaranteeing a
    # runaway tool-calling loop terminates rather than running unbounded.
    max_tool_iterations: int = _env_int("PBRER_MAX_TOOL_ITERATIONS", 200)
    max_invocations_per_run: int = _env_int("PBRER_MAX_INVOCATIONS_PER_RUN", 40)
    # Document/Excel Agent tool chains routinely need the model to echo a
    # prior tool result's array back as the NEXT tool call's argument (e.g.
    # detect_headings' full heading list into exclude_front_matter_headings).
    # Confirmed empirically: a real ~1700-block PBRER document's 124
    # headings alone need ~5000 output tokens to round-trip; the old 2048
    # default silently truncated generation mid-tool-call, leaving an
    # empty/unusable argument with no error raised anywhere.
    max_output_tokens: int = _env_int("PBRER_MAX_OUTPUT_TOKENS", 16000)
    temperature: float = 0.0
    enable_cache: bool = _env_bool("PBRER_ENABLE_LLM_CACHE", True)


@dataclass(frozen=True)
class DocumentAgentSettings:
    # Candidate titles for the PBRER section that contains topic-level
    # safety evaluations -- domain configuration for "what we are looking
    # for in a PBRER" (this application's whole purpose), not a guess about
    # one tenant's wording. Multiple phrasings are tried because different
    # PBRER templates/versions word this heading slightly differently; a
    # deployment onboarding a template that uses a third phrasing adds it
    # here instead of patching code.
    target_section_title_candidates: tuple[str, ...] = _env_list(
        "PBRER_TARGET_SECTION_TITLES",
        ("Evaluation of Risks and New Information", "Signal and Risk Evaluation"),
    )
    # The leaf topics we want metrics for sit this many heading-levels below
    # the target section header (16.3 -> 16.3.1 "New information on
    # important identified risks" -> 16.3.1.1 "Cardiac failure" = 2). A
    # template nesting its topics at a different depth overrides this via
    # env var rather than requiring a code change.
    leaf_topic_depth_below_target: int = _env_int("PBRER_LEAF_TOPIC_DEPTH", 2)


@dataclass(frozen=True)
class AppSettings:
    llm: LLMSettings = field(default_factory=LLMSettings)
    document_agent: DocumentAgentSettings = field(default_factory=DocumentAgentSettings)
    rounding_decimals: int = _env_int("PBRER_ROUNDING_DECIMALS", 1)
    low_confidence_threshold: float = float(os.environ.get("PBRER_LOW_CONFIDENCE_THRESHOLD", "0.6"))


settings = AppSettings()
