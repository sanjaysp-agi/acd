"""
Metric registry: controlled, approved calculation rules for Section 16.3
numerical metrics.

Design rule (confirmed with the business owner during scoping):
  - Excluding Clinical-Trial-sourced cases is a FIXED, non-configurable
    RULE: it is always applied, cannot be toggled per tenant/topic, and no
    AI agent or config file can turn it off. That is a Python constant
    (CLINICAL_TRIALS_EXCLUSION_ENABLED), not a registry entry.
  - What is NOT fixed is the exact wording a given tenant's export uses for
    that category. This tenant's files happen to spell it
    "Report from study-Clinical Trials", but another export could spell it
    differently. So the *rule* is hardcoded; the *value recognition* is a
    dynamic pattern match (see is_clinical_trial_source below), run against
    the actual distinct values profiled from the primary-source column at
    runtime, not a hardcoded literal string comparison.
  - The canonical field names below are the stable vocabulary that dynamic
    column-mapping (tools/excel_tools.map_columns_to_schema) maps real,
    possibly-unknown workbook headers onto. They are not literal Excel
    header strings -- a different tenant's export may use entirely
    different header text for the same canonical field.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Fixed, non-configurable rule: Clinical-Trial-sourced cases are ALWAYS
# excluded. The rule cannot be disabled. The matcher below is dynamic so it
# keeps working if a tenant's export phrases the category differently.
# ---------------------------------------------------------------------------
CLINICAL_TRIALS_EXCLUSION_ENABLED = True
_CLINICAL_TRIAL_PATTERN = re.compile(r"clinical\s*trial", re.IGNORECASE)


def is_clinical_trial_source(value) -> bool:
    """Dynamic recognizer for the Clinical Trials primary-source category.

    Matches on normalized substring ("clinical trial", case/whitespace
    insensitive) rather than a single hardcoded literal string, so it keeps
    working if a tenant's export phrases the category differently (e.g.
    "Report from study-Clinical Trials", "Clinical Trial Report",
    "CT - Clinical Trials", etc.). Callers should always run this against
    every distinct value actually observed in the mapped primary-source
    column (via profiling) and record which value(s) matched, so the match
    is auditable rather than silent.
    """
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    return bool(_CLINICAL_TRIAL_PATTERN.search(text))


# ---------------------------------------------------------------------------
# Canonical schema -- the stable vocabulary agents map real columns onto
# ---------------------------------------------------------------------------
class CanonicalField(str, Enum):
    CASE_ID = "case_id"
    INITIAL_APPROVAL_DATE = "initial_approval_date"
    PRIMARY_SOURCE = "primary_source"
    CASE_SERIOUSNESS = "case_seriousness"
    CASE_DEATH = "case_death"
    CASE_TYPE = "case_type"
    EVENT_PT = "event_pt"
    EVENT_HLT = "event_hlt"
    EVENT_HLGT = "event_hlgt"
    EVENT_SOC = "event_soc"
    EVENT_SERIOUSNESS = "event_seriousness"
    EVENT_DEATH = "event_death"
    EVENT_RELATEDNESS = "event_relatedness"


CLINICAL_TRIALS_EXCLUSION_CANONICAL_FIELD = CanonicalField.PRIMARY_SOURCE


# ---------------------------------------------------------------------------
# Yes/No style fields: recognized by normalized comparison (trim + casefold),
# not a brittle exact-case literal match, since tenants may export "YES",
# "yes ", "Y", etc. Each DISTINCT category below (No, No Information, Not
# Asked, Unknown, Masked, blank) must stay distinguishable from true "No" --
# never silently coalesced -- but all are normalized the same way.
# ---------------------------------------------------------------------------
def normalize_flag_value(value) -> str:
    """Normalize a Yes/No-style cell value for comparison (trim + casefold)."""
    if value is None:
        return ""
    return str(value).strip().casefold()


def is_affirmative(value) -> bool:
    return normalize_flag_value(value) == "yes"


KNOWN_NON_AFFIRMATIVE_CATEGORIES = {
    "no",
    "no information",
    "not asked",
    "unknown",
    "masked",
    "",
}


class WorkbookType(str, Enum):
    ALL_CASE = "all_case"
    TOPIC_CASE = "topic_case"
    ALL_DRUG_EVENT = "all_drug_event"
    TOPIC_DRUG_EVENT = "topic_drug_event"
    UNCLASSIFIED = "unclassified"


class DataGrain(str, Enum):
    ONE_ROW_PER_CASE = "one_row_per_case"
    ONE_ROW_PER_CASE_EVENT = "one_row_per_case_event"
    UNKNOWN = "unknown"


class CriterionType(str, Enum):
    PT = "PT"
    HLT = "HLT"
    HLGT = "HLGT"
    SOC = "SOC"
    SMQ = "SMQ"
    CMQ = "CMQ"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Configurable case-population rule (Part 3-K). Default mirrors the current
# validated benchmark behaviour: do NOT silently drop these case types.
# Must be confirmed against company SOP before being treated as final.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CasePopulationRule:
    exclude_case_types: tuple[str, ...] = ()  # e.g. () means include everything
    requires_sop_confirmation: bool = True
    note: str = (
        "Current benchmark includes Invalid AE case / Invalid non-AE case / "
        "Non-AE case records. Do not exclude unless an approved SOP rule "
        "explicitly requires it."
    )


@dataclass(frozen=True)
class RelatednessRule:
    apply_relatedness_filter: bool = False
    note: str = (
        "Current validated methodology does NOT filter by "
        "Derived-Overall-Event-Relatedness. Applying it changed the "
        "Hallucinations serious count from 98 to 95 in independent testing. "
        "Keep disabled unless an approved SOP rule explicitly requires it."
    )


@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    description: str
    source_workbook_type: WorkbookType
    grain: DataGrain
    required_fields: tuple[CanonicalField, ...]
    applies_date_filter: bool = True
    distinct_by: CanonicalField | None = CanonicalField.CASE_ID
    # Clinical Trials exclusion is NOT a per-metric flag -- it is globally
    # fixed (CLINICAL_TRIALS_EXCLUSION_ENABLED) and applied by
    # processing/source_filter.py to every metric whose required_fields
    # include PRIMARY_SOURCE. No metric can opt out.


METRIC_REGISTRY: dict[str, MetricDefinition] = {
    "topic_case_count": MetricDefinition(
        metric_id="topic_case_count",
        description="Distinct Case Number count from the topic-specific case workbook, "
        "within the reporting period, excluding Clinical Trials.",
        source_workbook_type=WorkbookType.TOPIC_CASE,
        grain=DataGrain.ONE_ROW_PER_CASE,
        required_fields=(CanonicalField.CASE_ID, CanonicalField.INITIAL_APPROVAL_DATE,
                          CanonicalField.PRIMARY_SOURCE),
    ),
    "total_case_count": MetricDefinition(
        metric_id="total_case_count",
        description="Distinct Case Number count from the all-case workbook, "
        "within the reporting period, excluding Clinical Trials.",
        source_workbook_type=WorkbookType.ALL_CASE,
        grain=DataGrain.ONE_ROW_PER_CASE,
        required_fields=(CanonicalField.CASE_ID, CanonicalField.INITIAL_APPROVAL_DATE,
                          CanonicalField.PRIMARY_SOURCE),
    ),
    "source_breakdown": MetricDefinition(
        metric_id="source_breakdown",
        description="Eligible distinct cases grouped by Derived-Primary-Source.",
        source_workbook_type=WorkbookType.TOPIC_CASE,
        grain=DataGrain.ONE_ROW_PER_CASE,
        required_fields=(CanonicalField.CASE_ID, CanonicalField.PRIMARY_SOURCE),
    ),
    "serious_case_count": MetricDefinition(
        metric_id="serious_case_count",
        description="Distinct Case Number with ANY topic-matching event row where "
        "Event Seriousness = Yes. Topic-specific EVENT-level rollup, not the "
        "general case-level Seriousness flag.",
        source_workbook_type=WorkbookType.TOPIC_DRUG_EVENT,
        grain=DataGrain.ONE_ROW_PER_CASE_EVENT,
        required_fields=(CanonicalField.CASE_ID, CanonicalField.EVENT_SERIOUSNESS),
    ),
    "fatal_case_count": MetricDefinition(
        metric_id="fatal_case_count",
        description="Distinct Case Number with ANY topic-matching event row where "
        "Death (Event) = Yes. Only explicit Yes qualifies.",
        source_workbook_type=WorkbookType.TOPIC_DRUG_EVENT,
        grain=DataGrain.ONE_ROW_PER_CASE_EVENT,
        required_fields=(CanonicalField.CASE_ID, CanonicalField.EVENT_DEATH),
    ),
    "event_pt_frequency": MetricDefinition(
        metric_id="event_pt_frequency",
        description="Event-row counts (not distinct case counts) per Event PT, "
        "with a separate distinct-case count shown alongside.",
        source_workbook_type=WorkbookType.TOPIC_DRUG_EVENT,
        grain=DataGrain.ONE_ROW_PER_CASE_EVENT,
        required_fields=(CanonicalField.CASE_ID, CanonicalField.EVENT_PT),
        distinct_by=None,
    ),
}


CASE_POPULATION_RULE = CasePopulationRule()
RELATEDNESS_RULE = RelatednessRule()
