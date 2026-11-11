import { html } from "../../html.js";

// Right-rail "Source Citations" tab: every piece of evidence that used to
// live on the separate Document Analysis / Excel Analysis / Calculation
// Review pages, scoped to the one table a reviewer is currently looking at.
export default function SourceCitations({ data, group }) {
  if (!group) return html`<p class="caption">Select a generated table to see its source citations.</p>`;

  const topic = (data.document_structure.topics || []).find(
    (t) => t.section_number === group.section || t.title === group.heading
  );
  const mapping = (data.topic_mapping.mappings || []).find(
    (m) => m.pbrer_section_number === group.section
  );
  const planSteps = (data.execution_plan.steps || []).filter(
    (s) => group.metrics.some((mr) => mr.metric_id === s.metric_id)
  );

  return html`
    <div>
      <h4>Document source</h4>
      ${topic ? html`
        <p class="caption">
          Heading detected at confidence
          ${topic.section_number_confidence != null ? topic.section_number_confidence.toFixed(2) : "unconfirmed"}.
        </p>
        ${Object.keys(topic.historical_metrics || {}).length > 0 && html`<pre>${JSON.stringify(topic.historical_metrics, null, 2)}</pre>`}
      ` : html`<p class="caption">No document topic matched to this table.</p>`}

      <h4>Data source mapping</h4>
      ${mapping ? html`
        <p><b>Case workbook:</b> ${mapping.case_workbook || "(none)"}</p>
        <p><b>Drug-event workbook:</b> ${mapping.drug_event_workbook || "(none)"}</p>
        <p class="caption">Mapping confidence ${mapping.confidence.toFixed(2)} — matched on term-overlap between the document's search criteria and the workbook's cover-page criterion.</p>
      ` : html`<p class="caption">No data source mapping recorded.</p>`}

      <h4>Calculation logic</h4>
      ${planSteps.length > 0 ? planSteps.map((s, i) => html`
        <div key=${i} class="card">
          <p><b>${s.metric_id}</b></p>
          <p class="caption">Join requirements: ${s.join_requirements || "(none recorded)"}</p>
          <p class="caption">Percentage formula: ${s.percentage_formula || "(not a percentage metric)"}</p>
          <p class="caption">Deduplication: ${s.distinct_by ? `Distinct by ${s.distinct_by}` : "None — event-row counts"}</p>
        </div>
      `) : html`<p class="caption">No calculation plan steps recorded.</p>`}

      <h4>Per-metric evidence</h4>
      ${group.metrics.map((mr, i) => html`
        <details key=${i}>
          <summary>${mr.metric_id}</summary>
          <p><b>Source:</b> <code>${mr.evidence.source_workbook}</code> / sheet <code>${mr.evidence.source_sheet}</code> / header row ${mr.evidence.header_row}</p>
          <p><b>Case ID column:</b> ${mr.evidence.case_id_column} — <b>Date column:</b> ${mr.evidence.date_column} (${mr.evidence.date_format})</p>
          <p><b>Reporting period:</b> ${mr.evidence.reporting_start} to ${mr.evidence.reporting_end} (inclusive)</p>
          <p><b>Rows before filter:</b> ${mr.evidence.rows_before_filter} — <b>after filter:</b> ${mr.evidence.rows_after_filter}</p>
          <p><b>Calculation function:</b> <code>${mr.evidence.calculation_function}</code></p>
          ${typeof mr.calculated_value === "object" && mr.calculated_value !== null && html`
            <p class="caption">Full calculated value:</p>
            <pre>${JSON.stringify(mr.calculated_value, null, 2)}</pre>
          `}
        </details>
      `)}
    </div>
  `;
}
