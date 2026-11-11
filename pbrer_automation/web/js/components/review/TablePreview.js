import { html } from "../../html.js";
import Table, { formatCell } from "../Table.js";
import Badge from "../Badge.js";
import Banner from "../Banner.js";
import { formatCaseRatio } from "../../lib/businessMetrics.js";

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
  if (Array.isArray(v)) return v.length ? `${v.length} items — see Source Citations` : "-";
  if (v && typeof v === "object") return `${Object.keys(v).length} items — see Source Citations`;
  return "-";
}

const COLUMNS = [
  { key: "metric_id", label: "Metric" },
  { key: "value", label: "Value" },
  { key: "historical_value", label: "Historical" },
  { key: "difference", label: "Difference" },
  { key: "validation_status", label: "Status", render: (v) => html`<${Badge} status=${v} />` },
];

// Center panel of Review & Validation: the selected table's figures,
// rendered as a clean regulatory-style data table -- this IS the "table"
// a reviewer is reviewing.
export default function TablePreview({ group }) {
  if (!group) return html`<p class="caption">Select a generated table from the list on the left.</p>`;
  const rows = group.metrics.map((mr) => ({ ...mr, value: displayValue(mr, group.metrics) }));
  return html`
    <div>
      <h3>${group.section || "Total"} — ${group.heading}</h3>
      ${group.metrics.length === 0
        ? html`<${Banner} kind="warn">No figures were calculated for this topic -- its data source mapping needs review. See Validation Findings.<//>`
        : html`<${Table} columns=${COLUMNS} rows=${rows} />`}
    </div>
  `;
}
