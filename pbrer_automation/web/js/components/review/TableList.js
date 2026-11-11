import { html } from "../../html.js";
import { sectionStatus } from "../../lib/businessMetrics.js";
import { statusClass } from "../Badge.js";

// Left panel of Review & Validation: one row per generated Section 16.3
// table (topic), with a rollup status badge -- failed > warning >
// unverified > verified, most-severe-wins (see businessMetrics.sectionStatus).
export default function TableList({ groups, selectedKey, onSelect }) {
  if (groups.length === 0) return html`<p class="caption">No tables generated for this run.</p>`;
  return html`
    <div>
      ${groups.map((g) => {
        const status = sectionStatus(g.metrics);
        return html`
          <button key=${g.key} class="table-list-item ${g.key === selectedKey ? "active" : ""}" onClick=${() => onSelect(g.key)}>
            <span>
              <span class="section-tag">${g.section || "Total"}</span><br/>
              ${g.heading}
            </span>
            <span class="badge ${statusClass(status)}">${status}</span>
          </button>
        `;
      })}
    </div>
  `;
}
