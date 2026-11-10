import { html } from "../html.js";
import { useRun } from "../useRun.js";
import Spinner from "../components/Spinner.js";
import { NoRunBanner } from "../components/Banner.js";

const SEVERITY_ICON = { info: "ℹ️", warning: "⚠️", critical: "🔴" };

export default function DocumentAnalysis({ runId, refreshKey }) {
  const { data, loading } = useRun(runId, refreshKey);

  if (!runId) return html`<h2>Document Analysis</h2><${NoRunBanner} />`;
  if (loading) return html`<h2>Document Analysis</h2><${Spinner} />`;
  if (!data) return html`<h2>Document Analysis</h2>`;

  const doc = data.document_structure;

  return html`
    <h2>Document Analysis</h2>
    <p><b>Document:</b> ${doc.document_file_name}</p>
    <p><b>Heading detection strategy:</b> <code>${doc.heading_style_strategy}</code></p>
    <p><b>Target section located:</b> ${doc.target_section_located ? `Yes -- ${doc.target_section_title}` : "NOT located"}</p>

    ${doc.warnings.length > 0 && html`
      <details>
        <summary>Warnings (${doc.warnings.length})</summary>
        ${doc.warnings.map((w, i) => html`<p key=${i}>${SEVERITY_ICON[w.severity] || ""} <b>${w.code}</b>: ${w.message}</p>`)}
      </details>
    `}

    <h3>Topic catalogue</h3>
    ${doc.topics.map((t, i) => html`
      <details key=${i} class="card">
        <summary>${t.section_number} -- ${t.title} (${t.section_number_confidence ? `confidence ${t.section_number_confidence.toFixed(2)}` : "unconfirmed"})</summary>
        ${Object.keys(t.historical_metrics || {}).length > 0
          ? html`<pre>${JSON.stringify(t.historical_metrics, null, 2)}</pre>`
          : html`<p class="caption">No historical figures extracted for this topic (no data table found in the document).</p>`}
        ${t.raw_table_rows.length > 0 && html`
          <p class="caption">Raw table rows:</p>
          <table><tbody>
            ${t.raw_table_rows.map((row, j) => html`
              <tr key=${j}>${Object.values(row).map((v, k) => html`<td key=${k}>${v}</td>`)}</tr>
            `)}
          </tbody></table>
        `}
      </details>
    `)}
  `;
}
