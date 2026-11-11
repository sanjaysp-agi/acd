import { React, html } from "../html.js";
import { listRuns } from "../api.js";
import Spinner from "../components/Spinner.js";
import Banner from "../components/Banner.js";
import Badge from "../components/Badge.js";

// Past runs, picking up `run_manager.list_past_runs()` -- once a run's
// full result is persisted (observability/run_store.py), reloading it is
// just setting the active run_id.
export default function History({ runId, setRunId, navigate }) {
  const [runs, setRuns] = React.useState(null);

  React.useEffect(() => {
    listRuns().then(setRuns);
  }, []);

  if (runs === null) return html`<h2>History</h2><${Spinner} />`;
  if (runs.length === 0) return html`<h2>History</h2><${Banner} kind="info">No runs yet. Go to <b>Upload Sources</b> to start one.<//>`;

  return html`
    <div class="page-head">
      <div>
        <h2>History</h2>
        <p class="caption">Every past run, with its business metrics and validation outcome.</p>
      </div>
    </div>
    <table>
      <thead><tr>
        <th>Run ID</th><th>Generated at</th><th>Safety topics</th><th>Data sources</th>
        <th>Calculated values</th><th>Benchmark</th><th></th>
      </tr></thead>
      <tbody>
        ${runs.map((r) => html`
          <tr key=${r.run_id} style=${{ background: r.run_id === runId ? "rgba(91,141,239,.08)" : "" }}>
            <td><code>${r.run_id}</code></td>
            <td>${r.generated_at}</td>
            <td>${r.topics_found}</td>
            <td>${r.workbooks_found}</td>
            <td>${r.metrics_calculated}</td>
            <td>
              <${Badge} status="match" /> ${r.benchmark_matches}
              ${r.benchmark_mismatches > 0 && html` <${Badge} status="mismatch" /> ${r.benchmark_mismatches}`}
            </td>
            <td><button class="btn secondary" onClick=${() => { setRunId(r.run_id); navigate("Dashboard"); }}>Load</button></td>
          </tr>
        `)}
      </tbody>
    </table>
  `;
}
