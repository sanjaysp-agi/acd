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
uvicorn server.main:app --reload
```

Open the printed local URL, go to **Upload Documents**, upload the previous/approved
PBRER (.docx) and the current Excel exports (all-case, all-drug-event, and any
topic-specific case/drug-event pairs), enter the reporting start/end dates, and click
**Run pipeline**. A single run against the 10 real development files takes roughly
3-5 minutes, dominated by the two large all-case/all-drug-event exports (28k/63k rows) --
live per-agent progress streams to the page the whole time (see "Frontend: Streamlit ->
React" below).

## Running tests

```bash
pytest -m "not slow" -v     # 31 unit tests, ~7s, no real files required beyond the dev fixtures
pytest -m slow -v           # full end-to-end pipeline reproduction against real files
```

**Test results (this environment):** 31/31 fast tests pass; 1/1 slow test passes (full
pipeline reproduction -- see "Independent audit and remediation pass" below for what it
originally caught). The `slow` end-to-end test reproduces every benchmark figure in Part 6
of the original spec exactly (see below). After the first run, the file-hash analysis cache
(`llm/cache.py:AnalysisCache`) makes repeat slow runs against the same fixtures finish in
under a minute instead of ~4 minutes.

---

## What's actually implemented

| Deliverable | Status |
|---|---|
| Document Understanding Agent | ✅ real tool-calling loop, 10 predefined tools |
| Excel Understanding Agent | ✅ real tool-calling loop, 10 predefined tools (incl. `detect_date_formats`), parallelized across workbooks |
| Topic Mapping Agent | ✅ tool-calling wrapper around deterministic criterion-overlap scoring + independent all-event reconstruction/cross-validation (`processing/topic_reconstruction.py`) |
| Calculation Planning Agent | ✅ tool-calling wrapper around deterministic plan assembly + validation, incl. join-requirements/percentage-formula documentation per step |
| Deterministic Python calculation engine | ✅ pandas, no AI, reproduces every benchmark figure exactly, incl. serious/fatal percentages as a first-class calculated metric |
| Configurable metric registry | ✅ `config/metric_registry.py` |
| Dynamic schema mapping / data profiling | ✅ `tools/excel_tools.py` |
| Validation & reconciliation | ✅ `validation/` -- all 14 mandatory checks from Part 5 now formalized as `ValidationCheckResult`s in a single `ValidationReport` (`validation/input_validator.py`, `validation/mapping_validator.py`, `validation/calculation_validator.py`) |
| AWS Bedrock integration | ⚠️ implemented, **not verified live** -- see below |
| Cost controls / LLM-call caching | ✅ implemented; `llm/cache.py:AnalysisCache` now actually caches Document/Excel Agent analysis by file hash (cost-control item 6), and `PBRER_MAX_TOOL_ITERATIONS` is now wired into every agent instead of being dead config |
| React frontend (buildless, no npm), 10 pages + Run History | ✅ FastAPI + vendored React 18/htm, no bundler -- see "Frontend: Streamlit -> React" below; incl. manual topic-mapping correction/approval + re-run |
| Live Agent Execution & Traceability page | ✅ reads real persisted tool-call events, never simulated |
| Persisted structured execution logs | ✅ `observability/trace_store.py`, one JSONL per run |
| Calculation results / audit / report-ready / benchmark workbooks | ✅ `generation/` |
| Unit + integration tests | ✅ 31 fast + 23 slow (1 full pipeline + 22 frontend AppTest) |
| README / `.env.example` | ✅ this file |

## Independent audit and remediation pass

A follow-up audit (independent of the original build) re-verified every claim in this
README against the actual code, rather than trusting the prose. It found the core
architecture and benchmark reproduction were genuine, but several spec-required pieces
were partially implemented or silently dead code. All of the following were fixed and
re-verified against the full test suite + the real development fixtures:

- **Independent topic reconstruction/cross-validation** (prompt.md Part 2 Agent 3, lines
  378-394) did not exist at all. Added `processing/topic_reconstruction.py`: re-applies
  each topic's own Excel search criterion to the all-drug-event workbook's MedDRA
  columns and compares the reconstructed case set against the topic-specific export,
  recording discrepancies rather than silently resolving them. SMQ/CMQ criteria are
  explicitly never reconstructed (no membership column exists in a standard export).
  Surfaced in the Validation & Audit page and as mandatory check #13.
- **`ExecutionPlanStep.join_requirements` / `.percentage_formula`** existed in the schema
  but were never populated. Now part of the approved `MetricDefinition` in the metric
  registry and shown on the Calculation Review page.
- **Serious/fatal percentages were never actually calculated** as a result at all
  (`calculate_percentages` was imported into `pipeline.py` but never called). Added as a
  first-class `serious_fatal_percentages` metric with its own validation check
  (independent recomputation from the same inputs).
- **Rule H (mismatched case/event exports)** had date/CT-filter restriction logic but no
  check for event-workbook case IDs with no matching case record (or vice versa). Added
  `processing.topic_reconstruction.check_case_event_population_alignment` + a formal
  validation check.
- **Validation module** only had 2 of the 3 planned files and formalized 5 of the 14
  mandatory checks from Part 5. Added `validation/input_validator.py` (checks #1-4:
  input files present, workbook/sheet identification, header detection, footer
  detection) and `validation/mapping_validator.py` (checks #8, #12, #13), plus checks
  #10 (seriousness/death category sanity) and #11 (percentage recomputation) in
  `calculation_validator.py`. `assemble_validation_report()` now actually builds the
  `ValidationReport` schema that previously existed but was never constructed.
- **`detect_date_formats`** (one of the 11 Excel-agent tools required by Part 2) was
  defined but never invoked by anything. Wired into the per-workbook investigation loop
  to independently validate the mapped initial-approval-date column's format -- which
  also surfaced a real bug (it only recognized raw Python `int`/`float` inputs, but
  every real caller passes already-stringified profile samples) that's now fixed.
- **Topic Mapping page had no manual correction/approval** (prompt.md line 881) --
  only a read-only table. Added an `st.data_editor` with per-row workbook
  reassignment/approval and an "Apply corrections and re-run calculations" action that
  re-runs the Calculation Planning Agent + calculation engine + validation without
  re-running the (unchanged) Document/Excel Understanding Agents.
- **`PBRER_MAX_TOOL_ITERATIONS`** was defined in settings but never read by any agent
  (each one hardcoded its own iteration cap). Now every agent defaults to this setting.
- **`file_hash()`-based analysis caching** (cost-control item 6) existed as a helper
  function but was never called. Added `llm/cache.py:AnalysisCache` and wired it into
  both the Document and Excel Understanding Agents, keyed on file content hash + config
  version -- a second run against byte-identical inputs skips the agent loop entirely.
- A real correctness bug surfaced while building the reconstruction feature: the
  general-purpose prose term-splitter (`tools.topic_tools.extract_criterion_terms`)
  treats `" and "` as a conjunction between two criteria, which would silently fragment
  a genuine MedDRA term like "Confusion and disorientation" into two bogus terms when
  applied to the Excel's own exact criterion value. Added a separate exact-match
  splitter, `extract_excel_criterion_terms`, used only by the reconstruction path.

Everything above is covered by new tests (`tests/test_topic_reconstruction.py`,
`tests/test_date_format_tool_wiring.py`, `tests/test_frontend_pages.py`) and the full
suite (54 tests) passes, including the real end-to-end benchmark reproduction.

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
  `detect_footer_rows`, `profile_columns`, `detect_date_formats`, `extract_cover_page_criteria`,
  `classify_workbook`, `map_columns_to_schema`. `match_workbooks` is also a predefined
  Python tool but runs once across all per-workbook results (cross-workbook pairing
  isn't a per-workbook investigation step) rather than through the same per-workbook
  ToolSpec loop.
- **Topic Mapping Agent** (`tools/topic_tools.py`): `match_topics_to_workbooks`
  (term-overlap scoring between the PBRER's prose criteria and the Excel cover
  page's own criterion value). Independent reconstruction/cross-validation against the
  all-drug-event workbook (`processing/topic_reconstruction.py`) runs as a separate,
  deterministic step in the pipeline, not through this agent's tool-calling loop --
  consistent with Part 3's "deterministic calculation engine" being pure pandas.
- **Calculation Planning Agent** (`tools/plan_tools.py`): `build_execution_plan`
  (assembles + validates steps -- including join requirements and percentage formulas --
  against `config/metric_registry.py`; never invents a business rule).

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
- **No browser was available to manually click through the React UI either.** The
  backend (every `/api/runs/...` endpoint, including a full 10-file real-fixture run,
  the topic-mapping recompute endpoint, and all 4 downloads) was verified end-to-end
  with real HTTP requests against the real `input/` fixtures. The frontend's JS was
  syntax-checked (`node --check` against each module) and every static asset path was
  verified to resolve (200, correct `text/javascript` MIME type) against a running
  server, but `playwright install chromium` failed in this environment (the corporate
  network's TLS-intercepting proxy rejects `cdn.playwright.dev`'s certificate chain --
  the same category of restriction that motivated vendoring React/htm locally instead
  of loading them from a CDN at runtime). A manual browser click-through is still
  recommended before sign-off.

## Frontend: Streamlit -> React (buildless, no npm)

The original Streamlit frontend was replaced with React, without installing Node/npm
(disallowed by company policy) and without any bundler/build step:

- **Backend**: FastAPI (`server/`), installed via `pip install fastapi` --
  `uvicorn`/`starlette`/`python-multipart`/`anyio` were already present as transitive
  deps. One process (`uvicorn server.main:app`) serves both the JSON API under `/api`
  and the static frontend (`web/`).
- **Frontend**: React 18 + `htm` (JSX-free "tagged template" markup), loaded as plain
  UMD `<script>` tags vendored into `web/vendor/` -- no `node_modules`, no JSX
  compilation step. Works identically online or fully air-gapped.
- **Run execution is now async**: `POST /api/runs` returns immediately with a `run_id`;
  the pipeline runs on a background thread. `GET /api/runs/{id}/events` streams live
  trace events over Server-Sent Events (the browser's built-in `EventSource`, no
  library) so the Upload page shows real per-agent progress instead of one blocking
  3-5 minute spinner.
- **Full run persistence**: previously only a thin summary JSON survived a run,
  everything else lived only in the Streamlit session's memory. `observability/run_store.py`
  now persists every stage's full Pydantic output to `data/runs/{run_id}/result.json`
  and rehydrates it back into typed models on load -- this is what makes the new
  **Run History** page possible (reload any past run, not just the one just computed).
- `pipeline.recompute_from_topic_mapping` (lifted out of the old Streamlit page,
  behavior unchanged) backs the Topic Mapping page's manual correction/re-run flow.
- Two small UX additions fell out of rebuilding the UI anyway: a searchable filter on
  the Traceability page's live/historical event log, and color-coded row highlighting
  (not just a status badge) on the Validation page's benchmark comparison table.
- Deliberately **not** done as part of this migration (each is a standalone feature on
  top of the now-React app, not required for Streamlit->React parity): per-file upload
  validation feedback, an audit/e-signature trail for manual approvals, a single
  zip-bundle download, auth/roles, or an admin UI for `config/metric_registry.py`.

## Project structure

See `pipeline.py` for the single entry point tying all five stages together
(Document Agent → Excel Agent → Topic Mapping Agent → Calculation Planning Agent →
deterministic calculation engine → validation/benchmark). Directory layout follows
the standard structure (`config/`, `agents/`, `tools/`, `llm/`, `processing/`,
`validation/`, `observability/`, `generation/`, `models/`, `tests/`), plus two
frontend-facing additions from the React migration: `server/` (FastAPI app + routers)
and `web/` (the buildless React frontend: vendored React/htm, hand-written CSS, and
one `.js` module per page/component -- see "Frontend: Streamlit -> React" above).
