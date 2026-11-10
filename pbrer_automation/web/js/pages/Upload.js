import { React, html } from "../html.js";
import { createRun } from "../api.js";
import Banner from "../components/Banner.js";
import Progress from "./Progress.js";

// The only place real inputs enter the app (prompt.md): the previous/
// approved PBRER, the current Excel exports, and the reporting interval.
// No AWS/Bedrock configuration exposed here.
export default function Upload({ setRunId, invalidate, navigate }) {
  const [docxFile, setDocxFile] = React.useState(null);
  const [excelFiles, setExcelFiles] = React.useState([]);
  const [start, setStart] = React.useState("2019-04-07");
  const [end, setEnd] = React.useState("2024-04-06");
  const [activeRunId, setActiveRunId] = React.useState(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState(null);

  const canRun = docxFile && excelFiles.length > 0 && !submitting && !activeRunId;

  const runPipeline = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const { run_id } = await createRun({ docxFile, excelFiles, reportingStart: start, reportingEnd: end });
      setActiveRunId(run_id);
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const onDone = (status) => {
    if (status === "completed") {
      setRunId(activeRunId);
    }
    invalidate();
  };

  return html`
    <h2>Upload Documents</h2>
    <p class="caption">Previous/approved PBRER, current Excel exports, and the reporting interval -- the only inputs this application needs.</p>

    ${error && html`<${Banner} kind="error">${error}<//>`}

    ${!activeRunId && html`
      <div class="field">
        <label>Previous/approved PBRER (.docx)</label>
        <input type="file" accept=".docx" onChange=${(e) => setDocxFile(e.target.files[0] || null)} />
      </div>
      <div class="field">
        <label>Excel exports (all-case, all-drug-event, and any topic-specific case/drug-event pairs)</label>
        <input type="file" accept=".xlsx" multiple onChange=${(e) => setExcelFiles(Array.from(e.target.files))} />
      </div>
      <div class="card-row">
        <div class="field"><label>Reporting start date</label><input type="date" value=${start} onInput=${(e) => setStart(e.target.value)} /></div>
        <div class="field"><label>Reporting end date</label><input type="date" value=${end} onInput=${(e) => setEnd(e.target.value)} /></div>
      </div>
      <${Banner} kind="info">Both reporting-period boundaries are treated as inclusive.<//>

      <button class="btn" disabled=${!canRun} onClick=${runPipeline}>
        ${submitting ? "Starting..." : "Run pipeline"}
      </button>

      ${!canRun && !submitting && html`
        <p class="caption">Upload both the PBRER document and at least one Excel export to enable the run.</p>
      `}
    `}

    ${activeRunId && html`
      <${Progress} runId=${activeRunId} onDone=${onDone} />
      <button class="btn secondary" onClick=${() => navigate("Dashboard")}>Go to Dashboard</button>
    `}
  `;
}
