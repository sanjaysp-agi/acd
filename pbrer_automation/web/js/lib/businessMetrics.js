// Pure functions deriving every business-facing KPI from one `GET
// /api/runs/{id}` payload -- kept in one place so Dashboard, Review &
// Validation and Results & Exports never compute the same number two
// different ways.

export function documentsUploaded(result) {
  const workbooks = result?.workbook_inventory?.workbooks?.length || 0;
  return 1 + workbooks; // the previous/approved PBRER + every data export
}

export function safetyTopicsExtracted(result) {
  return result?.document_structure?.topics?.length || 0;
}

// One "generated table" per distinct Section 16.3 topic that produced at
// least one calculated metric -- same grouping the old Results page used.
export function groupMetricsBySection(metricResults) {
  const byKey = new Map();
  for (const mr of metricResults || []) {
    const key = mr.pbrer_section_number || "total";
    if (!byKey.has(key)) {
      byKey.set(key, { key, section: mr.pbrer_section_number, heading: mr.topic_heading || "All post-marketing cases", metrics: [] });
    }
    byKey.get(key).metrics.push(mr);
  }
  return [...byKey.values()].sort((a, b) => a.key.localeCompare(b.key, undefined, { numeric: true }));
}

// A serious/fatal case count is always shown as "numerator/denominator"
// (e.g. "55/242") against its topic's own case count, never a bare number
// -- mirrors generation/formatting.py's format_case_ratio, which applies
// the same rule to the Word/Excel exports.
const RATIO_NUMERATOR_METRIC_IDS = ["serious_case_count", "fatal_case_count"];
const RATIO_DENOMINATOR_METRIC_IDS = ["topic_case_count", "total_case_count"];

export function caseRatioDenominator(groupMetrics) {
  for (const id of RATIO_DENOMINATOR_METRIC_IDS) {
    const m = (groupMetrics || []).find((mr) => mr.metric_id === id);
    if (m && typeof m.calculated_value === "number") return m.calculated_value;
  }
  return null;
}

// Returns "numerator/denominator" for a serious/fatal case count metric
// when a sibling topic/total case count is present in the same group;
// returns null otherwise (never fabricates a denominator).
export function formatCaseRatio(mr, groupMetrics) {
  if (!RATIO_NUMERATOR_METRIC_IDS.includes(mr.metric_id) || typeof mr.calculated_value !== "number") return null;
  const denominator = caseRatioDenominator(groupMetrics);
  if (denominator == null) return null;
  return `${mr.calculated_value}/${denominator}`;
}

// Looks up this metric's AI confidence score (see ai_score_report in the
// pipeline result / agents/ai_scoring_agent.py), scoped to the same
// section + metric so it can never be mismatched across topics.
export function aiScoreFor(result, mr) {
  const scores = result?.ai_score_report?.scores || [];
  return scores.find((s) => s.metric_id === mr.metric_id && s.pbrer_section_number === mr.pbrer_section_number) || null;
}

export function tablesGenerated(result) {
  return groupMetricsBySection(result?.metric_results).length;
}

// Rollup status badge for one generated table (section group): failed >
// warning > unverified > verified, most-severe-wins.
export function sectionStatus(metrics) {
  if (metrics.some((m) => m.validation_status === "failed")) return "failed";
  if (metrics.some((m) => m.validation_status === "warning")) return "warning";
  if (metrics.length > 0 && metrics.every((m) => m.validation_status === "verified")) return "verified";
  return "unverified";
}

export function validationSuccessPct(result) {
  const checks = result?.validation_report?.checks || [];
  if (checks.length === 0) return null;
  const passed = checks.filter((c) => c.status === "pass").length;
  return Math.round((100 * passed) / checks.length);
}

export function pendingReviewCount(result) {
  if (!result) return 0;
  const failedMetrics = (result.metric_results || []).filter((m) => m.validation_status === "failed").length;
  const mismatches = (result.benchmark_report?.rows || []).filter((r) => r.status === "mismatch").length;
  const reviewWarnings = (result.extraction_review || []).filter((f) => f.severity === "warning").length;
  const unmatchedTopics = result.topic_mapping?.unmatched_document_topics?.length || 0;
  const unmatchedWorkbooks = result.topic_mapping?.unmatched_workbooks?.length || 0;
  const mappingsNeedingReview = (result.topic_mapping?.mappings || []).filter((m) => m.needs_review).length;
  return failedMetrics + mismatches + reviewWarnings + unmatchedTopics + unmatchedWorkbooks + mappingsNeedingReview;
}
