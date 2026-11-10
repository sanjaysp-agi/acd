import { html } from "../html.js";

// Generic read-only table: columns = [{key, label, render?: (value, row) => node}]
// `rowStyle?: (row) => object` lets a page color-code rows (e.g. the
// Validation page's benchmark match/mismatch diff highlighting). Must
// return a style OBJECT (React convention), not a CSS string.
export default function Table({ columns, rows, emptyText, rowStyle }) {
  if (!rows || rows.length === 0) {
    return html`<p class="caption">${emptyText || "No data."}</p>`;
  }
  return html`
    <table>
      <thead>
        <tr>${columns.map((c) => html`<th key=${c.key}>${c.label}</th>`)}</tr>
      </thead>
      <tbody>
        ${rows.map((row, i) => html`
          <tr key=${i} style=${rowStyle ? rowStyle(row) : undefined}>
            ${columns.map((c) => html`<td key=${c.key}>${c.render ? c.render(row[c.key], row) : formatCell(row[c.key])}</td>`)}
          </tr>
        `)}
      </tbody>
    </table>
  `;
}

export function formatCell(value) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.slice(0, 10).join(", ") + (value.length > 10 ? ", ..." : "");
  if (typeof value === "object") return Object.entries(value).map(([k, v]) => `${k}=${v}`).join("; ");
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value);
}
