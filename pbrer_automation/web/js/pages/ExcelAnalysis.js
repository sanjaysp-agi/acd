import { html } from "../html.js";
import { useRun } from "../useRun.js";
import Spinner from "../components/Spinner.js";
import { NoRunBanner } from "../components/Banner.js";
import Table from "../components/Table.js";

const MAPPING_COLUMNS = [
  { key: "raw_column", label: "Raw column" },
  { key: "canonical_field", label: "Canonical field" },
  { key: "confidence", label: "Confidence" },
  { key: "needs_review", label: "Needs review" },
];

export default function ExcelAnalysis({ runId, refreshKey }) {
  const { data, loading } = useRun(runId, refreshKey);

  if (!runId) return html`<h2>Excel Analysis</h2><${NoRunBanner} />`;
  if (loading) return html`<h2>Excel Analysis</h2><${Spinner} />`;
  if (!data) return html`<h2>Excel Analysis</h2>`;

  const workbooks = data.workbook_inventory.workbooks;

  return html`
    <h2>Excel Analysis</h2>
    ${workbooks.map((wb, i) => html`
      <details key=${i} class="card">
        <summary>${wb.file_name} -- ${wb.workbook_type} (confidence ${wb.classification_confidence.toFixed(2)})</summary>
        <p><b>Linked workbook:</b> ${wb.linked_workbook || "-"}</p>
        <p><b>Data grain:</b> ${wb.data_grain}</p>
        <p><b>Classification evidence:</b></p>
        <ul>${wb.classification_evidence.map((e, j) => html`<li key=${j} class="caption">${e}</li>`)}</ul>

        ${wb.cover_page_criteria && wb.cover_page_criteria.criterion_value && html`
          <p><b>Cover-page criterion:</b> ${wb.cover_page_criteria.criterion_type} = ${wb.cover_page_criteria.criterion_value}</p>
        `}

        ${wb.sheets.filter((s) => s.role === "data_table").map((s, j) => html`
          <p key=${j}><b>Sheet <code>${s.sheet_name}</code></b> -- header row ${s.header_row}, ${s.row_count} data rows, footer rows ${JSON.stringify(s.footer_rows)}</p>
        `)}

        <p><b>Column mappings:</b></p>
        <${Table} columns=${MAPPING_COLUMNS} rows=${wb.column_mappings} />

        ${wb.warnings.map((w, j) => html`<p key=${j} class="caption">⚠️ ${w.message}</p>`)}
      </details>
    `)}
  `;
}
