import { html } from "../html.js";
import { useRun } from "../useRun.js";
import Spinner from "../components/Spinner.js";
import Banner, { NoRunBanner } from "../components/Banner.js";
import Table, { formatCell } from "../components/Table.js";
import Badge from "../components/Badge.js";

const CHECK_COLUMNS = [
  { key: "check_name", label: "Check" },
  { key: "status", label: "Status", render: (v) => html`<${Badge} status=${v} />` },
  { key: "message", label: "Message" },
];

const METRIC_STATUS_COLUMNS = [
  { key: "pbrer_section_number", label: "Section" },
  { key: "topic_heading", label: "Topic" },
  { key: "metric_id", label: "Metric" },
  { key: "validation_status", label: "Status", render: (v) => html`<${Badge} status=${v} />` },
  { key: "validation_messages", label: "Messages", render: (v) => (v || []).join(" | ") },
];

const RECON_COLUMNS = [
  { key: "pbrer_section_number", label: "Section" },
  { key: "topic_heading", label: "Topic" },
  { key: "criterion_type", label: "Criterion type" },
  { key: "feasible", label: "Feasible" },
  { key: "reconstructed_case_count", label: "Reconstructed cases" },
  { key: "topic_export_case_count", label: "Topic export cases" },
  { key: "comparison_status", label: "Comparison status", render: (v) => html`<${Badge} status=${v} />` },
  { key: "reason", label: "Reason/notes" },
];

// New since the migration: color the whole benchmark row by match status,
// not just the Status badge cell -- makes mismatches scannable at a glance.
const BENCH_ROW_BG = { match: "rgba(62,207,142,.06)", mismatch: "rgba(229,88,106,.08)", unverified: "" };

const BENCH_COLUMNS = [
  { key: "metric_label", label: "Metric" },
  { key: "expected", label: "Expected", render: (v) => formatCell(v) },
  { key: "calculated", label: "Calculated", render: (v) => formatCell(v) },
  { key: "difference", label: "Difference", render: (v) => formatCell(v) },
  { key: "status", label: "Status", render: (v) => html`<${Badge} status=${v} />` },
];

export default function Validation({ runId, refreshKey }) {
  const { data, loading } = useRun(runId, refreshKey);

  if (!runId) return html`<h2>Validation &amp; Audit</h2><${NoRunBanner} />`;
  if (loading) return html`<h2>Validation &amp; Audit</h2><${Spinner} />`;
  if (!data) return html`<h2>Validation &amp; Audit</h2>`;

  const results = data.metric_results;
  const bench = data.benchmark_report;
  const report = data.validation_report;
  const reconstruction = data.topic_reconstruction || [];
  const failed = results.filter((mr) => mr.validation_status === "failed");
  const discrepancies = reconstruction.filter((r) => r.feasible && (r.comparison || {}).status === "discrepancy");

  const matches = bench.rows.filter((r) => r.status === "match").length;
  const mismatches = bench.rows.filter((r) => r.status === "mismatch").length;
  const unverified = bench.rows.filter((r) => r.status === "unverified").length;

  return html`
    <h2>Validation &amp; Audit</h2>

    ${report && html`
      <h3>Overall validation status</h3>
      <div class="card-row">
        <div class="stat"><div class="label">Overall status</div><div class="value"><${Badge} status=${report.overall_status} /></div></div>
        <div class="stat"><div class="label">Checks passed</div><div class="value">${report.checks.filter((c) => c.status === "pass").length}</div></div>
        <div class="stat"><div class="label">Warnings</div><div class="value">${report.checks.filter((c) => c.status === "warning").length}</div></div>
        <div class="stat"><div class="label">Failures</div><div class="value">${report.checks.filter((c) => c.status === "fail").length}</div></div>
      </div>

      <h3>Mandatory checks (prompt.md Part 5, #1-14)</h3>
      <p class="caption">Input validation, workbook/sheet identification, header/footer detection, date normalization, case
        ID checks, case/event join (Rule H), Clinical Trials exclusion, seriousness/death classification, percentage
        calculation, topic-criteria matching, independent topic reconstruction, and date-boundary inclusivity.</p>
      <${Table} columns=${CHECK_COLUMNS} rows=${report.checks} />
    `}

    <h3>Validation status by metric</h3>
    <${Table} columns=${METRIC_STATUS_COLUMNS} rows=${results} />
    ${failed.length > 0 && html`<${Banner} kind="error">${failed.length} metric(s) FAILED validation -- not marked verified.<//>`}

    ${reconstruction.length > 0 && html`
      <h3>Independent topic reconstruction (cross-validation)</h3>
      <p class="caption">Each topic's own Excel search criterion re-applied to the all-drug-event workbook, independently of
        the topic-specific export -- a cross-check, never a substitute.</p>
      <${Table} columns=${RECON_COLUMNS} rows=${reconstruction.map((r) => ({
        ...r, comparison_status: r.feasible ? (r.comparison || {}).status || "n/a" : "not attempted",
      }))} />
      ${discrepancies.length > 0 && html`
        <${Banner} kind="warn">${discrepancies.length} topic(s) show a discrepancy between the independent reconstruction and the topic-specific export -- see evidence below.<//>
        ${discrepancies.map((r, i) => html`
          <details key=${i}><summary>Discrepancy evidence -- ${r.topic_heading}</summary><pre>${JSON.stringify(r.comparison, null, 2)}</pre></details>
        `)}
      `}
    `}

    <h3>Benchmark comparison</h3>
    <p class="caption">A match does not alone prove methodological correctness -- see the Results page for the full
      filter/evidence trail behind each figure.</p>
    <${Table} columns=${BENCH_COLUMNS} rows=${bench.rows} rowStyle=${(r) => ({ background: BENCH_ROW_BG[r.status] || "" })} />

    <div class="card-row">
      <div class="stat"><div class="label">Matches</div><div class="value">${matches}</div></div>
      <div class="stat"><div class="label">Mismatches</div><div class="value">${mismatches}</div></div>
      <div class="stat"><div class="label">Unverified (no historical figure)</div><div class="value">${unverified}</div></div>
    </div>
  `;
}
