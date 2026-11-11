import { html } from "../html.js";

// Slide-over panel used for the global Audit Trail. Closes on overlay
// click or the close button; `open` gates whether anything renders.
export default function Drawer({ open, title, onClose, children }) {
  if (!open) return null;
  return html`
    <div key="overlay" class="drawer-overlay" onClick=${onClose}></div>
    <div key="panel" class="drawer-panel" role="dialog" aria-label=${title}>
      <div class="drawer-head">
        <h3>${title}</h3>
        <button class="drawer-close" onClick=${onClose} aria-label="Close"><span aria-hidden="true">&times;</span></button>
      </div>
      <div class="drawer-body">${children}</div>
    </div>
  `;
}
