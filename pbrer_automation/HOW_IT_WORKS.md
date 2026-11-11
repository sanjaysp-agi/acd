# PBRER Section 16.3 Automation — How It Works, and Why It's a Good POC

This document explains the system in plain terms: what it automates, how the
agents are structured, how the LLM is actually wired in, and what makes this
a credible proof of concept rather than a demo that only works on a happy
path. For the full technical reference see `README.md`; this file is the
narrative version.

## 1. What problem this solves

A PBRER (Periodic Benefit-Risk Evaluation Report) Section 16.3 requires a
safety team to take raw case-level Excel exports from a safety database and
turn them into a set of audited figures per safety topic: case counts,
serious/fatal counts, percentages, and source breakdowns — cross-checked
against the previous report. Today that's manual, slow, and error-prone
(the dev fixtures this POC is built against contain a real row-count-vs-
case-count bug that a human reviewer introduced in production).

This system automates the *understanding* work (which file is which, which
column means what, which topic maps to which workbook) with AI, and keeps
every actual number calculation in deterministic, auditable Python — never
decided by a model.

## 2. The seven-stage pipeline

```
Document Agent ─┐
                 ├─→ Topic Mapping Agent → Calculation Planning Agent
Excel Agent ─────┘         → deterministic calculation engine
                            → Extraction Review Agent
                            → validation/benchmark comparison
                            → AI Scoring Agent
```

Document Agent and Excel Agent now run **concurrently** (see §3a) — neither
depends on the other's output, only Topic Mapping Agent (next) needs both.

1. **Document Understanding Agent** reads the *previous/approved* PBRER
   (`.docx`) and finds Section 16.3. Tool sequence (one real run,
   `run_f93670d6ceda`): `detect_headings` → `exclude_front_matter_headings`
   → `reconstruct_section_numbers` → `locate_target_section` →
   `calibrate_section_numbers` → `extract_topic_subtree`, then for each
   leaf topic under 16.3: `extract_tables_near_heading` +
   `parse_topic_historical_metrics`. Output: each topic's historical
   figures (case count, serious/fatal count, source breakdown) and its
   prose search criteria, exactly as published in the last report.
2. **Excel Understanding Agent** investigates every uploaded workbook —
   `inspect_workbook` → `inspect_sheet` → `detect_header_row` →
   `detect_data_region` → `detect_footer_rows` → `profile_columns` →
   `detect_date_formats` → `extract_cover_page_criteria` →
   `classify_workbook` → `map_columns_to_schema`. Runs these steps for all
   10 workbooks **in parallel** (`max_workers=10`). Output: for every
   workbook, which sheet holds the data, where the real rows start/end,
   what each column means (case ID, seriousness, MedDRA term, dates,
   etc.), and the workbook's own stated search criterion.
3. **Topic Mapping Agent** calls `match_topics_to_workbooks` — compares
   each PBRER topic's prose criteria (from stage 1) against each
   workbook's stated criterion (from stage 2) and scores the match. It
   will explicitly report "no match found" rather than force a weak guess
   (confirmed in a real run: 3 topics with zero overlap were correctly
   left unmatched instead of being assigned a wrong workbook). It then
   independently *reconstructs* each matched topic's case set from the
   all-drug-event export and cross-checks it against the topic-specific
   export, flagging mismatches instead of silently trusting either side.
4. **Calculation Planning Agent** calls `build_execution_plan` — for every
   *matched* topic, documents which columns, which join, and which formula
   produce each of 6 metrics (case count, source breakdown, serious count,
   fatal count, PT frequency, serious/fatal %), validated against a
   configurable metric registry so no business rule is invented on the
   fly. This stage decides *the recipe*; no number is computed here.
5. **Deterministic calculation engine** (`processing/`) is pure pandas —
   date normalization, the Clinical-Trials exclusion rule, case/event
   eligibility filtering, serious/fatal rollups, percentages. **No AI
   involvement at all, no tool-calling loop, no trace events of its own.**
   This is the part that actually produces every number in the report,
   using the recipe from stage 4.
6. **Extraction Review Agent** cross-checks stage 1's historical figures
   against stage 5's current-period figures for completeness — e.g. it
   flags when a topic has historical data but no current-period
   calculation (exactly what catches a topic whose workbook is missing
   from the upload, like Dopamine agonist withdrawal syndrome in the dev
   fixtures).
7. **AI Scoring Agent** runs last, after the validation report is
   assembled. Calls `compute_baseline_ai_scores` then `report_ai_scores` —
   assigns a confidence score (0–1) to every calculated metric, citing
   exactly which workbook/sheet it came from and whether a historical
   benchmark exists to check it against. `ai_score_report.mode` on the
   finished run records whether this (and every other agent in the run)
   actually ran on `"bedrock"` or fell back to `"local_deterministic"` —
   the single field that proves, after the fact, whether a run was really
   AI-driven.

Interleaved with stage 6/7, a **validation/benchmark stage** runs 14+
mandatory checks (file presence, header/footer detection, mapping
confidence, case/event population alignment, percentage recomputation,
etc.) and — when historical figures exist — compares every calculated
figure against the real PBRER's published numbers.

## 3. How the agents actually work (the tool-calling loop)

Every "understanding" agent (Document, Excel, Topic Mapping, Calculation
Planning) runs through the exact same generic loop
(`agents/base.py:ToolCallingAgent`), regardless of what's deciding the next
step:

1. Ask the **provider** "given what we've learned so far, what's the next
   move?"
2. If the provider says "call tool X with these arguments," the agent
   executes that *real, predefined* Python tool (never arbitrary code —
   the provider can only pick from a fixed tool list) and records the
   result.
3. Feed the tool's real result back into the conversation.
4. Repeat until the provider says "I'm done" or a safety iteration cap is
   hit.

Every single tool call is written to a persisted trace log
(`observability/trace_store.py`) — this is what the frontend's "Live Agent
Execution & Traceability" page reads from. Nothing shown there is
simulated; it's the literal record of what each agent actually did.

### 3a. Document Agent + Excel Agent run concurrently

`pipeline.py:run_full_pipeline` fans the two stages out on a thread pool and
joins before Topic Mapping Agent starts:

```python
with ThreadPoolExecutor(max_workers=2) as pool:
    doc_future = pool.submit(doc_agent.run, run_id, docx_path)
    excel_future = pool.submit(excel_agent.run, run_id, excel_dir)
    document_structure = doc_future.result()
    workbook_inventory = excel_future.result()
```

This is safe because the two agents read disjoint inputs and never touch
each other's state; the only shared resource is the trace log, which was
already lock-protected (`observability/trace_store.py`) since Excel
Agent's own internal per-workbook fan-out already wrote to it from
multiple threads. Confirmed working in a real run: both agents'
`agent_started` events land within milliseconds of each other, and their
tool calls appear genuinely interleaved in the trace.

**What this did *not* do**, measured on a real Bedrock run
(`run_f93670d6ceda`): Excel Agent (134 tool calls across 10
already-parallelized workbooks) finished in 308.6s; Document Agent (27
tool calls, run as a single sequential conversation) took 447.9s —
*longer*, despite 5x fewer calls, because every one of its round trips
pays real network latency serially. Document Agent is now the slower of
the two stages under live Bedrock latency — the opposite of what a
local-deterministic-mode timing test suggested, because local mode has no
network latency to expose the difference between "parallelized tool
calls" and "sequential tool calls." The next targeted speedup (not yet
implemented) would be fanning out Document Agent's per-leaf-topic
extraction (`extract_tables_near_heading` + `parse_topic_historical_metrics`
for each of ~10 topics) across a thread pool the same way Excel Agent
already fans out across workbooks — those calls are independent of each
other once the heading structure is known.

### Two interchangeable providers, same loop, same tools

- **`LocalDeterministicProvider`** — each agent supplies a rule-based
  Python policy function that makes the same *kind* of decision an LLM
  would (which tool to call next, given what the previous tool actually
  returned), via explicit branching instead of model inference. This is
  the default, and it's not a stub: the Excel agent's policy genuinely
  branches on sheet count, cover-page vs. data-table shape, and low-
  confidence column mappings.
- **`BedrockProvider`** — the same loop, but the "what's next" decision
  comes from a real AWS Bedrock Converse API call to Claude. The model
  sees the same system prompt, the same conversation history, and the same
  tool list as the local policy would, and picks a tool the same way.

Because both providers implement the identical `ToolCallingProvider`
interface and drive the identical `ToolCallingAgent` loop, switching
between them is a one-line config change (`PBRER_LLM_PROVIDER=local` vs.
`bedrock`) with **zero change to the agents, the tools, or the downstream
pipeline.** That's what makes this a real POC for AI-driven understanding
rather than an AI *demo* bolted onto a hardcoded parser.

## 4. What's deterministic vs. what's AI-driven — and why that split matters

| Layer | AI? | Why |
|---|---|---|
| "What sheet is this, what does this column mean, which topic does this workbook belong to" | Yes | This is genuinely ambiguous, judgment-requiring work — exactly what LLMs are good at and rigid parsers aren't. |
| "How many serious cases, what percentage, what's the PT frequency" | **No — pure pandas** | A calculated number must be reproducible, auditable, and never hallucinated. The AI layer's job stops at *understanding*; it never computes a figure or invents a business rule. |

This split is the core design decision, and it's why the system's benchmark
reproduction (see below) is meaningful rather than circular — the AI only
ever decides *where to look*, the math is the same whether the "where to
look" decision came from a model or a human.

## 5. Proven correctness: the benchmark

Run against the real Sifrol (pramipexole) PBRER development fixtures
(10 real files, 28k/63k-row exports), the deterministic engine reproduces
every benchmark figure in the original spec **exactly**:

| Metric | Expected | Calculated |
|---|---:|---:|
| Total post-marketing cases | 3,651 | 3,651 |
| ICD topic/serious/fatal cases | 242 / 55 / 1 | 242 / 55 / 1 |
| Hallucinations topic/serious/fatal cases | 270 / 98 / 1 | 270 / 98 / 1 |
| Augmentation/RLS topic/serious/fatal | 105 / 31 / 0 | 105 / 31 / 0 |

22 calculated metrics, zero validation failures, zero unparseable dates,
zero duplicate case IDs.

This proves the deterministic engine + understanding-agent pipeline is
correct for a real, previously-published report — independent of which
provider (local or Bedrock) made the understanding decisions.

## 6. Cost and safety controls (why this doesn't run away)

- **Per-run invocation cap** (`PBRER_MAX_INVOCATIONS_PER_RUN`) — hard stop
  on total model calls in one run.
- **Per-agent tool-iteration cap** (`PBRER_MAX_TOOL_ITERATIONS`) — a
  runaway tool-calling loop terminates instead of looping forever.
- **File-hash-keyed analysis cache** (`llm/cache.py:AnalysisCache`) — a
  second run against byte-identical input files skips the agent loop (and
  every model call it would have made) entirely. A repeat run against the
  same fixtures finishes in under a minute instead of ~4 minutes.
- **No tool is ever invented.** Both providers can only select *by name*
  from a fixed, predefined, typed Python tool list — a model deciding to
  call a tool can never execute arbitrary code.

## 7. Observability — nothing is a black box

- Every tool call, every agent start/completion, and every validation check
  is persisted to a structured JSONL trace per run
  (`data/runs/<run_id>.jsonl`).
- The React frontend's Traceability page reads that same file — there is
  no separate "demo narrative" path.
- `ai_score_report.mode` on every completed run records whether that run
  actually used `"bedrock"` or `"local_deterministic"` — so it's always
  possible to tell, after the fact, whether a given run's understanding
  decisions came from a real model or the rule-based fallback.
- Full run results (document structure, workbook inventory, topic mapping,
  execution plan, metric results, benchmark report, validation report) are
  persisted per run and reloadable from the Run History page — not just a
  one-time summary that disappears when the session ends.

## 8. Live AWS Bedrock status — confirmed working end-to-end

Three real issues were found and fixed while verifying live Bedrock calls
in this environment, worth recording because they're exactly the kind of
gap a lower-effort POC would have missed:

1. **`.env` was never actually loaded.** The app read every setting from
   `os.environ` directly with no `python-dotenv` call anywhere, so editing
   `.env` silently did nothing — the app would fall back to
   `PBRER_LLM_PROVIDER=local`'s default with no warning. A full run even
   *completed successfully* this way, because local mode reproduces the
   benchmark on its own — the failure was silent, not loud. Fixed by
   adding `load_dotenv()` at the top of `config/settings.py` (explicit
   path, and it never overrides an already-exported real environment
   variable).
2. **A blank `AWS_PROFILE=` in `.env` broke boto3 outright.** Once `.env`
   was actually loaded, an empty `AWS_PROFILE` value is not the same as an
   *unset* one to boto3 — it tried to load a profile literally named `""`
   and failed with `The config profile () could not be found`. Fixed by
   stripping the variable from `os.environ` when it's blank.
3. **`temperature` is rejected by the newer Bedrock Claude model.** The
   Converse request hardcoded a `temperature` parameter; current-generation
   Claude Sonnet models reject that parameter outright as deprecated, even
   at its default value. Fixed by removing it from the inference config.

**After all three fixes, a complete run went through real Bedrock
end-to-end and succeeded** (`run_f93670d6ceda`):

- `ai_score_report.mode: "bedrock"` — every agent in the run, not just one,
  ran on the real model.
- Benchmark figures matched the published PBRER exactly off AI-driven
  understanding: Impulse control disorders 242/55/1 (case/serious/fatal),
  Hallucinations and confusion 270/98/1, etc.
- The model's own structured output is visibly real reasoning, not
  templated text — e.g. Topic Mapping Agent's completion summary flagged
  a Cardiac failure match as "plausible but unverified" at confidence
  0.50, and explicitly declined to force-match three topics with zero
  term overlap rather than guessing.
- `validation_report.overall_status: "warning"` on that same run is
  expected, not a bug — it correctly flags the same known gaps the
  original spec documents (3 topics have no matching workbook in the dev
  fixture set at all).

This closes out what was previously an open question — Bedrock access in
this account/region works, the request shape issues above were the only
blockers, and the full 7-stage pipeline (not just a single agent call) now
runs on a real model start to finish.

## 9. Why this is a good POC, specifically

- **It doesn't hide the hard part.** The AI layer is scoped to exactly the
  ambiguous judgment calls (sheet/column/topic identification) that
  genuinely need it, and nothing else — the deterministic engine proves
  the *math* was never the thing being tested.
- **It's provider-agnostic by construction**, not by accident — the same
  loop, same tools, same trace format run whether the decision-maker is a
  rule-based policy or a real model, so switching to Bedrock required zero
  changes to the pipeline itself.
- **It's independently auditable.** Every tool call is traced, every run
  is reloadable, and the benchmark comparison is against a real published
  report with a real known discrepancy case (the ICD serious-event
  row-vs-case bug) — this isn't a curated example built to always pass.
- **It fails loudly, not silently.** `BedrockProvider` never catches and
  swallows an error to fall back to local mode — if Bedrock is
  misconfigured or blocked, the run fails with the real underlying
  exception message, which is exactly how the three bugs above were found
  and fixed instead of going unnoticed.
- **Cost and runaway-loop controls are real, not aspirational** — caps and
  caching are wired into the actual agent loop, not just documented as a
  future improvement.
