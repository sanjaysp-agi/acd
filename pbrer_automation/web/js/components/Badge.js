import { html } from "../html.js";

// Maps a status word to the ok/warn/fail CSS classes in app.css.
const OK = new Set(["ok", "match", "verified", "pass", "success", "completed"]);
const WARN = new Set(["warn", "warning", "unverified", "running"]);

export function statusClass(status) {
  const s = String(status || "").toLowerCase();
  if (OK.has(s)) return "ok";
  if (WARN.has(s)) return "warn";
  return "fail";
}

export default function Badge({ status }) {
  return html`<span class="badge ${statusClass(status)}">${status}</span>`;
}
