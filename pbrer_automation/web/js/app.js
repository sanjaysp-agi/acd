import { React, ReactDOM, html } from "./html.js";
import Dashboard from "./pages/Dashboard.js";
import Upload from "./pages/Upload.js";
import DocumentAnalysis from "./pages/DocumentAnalysis.js";
import ExcelAnalysis from "./pages/ExcelAnalysis.js";
import TopicMapping from "./pages/TopicMapping.js";
import Traceability from "./pages/Traceability.js";
import CalculationReview from "./pages/CalculationReview.js";
import Results from "./pages/Results.js";
import Validation from "./pages/Validation.js";
import Downloads from "./pages/Downloads.js";
import RunHistory from "./pages/RunHistory.js";

const PAGES = [
  ["Dashboard", Dashboard],
  ["Upload Documents", Upload],
  ["Document Analysis", DocumentAnalysis],
  ["Excel Analysis", ExcelAnalysis],
  ["Topic Mapping", TopicMapping],
  ["Agent Execution & Traceability", Traceability],
  ["Calculation Review", CalculationReview],
  ["Results Dashboard", Results],
  ["Validation & Audit", Validation],
  ["Downloads", Downloads],
  ["Run History", RunHistory],
];

const RUN_ID_STORAGE_KEY = "pbrer.currentRunId";

function App() {
  const [page, setPage] = React.useState("Dashboard");
  const [runId, setRunId] = React.useState(() => localStorage.getItem(RUN_ID_STORAGE_KEY) || null);
  const [refreshKey, setRefreshKey] = React.useState(0);

  const updateRunId = (id) => {
    setRunId(id);
    if (id) localStorage.setItem(RUN_ID_STORAGE_KEY, id);
    else localStorage.removeItem(RUN_ID_STORAGE_KEY);
    setRefreshKey((k) => k + 1);
  };

  const invalidate = () => setRefreshKey((k) => k + 1);

  const PageComponent = PAGES.find(([name]) => name === page)[1];

  return html`
    <div key="sidebar" class="sidebar">
      <h1>PBRER Automation</h1>
      ${PAGES.map(([name]) => html`
        <button key=${name} class="nav-item ${name === page ? "active" : ""}" onClick=${() => setPage(name)}>
          ${name}
        </button>
      `)}
    </div>
    <div key="main" class="main">
      <${PageComponent} runId=${runId} setRunId=${updateRunId} refreshKey=${refreshKey} invalidate=${invalidate} navigate=${setPage} />
    </div>
  `;
}

ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);
