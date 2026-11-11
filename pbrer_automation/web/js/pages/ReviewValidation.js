import { React, html } from "../html.js";
import { useRun } from "../useRun.js";
import Spinner from "../components/Spinner.js";
import Banner, { NoRunBanner } from "../components/Banner.js";
import Tabs from "../components/Tabs.js";
import TableList from "../components/review/TableList.js";
import TablePreview from "../components/review/TablePreview.js";
import SourceCitations from "../components/review/SourceCitations.js";
import ValidationFindings from "../components/review/ValidationFindings.js";
import ReviewerComments from "../components/review/ReviewerComments.js";
import { groupMetricsBySection } from "../lib/businessMetrics.js";

const TABS = [
  { key: "citations", label: "Source Citations" },
  { key: "findings", label: "Validation Findings" },
  { key: "comments", label: "Reviewer Comments" },
];

// 3-pane reviewer workspace: generated tables (left), the selected table's
// figures (center), and tabbed evidence/findings/comments (right) -- this
// is where every removed-from-nav technical detail (document/excel
// analysis, calculation logic, agent trace evidence) resurfaces, scoped to
// whatever the reviewer is currently looking at.
export default function ReviewValidation({ runId, refreshKey, invalidate }) {
  const { data, loading, error } = useRun(runId, refreshKey);
  const [selectedKey, setSelectedKey] = React.useState(null);
  const [rightTab, setRightTab] = React.useState("citations");

  // Topics with no matching workbook never produced a metric_result, so
  // they'd otherwise be unreachable here -- surface them as empty rows so
  // their "Fix data source mapping" action (in Validation Findings) is
  // actually reachable, not just mentioned in a Dashboard banner.
  const metricGroups = data ? groupMetricsBySection(data.metric_results) : [];
  const unmatchedGroups = data
    ? data.topic_mapping.mappings
        .filter((m) => !metricGroups.some((g) => g.key === (m.pbrer_section_number || "total")))
        .map((m) => ({ key: m.pbrer_section_number || "total", section: m.pbrer_section_number, heading: m.pbrer_heading, metrics: [] }))
    : [];
  const groups = [...metricGroups, ...unmatchedGroups].sort((a, b) => a.key.localeCompare(b.key, undefined, { numeric: true }));

  React.useEffect(() => {
    if (groups.length > 0 && !groups.some((g) => g.key === selectedKey)) {
      setSelectedKey(groups[0].key);
    }
  }, [data]);

  if (!runId) return html`<h2>Review & Validation</h2><${NoRunBanner} />`;
  if (loading) return html`<h2>Review & Validation</h2><${Spinner} />`;
  if (error) return html`<h2>Review & Validation</h2><${Banner} kind="error">${error}<//>`;
  if (!data) return html`<h2>Review & Validation</h2>`;

  const selected = groups.find((g) => g.key === selectedKey) || null;

  return html`
    <div class="page-head">
      <div>
        <h2>Review & Validation</h2>
        <p class="caption">Review each generated Section 16.3 table against its source citations and validation findings.</p>
      </div>
    </div>

    <div class="review-layout">
      <div class="review-pane">
        <div class="pane-head">Generated tables</div>
        <div class="pane-body"><${TableList} groups=${groups} selectedKey=${selectedKey} onSelect=${setSelectedKey} /></div>
      </div>
      <div class="review-pane">
        <div class="pane-head">Table preview</div>
        <div class="pane-body"><${TablePreview} group=${selected} /></div>
      </div>
      <div class="review-pane">
        <${Tabs} tabs=${TABS} active=${rightTab} onChange=${setRightTab}>
          ${(tab) => (
            tab === "citations" ? html`<${SourceCitations} data=${data} group=${selected} />` :
            tab === "findings" ? html`<${ValidationFindings} data=${data} group=${selected} runId=${runId} invalidate=${invalidate} />` :
            html`<${ReviewerComments} runId=${runId} tableId=${selected ? selected.key : "none"} />`
          )}
        <//>
      </div>
    </div>
  `;
}
