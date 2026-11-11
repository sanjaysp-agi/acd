import { React, ReactDOM, html } from "./html.js";
import Dashboard from "./pages/Dashboard.js";
import UploadSources from "./pages/UploadSources.js";
import RunProcessing from "./pages/RunProcessing.js";
import ReviewValidation from "./pages/ReviewValidation.js";
import ResultsExports from "./pages/ResultsExports.js";
import History from "./pages/History.js";
import StatusPill from "./components/StatusPill.js";
import AuditTrailDrawer from "./components/AuditTrailDrawer.js";

// 6 business-first modules -- internal pipeline stages (document/excel
// analysis, topic mapping, agent trace, calculation plan) are not nav
// items; their content lives inside Review & Validation and the global
// Audit Trail drawer below.
const PAGES = [
  ["Dashboard", Dashboard],
  ["Upload Sources", UploadSources],
  ["Run Processing", RunProcessing],
  ["Review & Validation", ReviewValidation],
  ["Results & Exports", ResultsExports],
  ["History", History],
];

const RUN_ID_STORAGE_KEY = "pbrer.currentRunId";
const THEME_STORAGE_KEY = "pbrer.theme";

function App() {
  const [page, setPage] = React.useState("Dashboard");
  const [runId, setRunId] = React.useState(() => localStorage.getItem(RUN_ID_STORAGE_KEY) || null);
  const [pendingRunId, setPendingRunId] = React.useState(null);
  const [refreshKey, setRefreshKey] = React.useState(0);
  const [theme, setTheme] = React.useState(() => localStorage.getItem(THEME_STORAGE_KEY) || "dark");
  const [auditOpen, setAuditOpen] = React.useState(false);

  React.useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  const updateRunId = (id) => {
    setRunId(id);
    if (id) localStorage.setItem(RUN_ID_STORAGE_KEY, id);
    else localStorage.removeItem(RUN_ID_STORAGE_KEY);
    setRefreshKey((k) => k + 1);
  };

  const invalidate = () => setRefreshKey((k) => k + 1);

  const PageComponent = PAGES.find(([name]) => name === page)[1];
  const activeRunId = pendingRunId || runId;
  const status = pendingRunId ? "running" : runId ? "completed" : "none";

  return html`
    <div key="topbar" class="topbar">
      <span class="brand">PBRER Section 16.3 Automation</span>
      <${StatusPill} status=${status} />
      <span class="spacer"></span>
      <div class="topbar-actions">
        <button class="icon-btn" disabled=${!activeRunId} onClick=${() => setAuditOpen(true)}>Audit trail</button>
        <button class="icon-btn" onClick=${() => setTheme((t) => (t === "dark" ? "light" : "dark"))}>
          ${theme === "dark" ? "Light mode" : "Dark mode"}
        </button>
      </div>
    </div>
    <div key="body" class="app-body">
      <div key="sidebar" class="sidebar">
        <div class="nav-label">Modules</div>
        ${PAGES.map(([name]) => html`
          <button key=${name} class="nav-item ${name === page ? "active" : ""}" onClick=${() => setPage(name)}>
            ${name}
          </button>
        `)}
      </div>
      <div key="main" class="main">
        <${PageComponent}
          runId=${runId}
          setRunId=${updateRunId}
          pendingRunId=${pendingRunId}
          setPendingRunId=${setPendingRunId}
          refreshKey=${refreshKey}
          invalidate=${invalidate}
          navigate=${setPage}
        />
      </div>
    </div>
    <${AuditTrailDrawer} open=${auditOpen} onClose=${() => setAuditOpen(false)} runId=${activeRunId} />
  `;
}

ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);
