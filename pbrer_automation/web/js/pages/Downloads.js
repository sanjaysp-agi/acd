import { html } from "../html.js";
import { downloadUrl } from "../api.js";
import { NoRunBanner } from "../components/Banner.js";

const ARTIFACTS = [
  { key: "calculation-results", file: "calculation_results.xlsx", desc: "Calculation results workbook -- every calculated metric with its value and status." },
  { key: "audit-trail", file: "audit_trail.xlsx", desc: "Audit-trail workbook -- full filter/evidence trail per metric." },
  { key: "report-ready", file: "section_16_3_figures.xlsx", desc: "Report-ready Section 16.3 numerical output -- figures laid out per topic." },
  { key: "benchmark-comparison", file: "benchmark_comparison.xlsx", desc: "Benchmark comparison report -- calculated vs. historical PBRER figures." },
];

export default function Downloads({ runId }) {
  if (!runId) return html`<h2>Downloads</h2><${NoRunBanner} />`;

  return html`
    <h2>Downloads</h2>
    ${ARTIFACTS.map((a) => html`
      <div key=${a.key} class="card">
        <p>${a.desc}</p>
        <a class="btn" href=${downloadUrl(runId, a.key)} download=${a.file}>Download ${a.file}</a>
      </div>
    `)}
  `;
}
