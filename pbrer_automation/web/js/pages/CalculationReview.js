import { html } from "../html.js";
import { useRun } from "../useRun.js";
import Spinner from "../components/Spinner.js";
import Banner, { NoRunBanner } from "../components/Banner.js";
import Table from "../components/Table.js";

const PLAN_COLUMNS = [
  { key: "pbrer_section_number", label: "Section" },
  { key: "topic_heading", label: "Topic" },
  { key: "metric_id", label: "Metric" },
  { key: "source_workbook", label: "Source workbook" },
  { key: "date_field", label: "Date field" },
  { key: "applies_clinical_trials_exclusion", label: "CT exclusion" },
  { key: "grain", label: "Grain" },
  { key: "distinct_by", label: "Distinct by", render: (v) => v || "(event rows)" },
  { key: "validated", label: "Validated" },
  { key: "validation_notes", label: "Notes", render: (v) => (v || []).join("; ") },
];

const DETAIL_COLUMNS = [
  { key: "metric_id", label: "Metric" },
  { key: "join_requirements", label: "Join requirements", render: (v) => v || "(none recorded)" },
  { key: "percentage_formula", label: "Percentage formula", render: (v) => v || "(not a percentage metric)" },
  { key: "distinct_by", label: "Deduplication", render: (v) => (v ? `Distinct by ${v}` : "None -- event-row counts, not deduplicated") },
];

export default function CalculationReview({ runId, refreshKey }) {
  const { data, loading } = useRun(runId, refreshKey);

  if (!runId) return html`<h2>Calculation Review</h2><${NoRunBanner} />`;
  if (loading) return html`<h2>Calculation Review</h2><${Spinner} />`;
  if (!data) return html`<h2>Calculation Review</h2>`;

  const plan = data.execution_plan;
  const seen = new Set();
  const detailRows = plan.steps.filter((s) => (seen.has(s.metric_id) ? false : seen.add(s.metric_id)));

  return html`
    <h2>Calculation Review</h2>
    <p><b>Reporting interval:</b> ${plan.reporting_start} to ${plan.reporting_end} (inclusive)</p>

    ${plan.warnings.map((w, i) => html`<${Banner} kind="warn" key=${i}>${w.message}<//>`)}

    <${Table} columns=${PLAN_COLUMNS} rows=${plan.steps} />
    <p class="caption">A step marked Validated=No was NOT executed by the calculation engine -- required column mappings were missing or low-confidence.</p>

    <h3>Join and percentage-formula logic per metric</h3>
    <p class="caption">Approved, controlled definitions from the metric registry -- never invented per-run by an agent.</p>
    <${Table} columns=${DETAIL_COLUMNS} rows=${detailRows} />
  `;
}
