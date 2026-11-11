import { html } from "../html.js";
import { statusClass } from "./Badge.js";

// Run-status-aware pill for the top bar's "Latest Run Status" indicator --
// same ok/warn/fail color mapping as Badge, plus a label fallback for
// statuses Badge doesn't already know about (e.g. "running", "no run").
const LABELS = {
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  none: "No run yet",
};

export default function StatusPill({ status }) {
  const key = status || "none";
  const cls = key === "none" ? "warn" : statusClass(key);
  return html`<span class="badge ${cls}">${LABELS[key] || key}</span>`;
}
