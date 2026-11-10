import { React, html } from "../html.js";
import { getTrace } from "../api.js";
import Spinner from "../components/Spinner.js";
import Banner, { NoRunBanner } from "../components/Banner.js";

const STATUS_ICON = { success: "✅", warning: "⚠️", error: "🔴", info: "ℹ️" };

export default function Traceability({ runId, refreshKey }) {
  const [events, setEvents] = React.useState(null);
  const [loading, setLoading] = React.useState(!!runId);
  const [search, setSearch] = React.useState("");
  const [chosenAgents, setChosenAgents] = React.useState(null);

  React.useEffect(() => {
    if (!runId) { setEvents(null); return; }
    setLoading(true);
    getTrace(runId).then((data) => {
      setEvents(data);
      setChosenAgents(new Set(data.map((e) => e.agent_name)));
      setLoading(false);
    });
  }, [runId, refreshKey]);

  if (!runId) return html`<h2>Agent Execution &amp; Traceability</h2><${NoRunBanner} />`;
  if (loading) return html`<h2>Agent Execution &amp; Traceability</h2><${Spinner} />`;
  if (!events || events.length === 0) return html`<h2>Agent Execution &amp; Traceability</h2><${Banner} kind="warn">No trace events recorded for this run.<//>`;

  const agents = [...new Set(events.map((e) => e.agent_name))].sort();
  const searchLower = search.toLowerCase();
  const matchesSearch = (e) => !searchLower || JSON.stringify(e).toLowerCase().includes(searchLower);

  const toggleAgent = (agent) => {
    const next = new Set(chosenAgents);
    next.has(agent) ? next.delete(agent) : next.add(agent);
    setChosenAgents(next);
  };

  return html`
    <h2>Agent Execution &amp; Traceability</h2>
    <p class="caption">${events.length} real tool-invocation events recorded for run <code>${runId}</code>. This is the agents' actual execution log, not a simulated timeline.</p>

    <div class="field">
      <label>Filter by agent</label>
      <div class="card-row">
        ${agents.map((a) => html`
          <label key=${a} style=${{ fontSize: "13px" }}>
            <input type="checkbox" checked=${chosenAgents.has(a)} onChange=${() => toggleAgent(a)} /> ${a}
          </label>
        `)}
      </div>
    </div>
    <div class="field">
      <input type="text" placeholder="Search events..." value=${search} onInput=${(e) => setSearch(e.target.value)} />
    </div>

    ${agents.filter((a) => chosenAgents.has(a)).map((agentName) => {
      const agentEvents = events.filter((e) => e.agent_name === agentName && matchesSearch(e));
      if (agentEvents.length === 0) return null;
      return html`
        <details key=${agentName} class="card">
          <summary><b>${agentName}</b> -- ${agentEvents.length} events</summary>
          ${agentEvents.map((e, i) => html`
            <div key=${i} class="trace-line">
              ${STATUS_ICON[e.status] || ""} <code>${e.event_type}</code>${e.tool_name ? html` -- <b>${e.tool_name}</b>` : ""}
              ${e.arguments_redacted && Object.keys(e.arguments_redacted).length > 0 && html`<div class="caption">args: ${JSON.stringify(e.arguments_redacted)}</div>`}
              ${e.result_summary && html`<div class="caption">result: ${e.result_summary}</div>`}
              ${e.message && html`<div class="caption">${e.message}</div>`}
            </div>
          `)}
        </details>
      `;
    })}
  `;
}
