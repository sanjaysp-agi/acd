import { React, html } from "../html.js";
import { eventsUrl, getRunStatus } from "../api.js";
import Banner from "../components/Banner.js";

// Live per-stage progress while a run executes. The primary view is a
// friendly 4-stage stepper (derived from real agent_started/agent_completed
// trace events -- see agents/base.py); the raw technical event feed is kept
// available in a collapsed section for audit transparency, not as the main
// view. Uses the browser's built-in EventSource against the backend's SSE
// stream -- no client library needed.
const STAGES = [
  { key: "document", title: "Document Intake", agents: ["document_understanding_agent"] },
  { key: "sources", title: "Data Source Analysis", agents: ["excel_understanding_agent"] },
  { key: "mapping", title: "Topic Mapping", agents: ["topic_mapping_agent"] },
  { key: "calc", title: "Calculation & Validation", agents: ["calculation_planning_agent", "extraction_review_agent"] },
];

function stageState(stage, events, runFailed) {
  const relevant = events.filter((e) => stage.agents.includes(e.agent_name));
  if (relevant.length === 0) return "pending";
  const done = stage.agents.every((a) => relevant.some((e) => e.agent_name === a && e.event_type === "agent_completed"));
  if (done) return "done";
  if (runFailed && relevant.some((e) => e.event_type === "warning" || e.status === "error")) return "failed";
  return "active";
}

export default function RunProcessing({ pendingRunId, runId, setRunId, setPendingRunId, navigate }) {
  const effectiveRunId = pendingRunId || runId;
  const [events, setEvents] = React.useState([]);
  const [status, setStatus] = React.useState(pendingRunId ? "running" : "idle");
  const [search, setSearch] = React.useState("");

  React.useEffect(() => {
    if (!pendingRunId) { setStatus(runId ? "completed" : "idle"); return; }
    setEvents([]);
    setStatus("running");
    const source = new EventSource(eventsUrl(pendingRunId));
    source.onmessage = (ev) => {
      const payload = JSON.parse(ev.data);
      setEvents((prev) => [...prev, payload]);
      if (payload.event_type === "run_completed") setStatus("completed");
      if (payload.event_type === "run_failed") setStatus("failed");
    };
    source.onerror = () => {
      source.close();
      getRunStatus(pendingRunId).then((s) => setStatus(s.status)).catch(() => setStatus("failed"));
    };
    return () => source.close();
  }, [pendingRunId]);

  React.useEffect(() => {
    if (pendingRunId && status === "completed") setRunId(pendingRunId);
  }, [status]);

  if (!effectiveRunId) {
    return html`
      <h2>Run Processing</h2>
      <${Banner} kind="info">
        No run in progress. Go to <a href="#" onClick=${(e) => { e.preventDefault(); navigate("Upload Sources"); }}>Upload Sources<//> to start one.
      <//>
    `;
  }

  const filtered = search
    ? events.filter((e) => JSON.stringify(e).toLowerCase().includes(search.toLowerCase()))
    : events;

  return html`
    <div class="page-head">
      <div>
        <h2>Run Processing</h2>
        <p class="caption">Document intake, data source analysis, topic mapping, calculation and validation for run <code>${effectiveRunId}</code>.</p>
      </div>
    </div>

    ${status === "failed" && html`<${Banner} kind="error">Run failed -- see the technical log below for details.<//>`}

    <div class="stepper">
      ${STAGES.map((stage) => {
        const st = stageState(stage, events, status === "failed");
        return html`
          <div key=${stage.key} class="stepper-step ${st}">
            <span class="dot"></span>
            <span class="title">${stage.title}</span>
            <span class="state">${{ pending: "Pending", active: "In progress", done: "Done", failed: "Failed" }[st]}</span>
          </div>
        `;
      })}
    </div>

    <div class="card">
      ${status === "running" && html`<p><span class="spinner"></span>Processing -- this typically takes 15-20 minutes.</p>`}
      ${status === "completed" && html`
        <p>Processing complete. ${pendingRunId ? "" : "(Showing the last completed run.)"}</p>
        <button class="btn" onClick=${() => { setPendingRunId(null); navigate("Review & Validation"); }}>Review results</button>
      `}
      ${status === "failed" && html`
        <button class="btn secondary" onClick=${() => { setPendingRunId(null); navigate("Upload Sources"); }}>Back to Upload Sources</button>
      `}

      <details>
        <summary>Technical log (${events.length} events)</summary>
        <div class="field">
          <input type="text" placeholder="Filter log..." value=${search} onInput=${(e) => setSearch(e.target.value)} />
        </div>
        <div style=${{ maxHeight: "320px", overflowY: "auto" }}>
          ${filtered.map((e, i) => html`
            <div class="trace-line" key=${i}>
              <b>${e.agent_name || e.event_type}</b> -- ${e.tool_name || e.event_type}${e.message ? `: ${e.message}` : ""}
              ${e.result_summary ? html` <span class="caption">${e.result_summary}</span>` : ""}
            </div>
          `)}
        </div>
      </details>
    </div>
  `;
}
