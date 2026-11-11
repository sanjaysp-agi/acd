import { React, html } from "../html.js";
import { getTrace } from "../api.js";
import Drawer from "./Drawer.js";
import Spinner from "./Spinner.js";
import Banner from "./Banner.js";

const STATUS_ICON = { success: "✅", warning: "⚠️", error: "🔴", info: "ℹ️" };

// Global audit-trail slide-over -- real agent tool-invocation events for
// the active run, available from any page via the top bar. Replaces the
// old standalone "Agent Execution & Traceability" nav item; the content is
// unchanged (same getTrace API, same per-agent grouping), only its access
// point moved.
export default function AuditTrailDrawer({ open, onClose, runId }) {
  const [events, setEvents] = React.useState(null);
  const [search, setSearch] = React.useState("");

  React.useEffect(() => {
    if (!open || !runId) return;
    setEvents(null);
    getTrace(runId).then(setEvents);
  }, [open, runId]);

  return html`
    <${Drawer} open=${open} onClose=${onClose} title="Audit trail">
      ${!runId && html`<${Banner} kind="info">No run selected.<//>`}
      ${runId && events === null && html`<${Spinner} label="Loading trace..." />`}
      ${runId && events && events.length === 0 && html`<${Banner} kind="warn">No trace events recorded for this run.<//>`}
      ${runId && events && events.length > 0 && html`
        <p class="caption">${events.length} real tool-invocation events recorded for run <code>${runId}</code>.</p>
        <div class="field">
          <input type="text" placeholder="Search events..." value=${search} onInput=${(e) => setSearch(e.target.value)} />
        </div>
        ${[...new Set(events.map((e) => e.agent_name))].sort().map((agentName) => {
          const searchLower = search.toLowerCase();
          const agentEvents = events.filter(
            (e) => e.agent_name === agentName && (!searchLower || JSON.stringify(e).toLowerCase().includes(searchLower))
          );
          if (agentEvents.length === 0) return null;
          return html`
            <details key=${agentName} class="card">
              <summary><b>${agentName}</b> — ${agentEvents.length} events</summary>
              ${agentEvents.map((e, i) => html`
                <div key=${i} class="trace-line">
                  ${STATUS_ICON[e.status] || ""} <code>${e.event_type}</code>${e.tool_name ? html` — <b>${e.tool_name}</b>` : ""}
                  ${e.result_summary && html`<div class="caption">result: ${e.result_summary}</div>`}
                  ${e.message && html`<div class="caption">${e.message}</div>`}
                </div>
              `)}
            </details>
          `;
        })}
      `}
    <//>
  `;
}
