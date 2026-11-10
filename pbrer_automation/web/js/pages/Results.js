import { html } from "../html.js";
import { useRun } from "../useRun.js";
import Spinner from "../components/Spinner.js";
import { NoRunBanner } from "../components/Banner.js";

function displayValue(mr) {
  const v = mr.calculated_value;
  if (mr.metric_id === "serious_fatal_percentages" && v && typeof v === "object") {
    return `serious ${v.serious_pct}% / fatal ${v.fatal_pct}%`;
  }
  if (["number", "string"].includes(typeof v)) return v;
  if (Array.isArray(v)) return v.length ? `${v.length} items` : "-";
  if (v && typeof v === "object") return `${Object.keys(v).length} items`;
  return "-";
}

export default function Results({ runId, refreshKey }) {
  const { data, loading } = useRun(runId, refreshKey);

  if (!runId) return html`<h2>Results Dashboard</h2><${NoRunBanner} />`;
  if (loading) return html`<h2>Results Dashboard</h2><${Spinner} />`;
  if (!data) return html`<h2>Results Dashboard</h2>`;

  const byTopic = {};
  for (const mr of data.metric_results) {
    const key = mr.pbrer_section_number || "Total";
    (byTopic[key] = byTopic[key] || []).push(mr);
  }
  const sections = Object.keys(byTopic).sort();

  return html`
    <h2>Results Dashboard</h2>
    ${sections.map((section) => {
      const metrics = byTopic[section];
      const heading = metrics[0].topic_heading || "All post-marketing cases";
      return html`
        <div key=${section} class="card">
          <h3>${section} -- ${heading}</h3>
          <div class="card-row">
            ${metrics.map((mr, i) => html`
              <div class="stat" key=${i}>
                <div class="label">${mr.metric_id}</div>
                <div class="value">${displayValue(mr)}</div>
                ${mr.historical_value != null && typeof mr.calculated_value === "number" && html`
                  <div class="caption">${mr.difference >= 0 ? "+" : ""}${mr.difference} vs historical ${mr.historical_value}</div>
                `}
              </div>
            `)}
          </div>
          ${metrics.map((mr, i) => html`
            <details key=${i}>
              <summary>Traceability -- ${mr.metric_id}</summary>
              <p><b>Validation status:</b> ${mr.validation_status}</p>
              <p><b>Source:</b> <code>${mr.evidence.source_workbook}</code> / sheet <code>${mr.evidence.source_sheet}</code> / header row ${mr.evidence.header_row}</p>
              <p><b>Case ID column:</b> ${mr.evidence.case_id_column} -- <b>Date column:</b> ${mr.evidence.date_column} (${mr.evidence.date_format})</p>
              <p><b>Reporting period:</b> ${mr.evidence.reporting_start} to ${mr.evidence.reporting_end} (inclusive)</p>
              <p><b>Clinical Trials exclusion:</b> applied, matched values ${JSON.stringify(mr.evidence.source_exclusion_values_matched)}</p>
              <p><b>Rows before filter:</b> ${mr.evidence.rows_before_filter} -- <b>after filter:</b> ${mr.evidence.rows_after_filter}</p>
              ${mr.evidence.distinct_case_count != null && html`<p><b>Distinct case count:</b> ${mr.evidence.distinct_case_count}</p>`}
              ${mr.evidence.event_row_count != null && html`<p><b>Event row count:</b> ${mr.evidence.event_row_count}</p>`}
              <p><b>Calculation function:</b> <code>${mr.evidence.calculation_function}</code></p>
              ${mr.validation_messages.length > 0 && html`<p class="caption">${mr.validation_messages.join(" | ")}</p>`}
              ${(typeof mr.calculated_value === "object") && html`<pre>${JSON.stringify(mr.calculated_value, null, 2)}</pre>`}
            </details>
          `)}
        </div>
      `;
    })}
  `;
}
