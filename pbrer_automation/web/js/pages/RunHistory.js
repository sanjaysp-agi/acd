import { React, html } from "../html.js";
import { listRuns } from "../api.js";
import Spinner from "../components/Spinner.js";
import Banner from "../components/Banner.js";

// New page: picking up `run_manager.list_past_runs()`, which existed in
// the old backend but had no frontend surface -- once a run's full result
// is persisted (see run_store.py), reloading a past run is just setting
// the active run_id.
export default function RunHistory({ runId, setRunId, navigate }) {
  const [runs, setRuns] = React.useState(null);

  React.useEffect(() => {
    listRuns().then(setRuns);
  }, []);

  if (runs === null) return html`<h2>Run History</h2><${Spinner} />`;
  if (runs.length === 0) return html`<h2>Run History</h2><${Banner} kind="info">No runs yet. Go to <b>Upload Documents</b> to start one.<//>`;

  return html`
    <h2>Run History</h2>
    <table>
      <thead><tr>
        <th>Run ID</th><th>Generated at</th><th>Topics</th><th>Workbooks</th>
        <th>Metrics</th><th>Benchmark matches</th><th>Mismatches</th><th></th>
      </tr></thead>
      <tbody>
        ${runs.map((r) => html`
          <tr key=${r.run_id} style=${{ background: r.run_id === runId ? "rgba(91,141,239,.08)" : "" }}>
            <td><code>${r.run_id}</code></td>
            <td>${r.generated_at}</td>
            <td>${r.topics_found}</td>
            <td>${r.workbooks_found}</td>
            <td>${r.metrics_calculated}</td>
            <td>${r.benchmark_matches}</td>
            <td>${r.benchmark_mismatches}</td>
            <td><button class="btn secondary" onClick=${() => { setRunId(r.run_id); navigate("Dashboard"); }}>Load</button></td>
          </tr>
        `)}
      </tbody>
    </table>
  `;
}
