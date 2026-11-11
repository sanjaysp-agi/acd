import { html } from "../html.js";

// KPI tile shared by Dashboard and Results & Exports. `sub` is an optional
// secondary line (e.g. a trend or qualifier) rendered below the value.
export default function StatCard({ label, value, sub }) {
  return html`
    <div class="stat-card">
      <div class="label">${label}</div>
      <div class="value">${value}</div>
      ${sub != null && html`<div class="sub">${sub}</div>`}
    </div>
  `;
}
