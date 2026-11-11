import { React, html } from "../../html.js";
import { recomputeTopicMapping } from "../../api.js";
import Badge from "../Badge.js";
import Banner from "../Banner.js";
import Spinner from "../Spinner.js";
import { formatCell } from "../Table.js";

const NONE = "(none)";

// Maps an AIScoreResult to the same ok/warn/fail vocabulary Badge already
// understands (verified/warning/failed/unverified) -- never a raw float
// with no qualitative read. "unverified" only when the score agent found
// no citation at all; otherwise the numeric score itself decides severity.
function aiScoreStatus(s) {
  if (!s.present_in_source) return "unverified";
  if (s.score >= 0.8) return "verified";
  if (s.score >= 0.5) return "warning";
  return "failed";
}

function aiScoreCitationText(citation) {
  if (!citation) return "no citation";
  if (citation.source_type === "document") {
    return [citation.document_section_number, citation.document_section_title].filter(Boolean).join(" — ") || "document (no section recorded)";
  }
  if (citation.source_type === "workbook") {
    return [citation.source_workbook, citation.source_sheet].filter(Boolean).join(" / ") || "workbook (no sheet recorded)";
  }
  return "no citation";
}

// Right-rail "Validation Findings" tab: mandatory-check results, benchmark
// comparison, independent reconstruction and extraction-review findings
// for the selected table, plus an inline "Fix data source mapping" action
// (replaces the old standalone Topic Mapping page) when this topic's
// workbook mapping needs review.
export default function ValidationFindings({ data, group, runId, invalidate }) {
  const [mappingRows, setMappingRows] = React.useState(null);
  const [recomputing, setRecomputing] = React.useState(false);
  const [editError, setEditError] = React.useState(null);
  const [editing, setEditing] = React.useState(false);

  React.useEffect(() => {
    setMappingRows(data.topic_mapping.mappings.map((m) => ({
      case_workbook: m.case_workbook || NONE,
      drug_event_workbook: m.drug_event_workbook || NONE,
      approved: !m.needs_review && m.case_workbook !== null,
    })));
    setEditing(false);
  }, [data]);

  if (!group) return html`<p class="caption">Select a generated table to see its validation findings.</p>`;
  if (!mappingRows) return null;

  const mappingIndex = data.topic_mapping.mappings.findIndex((m) => m.pbrer_section_number === group.section);
  const mapping = mappingIndex >= 0 ? data.topic_mapping.mappings[mappingIndex] : null;
  const needsFix = !!mapping && (mapping.needs_review || !mapping.case_workbook);

  const workbooks = data.workbook_inventory.workbooks;
  const caseOptions = [NONE, ...workbooks.filter((w) => ["topic_case", "all_case"].includes(w.workbook_type)).map((w) => w.file_name)];
  const eventOptions = [NONE, ...workbooks.filter((w) => ["topic_drug_event", "all_drug_event"].includes(w.workbook_type)).map((w) => w.file_name)];

  const updateRow = (patch) => setMappingRows((prev) => prev.map((r, i) => (i === mappingIndex ? { ...r, ...patch } : r)));

  const applyFix = async () => {
    setRecomputing(true);
    setEditError(null);
    try {
      const payload = mappingRows.map((r) => ({
        case_workbook: r.case_workbook === NONE ? null : r.case_workbook,
        drug_event_workbook: r.drug_event_workbook === NONE ? null : r.drug_event_workbook,
        approved: r.approved,
      }));
      await recomputeTopicMapping(runId, payload);
      setEditing(false);
      invalidate();
    } catch (e) {
      setEditError(e.message);
    } finally {
      setRecomputing(false);
    }
  };

  const failedMetrics = group.metrics.filter((mr) => mr.validation_status === "failed");
  const firstWord = (metricId) => metricId.replace(/_/g, " ").toLowerCase().split(" ")[0];
  const benchRows = (data.benchmark_report.rows || []).filter((r) => {
    const label = r.metric_label.toLowerCase();
    return group.metrics.some((mr) => label.includes(firstWord(mr.metric_id))) || label.includes(group.heading.toLowerCase());
  });
  const reconstruction = (data.topic_reconstruction || []).filter((r) => r.topic_heading === group.heading);
  const findings = (data.extraction_review || []).filter(
    (f) => f.topic_heading === group.heading || (group.section && f.pbrer_section_number === group.section)
  );
  // AI Score Validation Agent output (runs AFTER the deterministic
  // validation above -- see agents/ai_scoring_agent.py): a 0.0-1.0
  // confidence score per metric, always backed by a citation so the score
  // itself is checkable rather than an opaque number.
  const aiScores = (data.ai_score_report?.scores || []).filter(
    (s) => s.topic_heading === group.heading || (group.section && s.pbrer_section_number === group.section)
  );

  return html`
    <div>
      ${editError && html`<${Banner} kind="error">${editError}<//>`}

      ${needsFix && html`
        <${Banner} kind="warn">
          This table's data source mapping needs review.
          <button class="btn secondary" style=${{ marginLeft: "8px" }} onClick=${() => setEditing((v) => !v)}>
            ${editing ? "Hide" : "Fix data source mapping"}
          </button>
        <//>
      `}
      ${editing && mapping && html`
        <div class="card">
          <div class="field">
            <label>Case workbook</label>
            <select value=${mappingRows[mappingIndex].case_workbook} onChange=${(e) => updateRow({ case_workbook: e.target.value })}>
              ${caseOptions.map((o) => html`<option key=${o} value=${o}>${o}</option>`)}
            </select>
          </div>
          <div class="field">
            <label>Drug-event workbook</label>
            <select value=${mappingRows[mappingIndex].drug_event_workbook} onChange=${(e) => updateRow({ drug_event_workbook: e.target.value })}>
              ${eventOptions.map((o) => html`<option key=${o} value=${o}>${o}</option>`)}
            </select>
          </div>
          <label><input type="checkbox" checked=${mappingRows[mappingIndex].approved} onChange=${(e) => updateRow({ approved: e.target.checked })} /> Approved</label>
          <div style=${{ marginTop: "10px" }}>
            <button class="btn" disabled=${recomputing} onClick=${applyFix}>
              ${recomputing ? html`<${Spinner} label="Re-running calculations..." />` : "Apply and re-run calculations"}
            </button>
          </div>
        </div>
      `}

      <h4>Metric validation</h4>
      ${group.metrics.map((mr, i) => html`
        <div key=${i} style=${{ marginBottom: "8px" }}>
          <${Badge} status=${mr.validation_status} /> <span>${mr.metric_id}</span>
          ${mr.validation_messages.length > 0 && html`<div class="caption">${mr.validation_messages.join(" | ")}</div>`}
        </div>
      `)}
      ${failedMetrics.length > 0 && html`<${Banner} kind="error">${failedMetrics.length} metric(s) failed validation.<//>`}

      <h4>AI confidence score</h4>
      ${aiScores.length > 0 ? aiScores.map((s, i) => html`
        <div key=${i} style=${{ marginBottom: "8px" }}>
          <${Badge} status=${aiScoreStatus(s)} /> <span>${s.metric_id}: ${Math.round(s.score * 100)}%</span>
          <div class="caption">
            ${s.present_in_source ? "Present in source" : "Not found in source"} — ${aiScoreCitationText(s.citation)}
          </div>
          ${s.citation?.detail && html`<div class="caption">${s.citation.detail}</div>`}
        </div>
      `) : html`<p class="caption">No AI confidence score recorded for this table.</p>`}

      <h4>Benchmark comparison</h4>
      ${benchRows.length > 0 ? benchRows.map((r, i) => html`
        <div key=${i} style=${{ marginBottom: "6px" }}>
          <${Badge} status=${r.status} /> <span>${r.metric_label}: ${formatCell(r.calculated)} (expected ${formatCell(r.expected)})</span>
        </div>
      `) : html`<p class="caption">No historical figure to benchmark against.</p>`}

      ${reconstruction.length > 0 && html`
        <h4>Independent reconstruction</h4>
        ${reconstruction.map((r, i) => html`
          <p key=${i} class="caption">
            ${r.feasible
              ? `Reconstructed ${r.reconstructed_case_count} cases vs ${r.topic_export_case_count} in export — ${(r.comparison || {}).status || "n/a"}`
              : `Not feasible: ${r.reason}`}
          </p>
        `)}
      `}

      ${findings.length > 0 && html`
        <h4>Extraction review findings</h4>
        ${findings.map((f, i) => html`<${Banner} kind=${f.severity === "warning" ? "warn" : "info"} key=${i}>${f.message}<//>`)}
      `}
    </div>
  `;
}
