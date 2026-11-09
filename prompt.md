# MASTER PROMPT: BUILD AN AI-DRIVEN PBRER SECTION 16.3 AUTOMATION POC

Act as a senior AI engineer, Python architect, pharmacovigilance data analyst and full-stack developer.

Your task is to build a complete, runnable Proof of Concept (POC) for an AI-driven system that automates the extraction, calculation and validation of numerical information required for Section 16.3 of a PBRER (Periodic Benefit-Risk Evaluation Report).

I do not want just an architecture, explanation, project skeleton or code snippets. I want an actual working application with:

- Autonomous AI agents.
- Python-based document and Excel extraction tools.
- Dynamic data profiling and schema discovery.
- AI-assisted topic mapping and calculation planning.
- Deterministic calculation and validation engines.
- A professional Streamlit frontend.
- Agent-by-agent execution traceability displayed in the frontend.
- AWS Bedrock integration where access is available.
- Tests, documentation and downloadable outputs.

The system must adapt to changing filenames, sheet names, headers, data formats, safety topics and reporting intervals.

**Core principle: AI agents investigate and understand the files by invoking Python tools. Python libraries perform actual extraction and calculations. The frontend displays the actual execution and generated outputs.**

---

# PART 1 – UNDERSTAND THE AVAILABLE FILES

First inspect the current workspace and identify all available reference files.

The expected development files include:

1. Previous/approved SIFROL PBRER Word document.
2. PBRER traceability HTML.
3. All-case Excel export.
4. All-drug-event Excel export.
5. Topic-specific case Excel exports.
6. Topic-specific drug-event Excel exports.

Use the actual filenames and file structures discovered in the workspace. Do not assume filenames will always be identical.

### Important: Development references versus application inputs

During POC development, you will be given the PBRER traceability HTML.

Study it to understand:

- Existing filtering methodology.
- Search criteria.
- Reporting date selection.
- Primary-source exclusions.
- Case-level versus event-level counting.
- Serious and fatal case calculations.
- Topic-specific calculations.
- Other numerical calculations documented in it.

Use the traceability HTML to understand the existing methodology and compare it with the actual Excel records.

The traceability HTML is a DEVELOPMENT-ONLY REFERENCE.

**It must never be a required input in the actual application.**

Do not add a traceability HTML upload field to the frontend.

Translate the confirmed methodology into a structured, configurable metric registry.

The methodology in the HTML must not automatically be treated as an approved company SOP. Identify assumptions requiring confirmation.

### Source-of-truth hierarchy

Maintain a clear distinction:

| Reference | Purpose |
|---|---|
| Previous/approved PBRER | Section numbering, headings, historical figures and reporting structure |
| Development-only traceability HTML | Understand and investigate existing calculation methodology |
| Latest Excel exports | Source of new calculated figures |
| Approved metric registry | Controlled calculation rules for the application |
| User-provided reporting dates | Current reporting interval |

Never copy historical PBRER figures and present them as newly calculated results.

Do not modify or overwrite original source files.

---

# PART 2 – IMPLEMENT A TOOL-DRIVEN MULTI-AGENT ARCHITECTURE

This project must be genuinely AI-driven.

Do not implement a fixed Python pipeline and simply label each Python module as an AI agent.

The AI agents must be able to select and invoke predefined Python tools based on the information they have discovered.

Implement a tool-calling workflow.

The pattern should be:

1. Agent receives its task and available tool descriptions.
2. Agent decides which inspection or extraction tool to invoke.
3. Python executes that tool using the appropriate library.
4. Tool returns structured results.
5. Agent interprets the results.
6. Agent decides whether further inspection is needed.
7. Agent generates a structured output.
8. That output is passed to the next agent.

Use supported tool-calling capabilities of the configured LLM provider.

All tools must be predefined, typed and restricted.

**Do not allow the LLM to generate arbitrary Python code, execute arbitrary shell commands or directly manipulate source files.**

The agent can decide which safe Python tool to use, but the actual implementation of that tool must be written and validated by the application.

## Agent 1 – Document Understanding Agent

**Objective:** Understand the previous PBRER and extract the complete Section 16.3 structure.

Use:

- `python-docx`
- PyMuPDF only if PDF support is required.

Create reusable Python tools for:

- Document metadata inspection.
- Paragraph extraction.
- Table extraction.
- Heading detection.
- Section extraction.
- Surrounding-content inspection.
- Topic hierarchy reconstruction.

The AI agent should select the tools required to understand the document.

Extract:

- Section numbers.
- Section headings.
- Topic names.
- Topic hierarchy.
- Topic ordering.
- Numerical figures reported under each topic.
- Relevant reporting terminology and structure.

The agent should generate structured JSON.

Example:

```json
{
  "section": "16.3",
  "title": "Evaluation of Risks and New Information",
  "topics": [
    {
      "section_number": "16.3.1.3",
      "topic_name": "Hallucinations and confusion",
      "historical_metrics": {}
    }
  ]
}
```

The complete catalogue must be extracted from the actual PBRER. Do not hardcode example topic headings as the full topic list.

Where a report heading is ambiguous, inspect its surrounding paragraphs and table structure.

**Output:** `document_structure.json`

---

## Agent 2 – Excel Understanding Agent

**This is one of the most important agents in the POC.**

Its task is to autonomously investigate every uploaded workbook and understand what information it contains.

It must not depend on:

- Fixed filenames.
- Fixed sheet names.
- Headers always starting on row 1.
- Fixed column names.
- Fixed date formats.
- A fixed number of worksheets.

The Excel Agent should use Python tools to investigate the raw Excel files.

### A. Python tools available to the agent

Implement these reusable tools:

| Tool | Library | Responsibility |
|---|---|---|
| `discover_excel_files()` | pathlib, os | Discover uploaded Excel workbooks |
| `inspect_workbook()` | openpyxl | Inspect workbook structure and sheet names |
| `inspect_sheet()` | openpyxl | Inspect an individual worksheet |
| `detect_header_row()` | openpyxl, pandas | Find the real column-header row |
| `detect_data_region()` | pandas | Identify actual data boundaries |
| `detect_footer_rows()` | pandas, custom logic | Identify report footers and summary rows |
| `profile_columns()` | pandas | Profile column types and values |
| `detect_date_formats()` | pandas, custom logic | Identify possible date formats |
| `extract_cover_page_criteria()` | openpyxl | Extract topic search criteria |
| `classify_workbook()` | Python + AI | Identify workbook purpose |
| `map_columns_to_schema()` | Python + AI | Map changing headers to canonical fields |
| `match_workbooks()` | Python + AI | Associate related case and event workbooks |

You can reorganize these functions if necessary, but all the capabilities must be implemented.

### B. Dynamic Excel inspection

Real Excel exports may contain:

- Report metadata above the actual table.
- Headers starting at row 6 or another position.
- Merged cells.
- Blank rows.
- Footer information after the records.
- Numeric dates stored as floats, such as `20190407.0`.
- Missing or unexpected values.
- Different sheet names.
- Additional columns.

Implement dynamic header detection using candidate-row scoring, detected column patterns and workbook context.

Do not simply hardcode:

```python
pd.read_excel(file, header=5)
```

The system must first identify the correct header row.

Footer detection must not remove valid records. Every removed row must be accounted for in the processing audit.

### C. Autonomous inspection workflow

The Excel Agent must be capable of requesting additional inspection when its initial findings are insufficient.

Example:

- First, discover the workbook.
- Then inspect its available sheets.
- Discover an unfamiliar sheet name.
- Inspect that particular sheet.
- Detect the header row.
- Profile its columns.
- Inspect the cover page.
- Identify its search criteria.
- Classify its data grain.
- Generate its final workbook description.

The sequence must be driven by the agent's observations rather than a fixed assumption about file structure.

### D. Data profiling

Python must create compact data profiles for relevant columns.

Include:

- Column names.
- Detected types.
- Sample values, appropriately redacted.
- Unique categorical values.
- Missing-value counts.
- Invalid-value counts.
- Possible date formats.
- Duplicate counts.
- Data grain.

Example:

```json
{
  "column": "Derived-Initial-Approval-Date-(YYYYMMDD)",
  "detected_type": "numeric_date",
  "sample_values": [
    "20190407.0",
    "20200115.0",
    "20240325.0"
  ],
  "possible_format": "YYYYMMDD"
}
```

Normalize values such as `20190407.0` into `2019-04-07` using validated Python code.

Unknown, masked, not asked, blank and no-information values must remain distinct.

### E. Dynamic workbook classification

Classify each workbook into an appropriate category:

- All-case workbook.
- Topic-specific case workbook.
- All-drug-event workbook.
- Topic-specific drug-event workbook.
- Other/unclassified workbook.

Use workbook contents, sheet names, cover-page criteria, column profiles and filename clues.

Filenames are supporting evidence, not the sole basis for classification.

### F. Canonical schema mapping

Create a configurable canonical schema:

- `case_id`
- `initial_approval_date`
- `primary_source`
- `case_seriousness`
- `event_pt`
- `event_hlt`
- `event_hlgt`
- `event_soc`
- `event_seriousness`
- `event_death`

The agent should map actual workbook columns to these canonical fields.

For example:

`Derived-Initial-Approval-Date-(YYYYMMDD)`

and

`Initial Approval Date`

may represent the same semantic field.

However, proposed mappings must be validated against:

- Column values.
- Data types.
- Workbook context.
- The field's intended meaning.

Low-confidence or conflicting mappings must be marked for review.

**Output:** `workbook_inventory.json`

Include workbook name, type, sheets, criteria, columns, data grain, mapped fields, mapping confidence and any warnings.

---

## Agent 3 – Topic Mapping Agent

**Objective:** Connect the Document Agent's topic catalogue with the Excel Agent's workbook inventory.

For example:

Excel workbook:

`04_case_Hallucinations and confusion_CSMR.xlsx`

Corresponding PBRER heading:

`16.3.1.3 Hallucinations and confusion`

Extract the exact search criteria from the Excel cover page.

Support criterion types such as:

- PT
- HLT
- HLGT
- SOC
- SMQ
- CMQ

Keep the following separately:

- PBRER section number.
- PBRER heading.
- Original Excel search criterion.
- Criterion type.
- Associated case workbook.
- Associated drug-event workbook.

Do not assume that a report heading and an Excel search term have identical wording.

### Topic reconstruction and cross-validation

The all-drug-event workbook may already contain MedDRA fields such as SOC, HLGT, HLT and PT.

Where sufficient information exists:

1. Extract the search criteria from the topic workbook.
2. Apply these criteria to the all-event dataset.
3. Reconstruct matching topic events.
4. Compare the matching case numbers and event counts with topic-specific exports.
5. Record any discrepancies.

Use topic-specific exports as primary inputs for the initial POC.

Use all-event reconstruction as an independent cross-validation process.

Do not assume SMQ/CMQ criteria can be reproduced if the required information is unavailable.

Ambiguous mappings and mismatched case/event workbooks must be sent for review.

**Output:** `topic_mapping.json`

---

## Agent 4 – Calculation Planning Agent

This agent prepares a structured execution plan using:

- Document structure.
- Workbook inventory.
- Data profiles.
- Topic mappings.
- Approved metric definitions.

It should determine which validated Python functions must be used for each metric.

Create Pydantic schemas for the execution plan.

The plan should identify:

- Section number and topic.
- Source workbook and sheet.
- Canonical fields.
- Actual mapped column names.
- Date field and format.
- Reporting dates.
- Source exclusion.
- Metric definition.
- Case-level or event-level grain.
- Deduplication logic.
- Join requirements.
- Percentage formula.

The AI may propose mappings and processing plans. The application must validate them against approved definitions before execution.

**Do not allow the LLM to invent new business rules or generate executable calculation code.**

**Output:** `execution_plan.json`

---

# PART 3 – DETERMINISTIC PYTHON CALCULATION ENGINE

Implement the following calculation rules using predefined Python functions and Pandas.

Keep case-level and event-level data separate.

## A. Reporting date

For the currently validated SIFROL example:

`Derived-Initial-Approval-Date-(YYYYMMDD)`

The application must dynamically identify and validate the appropriate date column against the metric registry.

Normalize numeric date values and validate actual dates.

Both reporting-period boundaries are inclusive.

Do not silently substitute another date column.

If the date column is ambiguous, show the alternatives and require review.

## B. Primary-source exclusion

For the current POC methodology, exclude:

`Derived-Primary-Source = Report from study-Clinical Trials`

Include other source categories unless an additional approved rule specifies otherwise.

Do not hardcode a whitelist of source values.

## C. Topic case count

Source: Matching topic-specific case workbook.

- Apply reporting-period filter.
- Exclude Clinical Trials.
- Count distinct `Case Number`.

## D. Total case count

Source: All-case workbook.

Apply the same applicable filters.

Count distinct `Case Number`.

## E. Source breakdown

Group eligible distinct cases by:

`Derived-Primary-Source`

Preserve newly discovered source categories.

## F. Serious cases

Source: Matching topic-specific drug-event workbook.

Use:

`Event Seriousness = Yes`

Count distinct `Case Number`.

A case with multiple serious matching event rows counts once.

Do not use general case-level seriousness as a substitute for topic-specific event seriousness.

## G. Fatal cases

Source: Matching topic-specific drug-event workbook.

Use:

`Death (Event) = Yes`

Count distinct `Case Number`.

Only explicit Yes qualifies as fatal under the current example methodology.

Keep No, No Information and blank values distinct.

## H. Case and event relationship

Where required, restrict event calculations to the eligible topic case-number set.

Check for:

- Case IDs with no matching case record.
- Duplicate case records.
- Event records outside the eligible reporting period.
- Mismatched topic case and event exports.

Document the exact join and filtering procedure.

## I. Percentages

Serious percentage:

Serious distinct cases / Topic distinct cases × 100.

Fatal percentage:

Fatal distinct cases / Topic distinct cases × 100.

Use consistent rounding.

## J. Relatedness

For the current validated example, do not apply an extra relatedness filter unless the approved methodology explicitly requires it.

The independent test reported that applying relatedness filtering changed the Hallucinations serious count from 98 to 95.

Make this rule visible in the execution plan.

## K. Case population

Do not silently exclude Invalid AE case, Invalid non-AE case or Non-AE case records.

The current benchmark includes such records. Their future eligibility must be confirmed against the company SOP.

Keep this as a configurable population rule.

## L. Event PT frequencies

Where required:

- Use event-row counts.
- Do not substitute distinct case counts for event counts.
- Display both numbers where useful.

---

# PART 4 – AGENT EXECUTION AND TRACEABILITY IN THE FRONTEND

**This is a mandatory core feature, not just a debugging log.**

The actual Streamlit interface must visibly display what every agent does and what it generates.

The user should be able to understand how the application reached each result.

## A. Agent Execution Monitor

Create a dedicated frontend page or section:

**Agent Execution & Traceability**

Display the actual execution of:

1. Document Understanding Agent.
2. Excel Understanding Agent.
3. Topic Mapping Agent.
4. Calculation Planning Agent.
5. Python Calculation Engine.
6. Validation Module.
7. Report Generation Module.

Show:

- Agent name.
- Execution status.
- Start and completion time.
- Input received.
- Python tools invoked.
- Tool arguments, with sensitive values redacted.
- Tool results.
- Structured output generated.
- Validation result.
- Output passed to the next agent.

### B. Live execution timeline

Display actual processing events as they occur.

Example:

**Excel Understanding Agent – Running**

Action 1: Discovered uploaded workbook.

Action 2: Invoked `inspect_workbook()` using OpenPyXL.

Result: Found Cover Page_1 and CSMR Case_2.

Action 3: Invoked `detect_header_row()`.

Result: Identified the actual header row.

Action 4: Invoked `profile_columns()` using Pandas.

Result: Identified case number, initial approval date and primary source fields.

Action 5: Generated workbook classification.

Result: Topic-specific case workbook.

This must be dynamically populated from actual tool invocations and results. Do not hardcode these example activities.

### C. Expandable agent results

Every agent should have an expandable panel containing:

- Input summary.
- Actual tool calls.
- Python library used.
- Tool output.
- Generated JSON.
- Mapping decisions.
- Warnings.
- Next-agent handoff.

Display actual generated JSON or readable structured information.

### D. Traceability of each reported number

Every calculated metric must provide a detailed traceability link.

For example:

**16.3.1.3 – Hallucinations and confusion**

Metric: Topic case count.

Show:

- Agent that identified the workbook.
- Source workbook filename.
- Source sheet.
- Detected header row.
- Actual case ID column.
- Actual date column.
- Detected date format.
- Applied reporting dates.
- Applied source exclusions.
- Number of records before filtering.
- Number of records after filtering.
- Distinct case count.
- Python calculation function used.
- Validation status.

The user must be able to expand each result and inspect this evidence.

### E. Persisted execution logs

Store structured execution events and agent outputs per processing run.

Use a run ID.

Suggested event fields:

- Run ID.
- Timestamp.
- Agent name.
- Event type.
- Tool name.
- Redacted input arguments.
- Tool result summary.
- Structured output.
- Execution status.
- Error or warning details.

The UI should allow users to inspect previous processing runs while respecting the organization's data-retention policy.

### F. Important restriction

Do not expose hidden model chain-of-thought or private internal reasoning.

Display operational actions, actual tool invocations, extracted observations, structured decisions, generated outputs and validation results.

**Never simulate agent activity or fabricate tool logs.**

---

# PART 5 – VALIDATION AND AUDIT

Implement a dedicated validation module.

For each result, record:

- PBRER section number.
- Topic heading.
- Historical reference figure.
- Calculated figure.
- Difference.
- Source workbook and sheet.
- Relevant column names.
- Header row.
- Data region.
- Date format.
- Reporting dates.
- Source exclusions.
- Rows before and after filtering.
- Distinct case count or event-row count.
- Join logic.
- Deduplication logic.
- Calculation function.
- Validation status.

### Mandatory checks

1. Input file validation.
2. Workbook and sheet identification.
3. Dynamic header detection.
4. Footer detection.
5. Date normalization.
6. Missing and invalid case IDs.
7. Duplicate case records.
8. Case/event join validation.
9. Clinical Trials exclusion.
10. Seriousness and death classifications.
11. Percentage calculations.
12. Topic criteria matching.
13. Independent topic reconstruction, where possible.
14. Inclusive date-boundary validation.

A critical failure must prevent the result from being marked verified.

Display the reason and affected workbook/metric.

Create synthetic date-boundary tests for records immediately before, on and after both reporting boundaries.

---

# PART 6 – BENCHMARK RESULTS

Use the following figures as development acceptance tests.

| Metric | Expected |
|---|---:|
| Total post-marketing cases | 3,651 |
| Impulse Control Disorders topic cases | 242 |
| ICD serious cases | 55 |
| ICD fatal cases | 1 |
| Hallucinations and Confusion cases | 270 |
| Hallucinations serious cases | 98 |
| Hallucinations fatal cases | 1 |

Expected source breakdown:

**All cases**
- Spontaneous: 3,272
- Other Studies: 379

**Impulse Control Disorders**
- Spontaneous: 225
- Other Studies: 17

**Hallucinations and Confusion**
- Spontaneous: 224
- Other Studies: 46

These values are for testing only. They must never be hardcoded into the calculation engine.

The independent review also identified:

- ICD serious event rows in traceability HTML: 76.
- ICD serious event rows in independent testing: 77.
- ICD distinct serious cases: 55 in both.

Investigate this discrepancy and preserve the evidence.

For Hallucinations:

- Case-level serious flag: 118 cases.
- Topic-specific event-level serious roll-up: 98 cases.

Use the topic-specific event-level method.

Generate a benchmark comparison report with:

| Metric | Expected | Calculated | Difference | Status |
|---|---:|---:|---:|---|

A matching result alone does not prove methodological correctness. Show the underlying filters and calculation evidence.

If required files are missing, mark the benchmark as unverified rather than inventing results.

---

# PART 7 – STREAMLIT FRONTEND

Build a polished, simple and professional Streamlit web application.

Do not build a separate React frontend for this POC.

The end-user application should have only these primary inputs:

1. Previous/approved PBRER.
2. Multiple updated Excel exports.
3. Reporting start date.
4. Reporting end date.

**Do not display the traceability HTML upload field.**

The traceability HTML is only available during development to understand the example methodology.

Do not expose AWS configuration, credentials, model IDs or developer configuration in the end-user UI.

### Required UI pages

**1. Dashboard**

- Application overview.
- Latest run status.
- Reporting interval.
- Number of detected topics.
- Processing summary.

**2. Upload Documents**

- Previous PBRER uploader.
- Multiple Excel upload.
- Reporting start date.
- Reporting end date.

**3. Document Analysis**

- Extracted Section 16.3 headings.
- Topic catalogue.
- Section hierarchy.
- Historical metrics extracted from the report.

**4. Excel Analysis**

- All discovered workbooks.
- Workbook classifications.
- Sheet names.
- Detected header rows.
- Data regions.
- Column profiles.
- Cover-page criteria.
- Case/event classifications.
- Canonical field mappings.

**5. Topic Mapping**

- Matched PBRER topic.
- Excel search criteria.
- Case and event workbooks.
- Mapping confidence.
- Manual correction and approval.

**6. Agent Execution & Traceability**

- Live execution timeline.
- Actual Python tool invocations.
- Agent inputs and structured outputs.
- Generated JSON.
- Tool results.
- Agent-to-agent handoffs.
- Warnings and failures.
- Expandable calculation provenance.

**7. Calculation Review**

- Reporting dates.
- Date column.
- Source exclusions.
- Metric definitions.
- Join and deduplication logic.
- Proposed calculation plan.

**8. Results Dashboard**

- Total cases.
- Topic-wise cases.
- Source breakdown.
- Serious cases.
- Fatal cases.
- Percentages.
- PT frequencies where applicable.
- Comparison with historical PBRER figures.

**9. Validation & Audit**

- Passed validations.
- Warnings.
- Failed validations.
- Source workbook and sheet.
- Calculation evidence.

**10. Downloads**

- Calculation results workbook.
- Audit-trail report.
- Report-ready Section 16.3 numerical output.
- Benchmark comparison report.

The application must not generate unsupported medical conclusions, clinical narratives or risk assessments. Focus on numerical extraction, calculation, validation and report-ready presentation.

The UI should dynamically display real execution outputs. It must never use hardcoded example data as live results.

---

# PART 8 – AWS BEDROCK AND COST CONTROL

I have an AWS account and can provide local AWS CLI access.

Inspect the locally configured AWS credential profile.

If Bedrock access is available, implement a configurable Bedrock provider using the appropriate AWS SDK.

Prefer a shared LLM provider with separate agent roles.

Use supported model tool-calling capabilities where available.

Use configurable:

- AWS profile.
- AWS region.
- Bedrock model ID.
- Model parameters.
- Maximum tool iterations.
- Maximum invocation count.
- Maximum output tokens.

Use locally configured AWS credentials. Do not request or print access keys, secret keys or session tokens.

Do not hardcode credentials.

Do not create AWS infrastructure, deploy services or upload data to S3.

If Bedrock is unavailable, do not pretend AI calls succeeded. Provide an explicitly labelled local/manual mode and document unavailable AI features.

### Cost-control requirements

1. Use Python for file extraction and data profiling.
2. Do not send entire Excel files to an LLM.
3. Never send every case row for AI interpretation.
4. Send only relevant metadata, document sections, redacted samples and criteria.
5. Batch metadata where appropriate.
6. Cache document and workbook analysis using file hashes and configuration versions.
7. Avoid repeating identical LLM calls.
8. Limit tool iterations and model invocations.
9. Log actual model invocation counts and token usage where available.
10. Do not repeatedly retry failed Bedrock calls.
11. Keep calculations deterministic and local.

The AI must inspect data through safe predefined tools. Sensitive PV data and narratives must not be sent to unapproved external models.

---

# PART 9 – PROJECT STRUCTURE

Build a modular application similar to:

```text
pbrer_automation/
│
├── app.py
│
├── config/
│   ├── settings.py
│   └── metric_registry.py
│
├── agents/
│   ├── document_agent.py
│   ├── excel_agent.py
│   ├── topic_mapping_agent.py
│   └── calculation_planner.py
│
├── tools/
│   ├── document_tools.py
│   ├── excel_tools.py
│   ├── profiling_tools.py
│   └── topic_tools.py
│
├── llm/
│   ├── provider.py
│   ├── bedrock_provider.py
│   ├── cache.py
│   └── prompts.py
│
├── extraction/
│   ├── pbrer_extractor.py
│   ├── excel_extractor.py
│   └── coverpage_extractor.py
│
├── profiling/
│   ├── header_detector.py
│   ├── footer_detector.py
│   ├── data_profiler.py
│   ├── date_detector.py
│   └── schema_mapper.py
│
├── processing/
│   ├── date_normalizer.py
│   ├── source_filter.py
│   ├── case_calculator.py
│   ├── event_calculator.py
│   └── topic_reconstruction.py
│
├── validation/
│   ├── input_validator.py
│   ├── mapping_validator.py
│   ├── calculation_validator.py
│   └── reconciliation.py
│
├── observability/
│   ├── event_logger.py
│   ├── run_manager.py
│   └── trace_store.py
│
├── generation/
│   ├── report_generator.py
│   ├── excel_generator.py
│   └── audit_generator.py
│
├── models/
│   ├── schemas.py
│   └── execution_plan.py
│
├── tests/
│   ├── test_date_normalization.py
│   ├── test_header_detection.py
│   ├── test_footer_detection.py
│   ├── test_source_filter.py
│   ├── test_case_counts.py
│   ├── test_event_counts.py
│   ├── test_topic_mapping.py
│   ├── test_date_boundaries.py
│   └── test_traceability.py
│
├── data/
│   ├── input/
│   ├── cache/
│   ├── output/
│   └── runs/
│
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

You may simplify this structure where appropriate, but preserve the separation between agents, Python tools, extraction, profiling, processing, validation, traceability and reporting.

---

# PART 10 – IMPLEMENTATION ORDER

Work in this exact development sequence.

### Phase 1 – Inspect actual reference files

- Inspect all development inputs.
- Study the PBRER.
- Study the development-only traceability HTML.
- Inspect all Excel workbooks and their real structures.
- Identify missing files and methodology uncertainties.
- Write a concise discovery report.

### Phase 2 – Build Python extraction tools

Implement and test:

- Document tools.
- Excel inspection tools.
- Header detection.
- Footer detection.
- Data profiling.
- Date normalization.
- Cover-page extraction.

### Phase 3 – Build the two primary AI agents

Implement:

- Document Understanding Agent.
- Excel Understanding Agent.

Test their tool-calling behaviour and structured outputs independently.

Ensure agents can make additional inspection calls based on what they discover.

### Phase 4 – Build topic mapping and planning

- Connect report topics to Excel criteria.
- Identify case/event workbook relationships.
- Build the metric registry.
- Generate and validate execution plans.

### Phase 5 – Build calculation and validation

- Apply date and source filters.
- Calculate total and topic case counts.
- Calculate source breakdowns.
- Calculate serious and fatal cases.
- Calculate percentages and event PT frequencies where supported.
- Add reconciliation and benchmark tests.

### Phase 6 – Build the frontend and observability

- Build Streamlit screens.
- Add agent execution timeline.
- Display real tool invocations and agent outputs.
- Show calculation provenance.
- Enable downloads.

### Phase 7 – End-to-end testing

Run the full application using the supplied development files.

Verify that the user can:

1. Upload the PBRER and multiple Excel exports.
2. Enter reporting dates.
3. Run document and Excel agents.
4. View extracted data and topic mappings.
5. Review the execution plan.
6. Run calculations.
7. View validation results.
8. Inspect each metric's exact source and calculation.
9. Download the outputs.

Do not stop after creating the project structure or UI mockups.

Implement the actual functionality and run the available tests.

---

# PART 11 – FINAL DELIVERABLES

Deliver:

1. A complete runnable POC.
2. Document Understanding Agent.
3. Autonomous tool-driven Excel Understanding Agent.
4. Topic Mapping Agent.
5. Calculation Planning Agent.
6. Python calculation engine.
7. Configurable metric registry.
8. Data profiling and dynamic schema mapping.
9. Validation and reconciliation modules.
10. AWS Bedrock integration where access is available.
11. Cost controls and model-call caching.
12. Professional Streamlit frontend.
13. Live Agent Execution & Traceability page.
14. Persisted structured execution logs.
15. Calculation results Excel workbook.
16. Report-ready numerical output.
17. Calculation audit trail.
18. Benchmark comparison report.
19. Unit and integration tests.
20. README with setup, AWS configuration, usage and troubleshooting instructions.
21. `.env.example` without actual credentials.

At completion, provide:

- Features actually implemented.
- Which AI agents actually use LLM tool calling.
- Which Python tools each agent invokes.
- Which components are deterministic rather than AI-driven.
- Whether Bedrock was successfully tested.
- Model invocation count and token usage, where available.
- Benchmark results achieved.
- Failed or unverified calculations.
- Methodology rules requiring company confirmation.
- Tests executed and their results.
- Exact commands to launch the application.

Do not claim a feature is implemented when it is only a placeholder.

Do not fabricate tool calls, agent outputs or benchmark results.

Do not claim a calculation passed unless it was actually executed on the available Excel records.

Do not write clinical conclusions or invent medical narratives.

**FINAL INSTRUCTION: First inspect the actual workspace and reference files. Then build the complete POC incrementally, prioritising autonomous file understanding, accurate benchmark reproduction and visible agent traceability over decorative frontend elements. Test the complete application end to end and leave the project in a runnable state.**