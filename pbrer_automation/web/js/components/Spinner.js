import { html } from "../html.js";

export default function Spinner({ label }) {
  return html`<span><span class="spinner"></span>${label || "Loading..."}</span>`;
}
