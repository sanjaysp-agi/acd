import { React, html } from "../html.js";
import { createRun } from "../api.js";
import Banner from "../components/Banner.js";

// The only place real inputs enter the app (prompt.md): the previous/
// approved PBRER, the current data exports, and the reporting interval.
// No AWS/Bedrock configuration exposed here. Starting a run hands off to
// the Run Processing module rather than rendering progress inline.
export default function UploadSources({ setPendingRunId, navigate }) {
  const [docxFile, setDocxFile] = React.useState(null);
  const [excelFiles, setExcelFiles] = React.useState([]);
  const [start, setStart] = React.useState("2019-04-07");
  const [end, setEnd] = React.useState("2024-04-06");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState(null);

  const canRun = docxFile && excelFiles.length > 0 && !submitting;

  const runPipeline = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const { run_id } = await createRun({ docxFile, excelFiles, reportingStart: start, reportingEnd: end });
      setPendingRunId(run_id);
      navigate("Run Processing");
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  return html`
    <div class="page-head">
      <div>
        <h2>Upload Sources</h2>
        <p class="caption">Previous/approved PBRER document, current data exports, and the reporting interval -- the only inputs this application needs.</p>
      </div>
    </div>

    ${error && html`<${Banner} kind="error">${error}<//>`}

    <div class="card">
      <div class="field">
        <label>Previous/approved PBRER (.docx, .pdf, or .txt)</label>
        <input type="file" accept=".docx,.pdf,.txt" onChange=${(e) => setDocxFile(e.target.files[0] || null)} />
      </div>
      <div class="field">
        <label>Data exports (all-case, all-drug-event, and any topic-specific case/drug-event pairs -- .xlsx, .xls, or .csv)</label>
        <input type="file" accept=".xlsx,.xls,.csv" multiple onChange=${(e) => setExcelFiles(Array.from(e.target.files))} />
      </div>
      <div class="card-row">
        <div class="field"><label>Reporting start date</label><input type="date" value=${start} onInput=${(e) => setStart(e.target.value)} /></div>
        <div class="field"><label>Reporting end date</label><input type="date" value=${end} onInput=${(e) => setEnd(e.target.value)} /></div>
      </div>
      <${Banner} kind="info">Both reporting-period boundaries are treated as inclusive.<//>

      <button class="btn" disabled=${!canRun} onClick=${runPipeline}>
        ${submitting ? "Starting..." : "Start processing"}
      </button>

      ${!canRun && !submitting && html`
        <p class="caption">Upload both the PBRER document and at least one data export to enable the run.</p>
      `}
    </div>
  `;
}
