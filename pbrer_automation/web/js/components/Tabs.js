import { React, html } from "../html.js";

// Controlled tab strip. `tabs` = [{key, label}]; renders only the active
// panel's children (passed as a render function keyed by tab key).
export default function Tabs({ tabs, active, onChange, children }) {
  return html`
    <div>
      <div class="tabs" role="tablist">
        ${tabs.map((t) => html`
          <button
            key=${t.key}
            role="tab"
            aria-selected=${t.key === active}
            class="tab-btn ${t.key === active ? "active" : ""}"
            onClick=${() => onChange(t.key)}
          >${t.label}</button>
        `)}
      </div>
      <div class="tab-panel" role="tabpanel">${children(active)}</div>
    </div>
  `;
}
