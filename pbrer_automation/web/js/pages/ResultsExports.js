import { html } from "../html.js";
import { useRun } from "../useRun.js";
import { downloadUrl } from "../api.js";
import Spinner from "../components/Spinner.js";
import { NoRunBanner } from "../components/Banner.js";
import Table, { formatCell } from "../components/Table.js";
import Badge from "../components/Badge.js";
import { groupMetricsBySection, formatCaseRatio } from "../lib/businessMetrics.js";

function displayValue(mr, groupMetrics) {
  const v = mr.calculated_value;
  if (mr.metric_id === "serious_fatal_percentages" && v && typeof v === "object") {
    return `serious ${v.serious_pct}% / fatal ${v.fatal_pct}%`;
  }
  // Serious/fatal case counts always render as "numerator/denominator"
  // (e.g. "55/242") against the topic's own case count.
  const ratio = formatCaseRatio(mr, groupMetrics);
  if (ratio) return ratio;
  if (["number", "string"].includes(typeof v)) return formatCell(v);
  if (Array.isArray(v)) return v.length ? `${v.length} items` : "-";
  if (v && typeof v === "object") return `${Object.keys(v).length} items`;
  return "-";
}

const COLUMNS = [
  { key: "metric_id", label: "Metric" },
  { key: "value", label: "Value" },
  { key: "validation_status", label: "Status", render: (v) => html`<${Badge} status=${v} />` },
];

const EXPORTS = [
  { key: "docx-report", file: "section_16_3_report.docx", label: "Export to DOCX", desc: "Section 16.3 report with one table per topic -- ready for inclusion in the PBRER document." },
  { key: "report-ready", file: "section_16_3_figures.xlsx", label: "Export to XLSX", desc: "Report-ready Section 16.3 numerical output, laid out per topic." },
  { key: "audit-package", file: "audit_package.zip", label: "Export Audit Package", desc: "Full regulatory audit trail: calculation evidence, benchmark comparison, agent execution log and reviewer comments, bundled as one archive." },
];

export default function ResultsExports({ runId, refreshKey }) {
  const { data, loading } = useRun(runId, refreshKey);

  if (!runId) return html`<h2>Results & Exports</h2><${NoRunBanner} />`;
  if (loading) return html`<h2>Results & Exports</h2><${Spinner} />`;
  if (!data) return html`<h2>Results & Exports</h2>`;

  const groups = groupMetricsBySection(data.metric_results);

  return html`
    <div class="page-head">
      <div>
        <h2>Results & Exports</h2>
        <p class="caption">Finalized Section 16.3 outputs for run <code>${runId}</code>.</p>
      </div>
    </div>

    <div class="card">
      <h3>Version information</h3>
      <p><b>Run ID:</b> <code>${data.run_id}</code></p>
      <p><b>Generated at:</b> ${data.generated_at}</p>
      <p><b>Reporting interval:</b> ${data.execution_plan.reporting_start} to ${data.execution_plan.reporting_end} (inclusive)</p>
    </div>

    <h3>Generated Section 16.3 outputs</h3>
    ${groups.map((g) => html`
      <div key=${g.key} class="card">
        <h3>${g.section || "Total"} — ${g.heading}</h3>
        <${Table} columns=${COLUMNS} rows=${g.metrics.map((mr) => ({ ...mr, value: displayValue(mr, g.metrics) }))} />
      </div>
    `)}

    <h3>Export</h3>
    <div class="card-row">
      ${EXPORTS.map((x) => html`
        <div key=${x.key} class="card" style=${{ flex: "1 1 260px" }}>
          <p class="caption">${x.desc}</p>
          <a class="btn block" href=${downloadUrl(runId, x.key)} download=${x.file}>${x.label}</a>
        </div>
      `)}
    </div>
  `;
}
