import { html } from "../html.js";

export default function Banner({ kind = "info", children }) {
  return html`<div class="banner ${kind}">${children}</div>`;
}

export function NoRunBanner() {
  return html`<${Banner} kind="info">Run the pipeline first (Upload Documents).<//>`;
}
