import { React } from "./html.js";
import { getRun } from "./api.js";

// Mirrors the old Streamlit app's single `pipeline_result` session dict:
// each page independently loads the full run result (one small local JSON
// read on the server, no reason to share a cache across pages for a POC).
export function useRun(runId, refreshKey) {
  const [state, setState] = React.useState({ data: null, loading: !!runId, error: null });

  React.useEffect(() => {
    if (!runId) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    getRun(runId)
      .then((data) => { if (!cancelled) setState({ data, loading: false, error: null }); })
      .catch((error) => { if (!cancelled) setState({ data: null, loading: false, error: error.message }); });
    return () => { cancelled = true; };
  }, [runId, refreshKey]);

  return state;
}
