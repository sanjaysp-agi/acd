// Thin fetch() wrappers -- one per backend endpoint. No npm, no axios:
// the browser's native fetch/EventSource cover everything this needs.
const BASE = "/api/runs";

async function asJson(res) {
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* non-JSON error body */ }
    throw new Error(detail);
  }
  return res.json();
}

export function createRun({ docxFile, excelFiles, reportingStart, reportingEnd }) {
  const fd = new FormData();
  fd.append("docx_file", docxFile);
  for (const f of excelFiles) fd.append("excel_files", f);
  fd.append("reporting_start", reportingStart);
  fd.append("reporting_end", reportingEnd);
  return fetch(BASE, { method: "POST", body: fd }).then(asJson);
}

export function listRuns() {
  return fetch(BASE).then(asJson);
}

export function getRunStatus(runId) {
  return fetch(`${BASE}/${runId}/status`).then(asJson);
}

export function getRun(runId) {
  return fetch(`${BASE}/${runId}`).then(asJson);
}

export function getTrace(runId) {
  return fetch(`${BASE}/${runId}/trace`).then(asJson);
}

export function recomputeTopicMapping(runId, rows) {
  return fetch(`${BASE}/${runId}/topic-mapping/recompute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rows }),
  }).then(asJson);
}

export function eventsUrl(runId) {
  return `${BASE}/${runId}/events`;
}

export function downloadUrl(runId, artifact) {
  return `${BASE}/${runId}/downloads/${artifact}`;
}
