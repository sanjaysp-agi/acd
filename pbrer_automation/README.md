# PBRER Section 16.3 Automation -- POC

An AI-driven system that automates extraction, calculation and validation of the
numerical figures required for Section 16.3 of a PBRER (Periodic Benefit-Risk
Evaluation Report), built and validated against a real Sifrol (pramipexole) PBRER
cycle (2019-04-07 to 2024-04-06).

## Setup

```bash
cd pbrer_automation
pip install -r requirements.txt
cp .env.example .env   # defaults to local/deterministic mode; see "AWS Bedrock status" below
```

## Running the app

```bash
streamlit run app.py
```

Open the printed local URL, go to **Upload Documents**, upload the previous/approved
PBRER (.docx) and the current Excel exports (all-case, all-drug-event, and any
topic-specific case/drug-event pairs), enter the reporting start/end dates, and click
**Run pipeline**. A single run against the 10 real development files takes roughly
3-5 minutes, dominated by the two large all-case/all-drug-event exports (28k/63k rows).

## Running tests

```bash
pytest -m "not slow" -v     # 23 unit tests, ~15s, no real files required beyond the dev fixtures
pytest -m slow -v           # full end-to-end pipeline against real files, ~4 min
```

**Test results (this environment):** 23/23 fast tests pass. The `slow` end-to-end test
reproduces every benchmark figure in Part 6 of the original spec exactly (see below).

---

## What's actually implemented

| Deliverable | Status |
|---|---|
| Document Understanding Agent | ✅ real tool-calling loop, 9 predefined tools |
| Excel Understanding Agent | ✅ real tool-calling loop, 9 predefined tools, parallelized across workbooks |
| Topic Mapping Agent | ✅ tool-calling wrapper around deterministic criterion-overlap scoring |
| Calculation Planning Agent | ✅ tool-calling wrapper around deterministic plan assembly + validation |
| Deterministic Python calculation engine | ✅ pandas, no AI, reproduces every benchmark figure exactly |
| Configurable metric registry | ✅ `config/metric_registry.py` |
| Dynamic schema mapping / data profiling | ✅ `tools/excel_tools.py` |
| Validation & reconciliation | ✅ `validation/` |
| AWS Bedrock integration | ⚠️ implemented, **not verified live** -- see below |
| Cost controls / LLM-call caching | ✅ implemented (`llm/cache.py`), effectively idle since the app runs in local mode by default |
| Streamlit frontend, 10 pages | ✅ all 10 pages implemented and headlessly tested (`streamlit.testing.v1.AppTest`) |
| Live Agent Execution & Traceability page | ✅ reads real persisted tool-call events, never simulated |
| Persisted structured execution logs | ✅ `observability/trace_store.py`, one JSONL per run |
| Calculation results / audit / report-ready / benchmark workbooks | ✅ `generation/` |
| Unit + integration tests | ✅ 23 fast + 1 slow end-to-end |
| README / `.env.example` | ✅ this file |

## Which agents actually use LLM tool-calling, and in which mode

All four agents (`agents/document_agent.py`, `agents/excel_agent.py`,
`agents/topic_mapping_agent.py`, `agents/calculation_planner.py`) run through the
**same generic tool-calling loop** (`agents/base.py`), which is provider-agnostic:
it asks a `ToolCallingProvider` for the next step, executes the named tool if asked,
and records the real result. Two providers exist (`llm/provider.py`):

- `BedrockProvider` (`llm/bedrock_provider.py`): real AWS Bedrock Converse API tool
  calling. Implemented against the documented contract and unit-tested with a mocked
  client. **Not exercised against a live endpoint in this environment** -- see below.
- `LocalDeterministicProvider` (`llm/local_provider.py`): the default. Each agent
  supplies its own rule-based policy function that makes the *same* kind of decision
  an LLM would (which tool to call next, given what prior tool calls actually
  returned) via explicit Python branching instead of model inference. This is not a
  stub -- the Excel agent's policy genuinely branches on how many sheets a workbook
  has, whether a sheet looks like a cover page or a data table, and whether a column
  mapping came back low-confidence; the Document agent's policy genuinely branches on
  which heading-detection strategy succeeded and whether front-matter needed
  excluding. **Every run in this environment used local/deterministic mode** (see
  AWS Bedrock status).

## Which Python tools each agent invokes

- **Document Understanding Agent** (`tools/document_tools.py`, python-docx): `inspect_document_metadata`,
  `sample_paragraph_styles`, `detect_headings`, `exclude_front_matter_headings`,
  `reconstruct_section_numbers`, `locate_target_section`, `calibrate_section_numbers`,
  `extract_topic_subtree`, `extract_tables_near_heading`, `parse_topic_historical_metrics`.
- **Excel Understanding Agent** (`tools/excel_tools.py`, openpyxl + pandas): `discover_excel_files`,
  `inspect_workbook`, `inspect_sheet`, `detect_header_row`, `detect_data_region`,
  `detect_footer_rows`, `profile_columns`, `extract_cover_page_criteria`,
  `classify_workbook`, `map_columns_to_schema`, `match_workbooks`.
- **Topic Mapping Agent** (`tools/topic_tools.py`): `match_topics_to_workbooks`
  (term-overlap scoring between the PBRER's prose criteria and the Excel cover
  page's own criterion value).
- **Calculation Planning Agent** (`tools/plan_tools.py`): `build_execution_plan`
  (assembles + validates steps against `config/metric_registry.py`; never invents a
  business rule).

## What's deterministic, not AI-driven

The entire **calculation engine** (`processing/`) is pure pandas with no AI
involvement: date normalization, the fixed Clinical-Trials exclusion rule, case/event
eligibility filtering, serious/fatal event-level rollups, percentages, PT frequency.
Validation (`validation/`) and output generation (`generation/`) are likewise fully
deterministic. The AI layer's job stops at *understanding* (what sheet is this, what
column is this, which workbook matches which topic) -- it never computes a number or
writes a business rule.

## AWS Bedrock status

Local credential check (valid SSO-assumed role, account `728526885113`):

```
aws sts get-caller-identity   -> succeeds (ARN resolves correctly)
aws bedrock list-foundation-models --region eu-west-1   -> AccessDeniedException:
    "Authentication failed: Please make sure your API Key is valid."
aws bedrock list-foundation-models --region us-east-1   -> same error
```

That specific error wording (not a plain IAM permissions-denied message) suggests this
AWS org may gate Bedrock behind something other than standard IAM SigV4 (an API-key or
gateway layer) rather than a missing policy -- outside what this codebase can fix.
**Bedrock was never successfully invoked in this environment.** `BedrockProvider` is
fully implemented and ready; `PBRER_LLM_PROVIDER=bedrock` will surface the real error
rather than pretending success if you try it before this is resolved. Model invocation
count / token usage: N/A (zero real Bedrock calls made).

## Benchmark results achieved

Full end-to-end run against the real development fixtures (`tests/test_traceability.py::test_full_pipeline_reproduces_benchmark`, marked `slow`):

| Metric | Expected (PBRER) | Calculated | Status |
|---|---:|---:|---|
| Total post-marketing cases | 3,651 | 3,651 | ✅ match |
| All cases -- Spontaneous | 3,272 | 3,272 | ✅ match |
| All cases -- Other Studies | 379 | 379 | ✅ match |
| ICD topic cases | 242 | 242 | ✅ match |
| ICD serious cases | 55 | 55 | ✅ match |
| ICD fatal cases | 1 | 1 | ✅ match |
| ICD -- Spontaneous / Other Studies | 225 / 17 | 225 / 17 | ✅ match |
| Hallucinations topic cases | 270 | 270 | ✅ match |
| Hallucinations serious cases | 98 | 98 | ✅ match |
| Hallucinations fatal cases | 1 | 1 | ✅ match |
| Hallucinations -- Spontaneous / Other Studies | 224 / 46 | 224 / 46 | ✅ match |
| Augmentation/RLS topic/serious/fatal | 105 / 31 / 0 | 105 / 31 / 0 | ✅ match (document's own figures, not in the original Part 6 table) |

All 22 calculated metrics in this run passed validation (`validation_status="verified"`)
-- zero failures, zero unparseable dates, zero duplicate case IDs.

### Discrepancy figures cited in the original spec -- re-verified, corrected

The spec referenced "ICD serious event rows 76 vs 77" and a "Hallucinations case-level
118 vs event-level 98" discrepancy, attributed to the development traceability HTML.
Re-reading that HTML directly: it documents **ICD only**, and the real figures are
**76 event rows vs. 55 distinct serious cases** (the row-count-vs-case-count bug), and
separately **82 (case-level Seriousness flag) vs. 55 (correct event-level rollup)**.
No "77" and no Hallucinations 118-vs-98 figures exist in that document. The underlying
methodology point -- use the topic-specific **event-level** rollup, never the general
case-level flag -- is correct and is what this engine implements
(`processing/event_calculator.py`); the specific numbers in the spec should be treated
as a paraphrase-drift from memory, not ground truth.

## Unverified / no-benchmark topics

- **Cardiac failure** (16.3.1.1): has an Excel export, but the current PBRER carries
  **no numeric data for it at all** (downgraded to "not important" in 2019; current
  figures: 7 cases, 7 serious, 0 fatal, calculated but `unverified` -- there is nothing
  to compare against).
- **Dopamine Agonist Withdrawal Syndrome** (16.3.1.4), **Dystonia** (16.3.2.1),
  **Suicide-related behaviour** (16.3.2.2): the PBRER has full historical figures for
  these, but **no Excel export was provided** for them (file-number gap 05/06) -- the
  Topic Mapping Agent correctly reports them as unmatched rather than guessing.

## Methodology rules requiring company confirmation (never silently assumed)

- **Case population**: Invalid AE case / Invalid non-AE case / Non-AE case records are
  currently *included* (matches the benchmark), per `config/metric_registry.
  CasePopulationRule` -- flagged as requiring SOP confirmation, not treated as final.
- **Relatedness filtering**: NOT applied (`RelatednessRule.apply_relatedness_filter =
  False`) -- independent testing noted this would change Hallucinations' serious count
  from 98 to 95; kept disabled because 98 is what matches the actual PBRER.
- **Clinical Trials exclusion**: the only genuinely fixed, non-configurable rule in the
  system (`config.metric_registry.CLINICAL_TRIALS_EXCLUSION_ENABLED`) -- the *value
  recognition* (which primary-source string means "Clinical Trials") is a dynamic
  pattern match, not a hardcoded literal, since a different tenant's export could
  phrase it differently.

## Known architectural limitations (honest, not hidden)

- **No tenant-specific shape is hardcoded.** The 10 real files in `input/` all happen
  to share one export template (header always row 6, 2 sheets, identical columns) --
  that uniformity was treated as a property of *these fixtures*, never baked into the
  detectors. `tests/test_header_detection.py` includes synthetic workbooks with the
  header at row 6 and row 10 to prove this.
- **Re-reading cost on large files.** Each tool call on a workbook (inspect, detect
  header, detect footer, profile columns) independently re-opens the file -- this is
  the architectural price of genuinely independent, auditable tool calls, but it means
  the 63k-row all-drug-event export gets read from disk several times across a run.
  Mitigated with `read_only=True` openpyxl loads and a raw-XML merge-range reader
  (`tools/excel_tools._fast_merged_ranges`) instead of openpyxl's normal full-document
  parse, which cut a single large-file pass from 60s+ to ~15s. A production version
  could cache a parsed-sheet object across calls within one workbook's investigation;
  not done here to keep each tool's contract (and its trace entry) fully independent.
- **No browser was available to manually click through the UI.** All 10 Streamlit
  pages were verified headlessly with `streamlit.testing.v1.AppTest` (both with no run
  yet, and with a real completed pipeline result injected into session state) -- this
  caught and fixed a real bug (the benchmark-workbook generator crashing on dict-valued
  metrics). A manual browser click-through is still recommended before sign-off.

## Minor known cosmetic issue

The Validation & Audit page's benchmark table mixes scalar and stringified
dict/list values in one column; pyarrow logs a conversion warning and Streamlit
auto-recovers (confirmed via `AppTest`: page still renders with no exception). Not
fixed further since it's display-only and doesn't affect any calculated figure.

## Project structure

See `pipeline.py` for the single entry point tying all five stages together
(Document Agent → Excel Agent → Topic Mapping Agent → Calculation Planning Agent →
deterministic calculation engine → validation/benchmark). Directory layout follows
the standard structure (`config/`, `agents/`, `tools/`, `llm/`, `processing/`,
`validation/`, `observability/`, `generation/`, `models/`, `frontend/`, `tests/`).
