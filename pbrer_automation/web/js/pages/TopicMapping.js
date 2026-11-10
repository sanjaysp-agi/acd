import { React, html } from "../html.js";
import { useRun } from "../useRun.js";
import { recomputeTopicMapping } from "../api.js";
import Spinner from "../components/Spinner.js";
import Banner, { NoRunBanner } from "../components/Banner.js";

const NONE = "(none)";

export default function TopicMapping({ runId, refreshKey, invalidate }) {
  const { data, loading } = useRun(runId, refreshKey);
  const [rows, setRows] = React.useState(null);
  const [recomputing, setRecomputing] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [success, setSuccess] = React.useState(false);

  React.useEffect(() => {
    if (!data) { setRows(null); return; }
    setRows(data.topic_mapping.mappings.map((m) => ({
      case_workbook: m.case_workbook || NONE,
      drug_event_workbook: m.drug_event_workbook || NONE,
      approved: !m.needs_review && m.case_workbook !== null,
    })));
    setSuccess(false);
  }, [data]);

  if (!runId) return html`<h2>Topic Mapping</h2><${NoRunBanner} />`;
  if (loading) return html`<h2>Topic Mapping</h2><${Spinner} />`;
  if (!data || !rows) return html`<h2>Topic Mapping</h2>`;

  const mapping = data.topic_mapping;
  const workbooks = data.workbook_inventory.workbooks;
  const caseOptions = [NONE, ...workbooks.filter((w) => ["topic_case", "all_case"].includes(w.workbook_type)).map((w) => w.file_name)];
  const eventOptions = [NONE, ...workbooks.filter((w) => ["topic_drug_event", "all_drug_event"].includes(w.workbook_type)).map((w) => w.file_name)];

  const updateRow = (i, patch) => setRows((prev) => prev.map((r, j) => (i === j ? { ...r, ...patch } : r)));

  const applyAndRecompute = async () => {
    setRecomputing(true);
    setError(null);
    try {
      const payload = rows.map((r) => ({
        case_workbook: r.case_workbook === NONE ? null : r.case_workbook,
        drug_event_workbook: r.drug_event_workbook === NONE ? null : r.drug_event_workbook,
        approved: r.approved,
      }));
      await recomputeTopicMapping(runId, payload);
      setSuccess(true);
      invalidate();
    } catch (e) {
      setError(e.message);
    } finally {
      setRecomputing(false);
    }
  };

  return html`
    <h2>Topic Mapping</h2>
    <p class="caption">Confidence is term-overlap between the PBRER's own search-criteria text and the Excel cover page's
      criterion value -- not a guess from the heading's number or filename. Edit the Case/Drug-event workbook or Approved
      columns below to manually correct a mapping, then re-run the calculation stages with the correction applied.</p>

    ${error && html`<${Banner} kind="error">${error}<//>`}
    ${success && html`<${Banner} kind="info">Corrections applied -- execution plan, calculations and validation re-run.<//>`}

    <table>
      <thead><tr>
        <th>Section</th><th>Heading</th><th>Criterion type</th><th>Case workbook</th>
        <th>Drug-event workbook</th><th>Confidence</th><th>Needs review</th><th>Approved</th>
      </tr></thead>
      <tbody>
        ${mapping.mappings.map((m, i) => html`
          <tr key=${i}>
            <td>${m.pbrer_section_number}</td>
            <td>${m.pbrer_heading}</td>
            <td>${m.excel_criterion_type}</td>
            <td>
              <select value=${rows[i].case_workbook} onChange=${(e) => updateRow(i, { case_workbook: e.target.value })}>
                ${caseOptions.map((o) => html`<option key=${o} value=${o}>${o}</option>`)}
              </select>
            </td>
            <td>
              <select value=${rows[i].drug_event_workbook} onChange=${(e) => updateRow(i, { drug_event_workbook: e.target.value })}>
                ${eventOptions.map((o) => html`<option key=${o} value=${o}>${o}</option>`)}
              </select>
            </td>
            <td>${m.confidence.toFixed(2)}</td>
            <td>${m.needs_review ? "Yes" : "No"}</td>
            <td><input type="checkbox" checked=${rows[i].approved} onChange=${(e) => updateRow(i, { approved: e.target.checked })} /></td>
          </tr>
        `)}
      </tbody>
    </table>

    ${mapping.unmatched_document_topics.length > 0 && html`
      <${Banner} kind="warn">Unmatched PBRER topics (no Excel export provided): ${mapping.unmatched_document_topics.join(", ")}<//>
    `}
    ${mapping.unmatched_workbooks.length > 0 && html`
      <${Banner} kind="warn">Unmatched workbooks (no corresponding PBRER topic found): ${mapping.unmatched_workbooks.join(", ")}<//>
    `}

    <button class="btn" disabled=${recomputing} onClick=${applyAndRecompute}>
      ${recomputing ? html`<${Spinner} label="Re-running Calculation Planning Agent + calculation engine..." />` : "Apply corrections and re-run calculations"}
    </button>
  `;
}
