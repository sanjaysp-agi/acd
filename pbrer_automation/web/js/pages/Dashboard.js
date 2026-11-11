import { html } from "../html.js";
import { useRun } from "../useRun.js";
import Spinner from "../components/Spinner.js";
import Banner from "../components/Banner.js";
import StatCard from "../components/StatCard.js";
import StatusPill from "../components/StatusPill.js";
import {
  documentsUploaded, safetyTopicsExtracted, tablesGenerated,
  validationSuccessPct, pendingReviewCount,
} from "../lib/businessMetrics.js";

export default function Dashboard({ runId, refreshKey, navigate }) {
  const { data, loading, error } = useRun(runId, refreshKey);

  return html`
    <div class="page-head">
      <div>
        <h2>Dashboard</h2>
        <p class="caption">Overview of the latest Section 16.3 automation run.</p>
      </div>
    </div>

    ${!runId && html`
      <${Banner} kind="info">
        No run yet. Go to <a href="#" onClick=${(e) => { e.preventDefault(); navigate("Upload Sources"); }}>Upload Sources</a> to start one.
      <//>
    `}
    ${loading && html`<${Spinner} label="Loading latest run..." />`}
    ${error && html`<${Banner} kind="error">${error}<//>`}
    ${data && renderDashboard(data, navigate)}
  `;
}

function renderDashboard(result, navigate) {
  const pending = pendingReviewCount(result);
  const score = validationSuccessPct(result);
  const plan = result.execution_plan;
  const mapping = result.topic_mapping;

  return html`
    <div class="kpi-grid">
      <${StatCard} label="Latest run status" value=${html`<${StatusPill} status="completed" />`} sub=${result.generated_at} />
      <${StatCard} label="Reporting interval" value=${`${plan.reporting_start} – ${plan.reporting_end}`} sub="Both boundaries inclusive" />
      <${StatCard} label="Documents uploaded" value=${documentsUploaded(result)} />
      <${StatCard} label="Extracted safety topics" value=${safetyTopicsExtracted(result)} />
      <${StatCard} label="Generated Section 16.3 tables" value=${tablesGenerated(result)} />
      <${StatCard} label="Validation score" value=${score == null ? "N/A" : `${score}%`} />
      <${StatCard}
        label="Pending review items"
        value=${pending}
        sub=${pending > 0 ? html`<a href="#" onClick=${(e) => { e.preventDefault(); navigate("Review & Validation"); }}>Review now</a>` : "All clear"}
      />
    </div>

    ${mapping.unmatched_document_topics.length > 0 && html`
      <${Banner} kind="warn">
        ${mapping.unmatched_document_topics.length} safety topic(s) have no matching data source --
        see <a href="#" onClick=${(e) => { e.preventDefault(); navigate("Review & Validation"); }}>Review & Validation<//> to resolve.
      <//>
    `}
    ${mapping.unmatched_workbooks.length > 0 && html`
      <${Banner} kind="warn">
        ${mapping.unmatched_workbooks.length} uploaded data source(s) have no matching safety topic --
        see <a href="#" onClick=${(e) => { e.preventDefault(); navigate("Review & Validation"); }}>Review & Validation<//> to resolve.
      <//>
    `}
  `;
}
