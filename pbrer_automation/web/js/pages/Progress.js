import { React, html } from "../html.js";
import { eventsUrl, getRunStatus } from "../api.js";

// Live per-stage progress while a run executes, replacing the old
// Streamlit app's single blocking spinner for the full 3-5 minute run.
// Uses the browser's built-in EventSource against the backend's SSE
// stream -- no client library needed.
export default function Progress({ runId, onDone }) {
  const [events, setEvents] = React.useState([]);
  const [status, setStatus] = React.useState("running");
  const [search, setSearch] = React.useState("");

  React.useEffect(() => {
    if (!runId) return;
    const source = new EventSource(eventsUrl(runId));
    source.onmessage = (ev) => {
      const payload = JSON.parse(ev.data);
      setEvents((prev) => [...prev, payload]);
      if (payload.event_type === "run_completed") setStatus("completed");
      if (payload.event_type === "run_failed") setStatus("failed");
    };
    source.onerror = () => {
      source.close();
      getRunStatus(runId).then((s) => setStatus(s.status)).catch(() => setStatus("failed"));
    };
    return () => source.close();
  }, [runId]);

  React.useEffect(() => {
    if (status === "completed" || status === "failed") onDone && onDone(status);
  }, [status]);

  const filtered = search
    ? events.filter((e) => JSON.stringify(e).toLowerCase().includes(search.toLowerCase()))
    : events;

  return html`
    <div class="card">
      <p>${status === "running" ? html`<span class="spinner"></span>Running Document, Excel, Topic Mapping and Calculation Planning agents...` :
          status === "completed" ? "Run complete." : "Run failed -- see messages below."}</p>
      <div class="field">
        <input type="text" placeholder="Filter live events..." value=${search} onInput=${(e) => setSearch(e.target.value)} />
      </div>
      <div style=${{ maxHeight: "320px", overflowY: "auto" }}>
        ${filtered.map((e, i) => html`
          <div class="trace-line" key=${i}>
            <b>${e.agent_name || e.event_type}</b> -- ${e.tool_name || e.event_type} ${e.message ? `: ${e.message}` : ""}
            ${e.result_summary ? html` <span class="caption">${e.result_summary}</span>` : ""}
          </div>
        `)}
      </div>
    </div>
  `;
}
