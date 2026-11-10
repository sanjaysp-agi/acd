import { html } from "../html.js";
import { useRun } from "../useRun.js";
import Spinner from "../components/Spinner.js";
import Banner, { NoRunBanner } from "../components/Banner.js";

export default function Dashboard({ runId, refreshKey }) {
  const { data, loading, error } = useRun(runId, refreshKey);

  return html`
    <h2>PBRER Section 16.3 Automation</h2>
    <p class="caption">AI-driven extraction, calculation and validation of Section 16.3 numerical figures.</p>
    ${!runId && html`<${Banner} kind="info">No run yet. Go to <b>Upload Documents</b> to start.<//>`}
    ${loading && html`<${Spinner} label="Loading run..." />`}
    ${error && html`<${Banner} kind="error">${error}<//>`}
    ${data && renderDashboard(data)}
  `;
}

function renderDashboard(result) {
  const doc = result.document_structure;
  const inv = result.workbook_inventory;
  const mapping = result.topic_mapping;
  const bench = result.benchmark_report;
  const topicsMapped = mapping.mappings.filter((m) => m.case_workbook).length;
  const matches = bench.rows.filter((r) => r.status === "match").length;
  const mismatches = bench.rows.filter((r) => r.status === "mismatch").length;

  return html`
    <h3>Latest run: <code>${result.run_id}</code></h3>
    <p class="caption">Generated at ${result.generated_at}</p>

    <div class="card-row">
      <div class="stat"><div class="label">Topics detected</div><div class="value">${doc.topics.length}</div></div>
      <div class="stat"><div class="label">Workbooks discovered</div><div class="value">${inv.workbooks.length}</div></div>
      <div class="stat"><div class="label">Topics mapped</div><div class="value">${topicsMapped}</div></div>
      <div class="stat">
        <div class="label">Benchmark matches</div>
        <div class="value">${matches}${mismatches ? html` <span class="badge fail">-${mismatches} mismatch</span>` : ""}</div>
      </div>
    </div>

    <h3>Reporting interval</h3>
    <p><b>${result.execution_plan.reporting_start}</b> to <b>${result.execution_plan.reporting_end}</b> (both boundaries inclusive)</p>

    ${mapping.unmatched_document_topics.length > 0 && html`
      <${Banner} kind="warn">Topics with no matching Excel workbook: ${mapping.unmatched_document_topics.join(", ")}<//>
    `}
    ${mapping.unmatched_workbooks.length > 0 && html`
      <${Banner} kind="warn">Workbooks with no matching PBRER topic: ${mapping.unmatched_workbooks.join(", ")}<//>
    `}
  `;
}
