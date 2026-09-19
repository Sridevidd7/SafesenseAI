/**
 * api.ts — Typed HTTP client for the SafeSense AI FastAPI backend.
 *
 * All calls go through the Vite dev-server proxy:
 *   /api/* → http://localhost:8000/api/*
 *
 * No mock data. No hardcoded values. Every function returns typed data
 * from the real backend.
 */

// ─── Response types (mirror backend Pydantic schemas) ────────────────────────

export interface DashboardStats {
  total_reports:         number;
  sif_count:             number;
  non_sif_count:         number;
  critical_count?:       number;
  high_risk_count?:      number;
  sif_percentage:        number;
  risk_distribution:     Record<string, number>;   // { CRITICAL: n, HIGH: n, ... }
  category_distribution: Record<string, number>;   // { "Confined Space": n, ... }
  avg_risk_score:        number;
  top_category:          string;
  top_risk_level:        string;
}

export interface TrendPoint {
  month:    string;
  total:    number;
  sif:      number;
  critical: number;
}

export interface ApiReport {
  report_id:     string;
  id?:           string | number;
  description:   string;
  category:      string;
  risk_score:    number;
  sif_potential: string;   // "YES" | "NO"
  risk_level:    string;   // "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
  date?:         string | null;
  created_at?:   string | null;
}

export interface ReportsListResponse {
  total:   number;
  reports: ApiReport[];
}

export interface UploadResult {
  inserted:           number;
  duplicates:         number;
  total:              number;
  filename?:          string;
  total_rows?:        number;
  processed?:         number;
  duplicates_skipped?: number;
  file_duplicate?:    boolean;
  message?:           string;
  skipped?:           number;
  skipped_reasons?:   string[];
  sif_count?:         number;
  risk_summary?:      Record<string, number>;
  description_column?: string;
  sample?: Array<{
    row_index:     number;
    saved_id:      string;
    report_id?:    string;
    description:   string;
    category:      string;
    risk_score:    number;
    risk_level:    string;
    sif_potential: string;
    date?:         string;
  }>;
}

// ─── Base fetch wrapper ───────────────────────────────────────────────────────

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore parse error — use status code message
    }
    throw new Error(detail);
  }

  return res.json() as Promise<T>;
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

/**
 * GET /api/dashboard/stats or /api/dashboard/summary
 * Returns aggregated metrics from the reports table.
 */
export async function fetchDashboardStats(): Promise<DashboardStats> {
  return apiFetch<DashboardStats>('/dashboard/summary');
}

export const fetchDashboardSummary = fetchDashboardStats;

/**
 * GET /api/risk-intelligence/trends
 * Returns time-series monthly trend aggregated in SQLite.
 */
export async function fetchRiskIntelligenceTrends(): Promise<TrendPoint[]> {
  return apiFetch<TrendPoint[]>('/risk-intelligence/trends');
}

/**
 * POST /api/admin/reset-db
 * Hard resets the database and clears caches.
 */
export async function resetDatabase(): Promise<{ status: string }> {
  return apiFetch<{ status: string }>('/admin/reset-db', {
    method: 'POST',
  });
}

// ─── Reports ─────────────────────────────────────────────────────────────────

export interface FetchReportsParams {
  search?:     string;
  risk_level?: string;
  limit?:      number;
  offset?:     number;
}

/**
 * GET /api/reports
 * Returns stored reports with optional search, risk_level filter, and pagination.
 */
export async function fetchReports(params?: FetchReportsParams): Promise<ReportsListResponse> {
  const query = new URLSearchParams();
  if (params?.search) query.set('search', params.search);
  if (params?.risk_level) query.set('risk_level', params.risk_level);
  if (params?.limit !== undefined) query.set('limit', String(params.limit));
  if (params?.offset !== undefined) query.set('offset', String(params.offset));
  const qs = query.toString() ? `?${query.toString()}` : '';
  return apiFetch<ReportsListResponse>(`/reports${qs}`);
}

export interface AnalyzeReportPayload {
  report_text?:      string;
  description?:      string;
  activity?:         string;
  severity?:         string;
  report_type?:      string;
  life_saving_rule?: string;
  barrier_failure?:  string;
}

/**
 * POST /api/analyze-report
 * Run the HSE rule engine on a specific report observation.
 */
export async function analyzeReportApi(payload: AnalyzeReportPayload): Promise<any> {
  return apiFetch<any>('/analyze-report', {
    method: 'POST',
    body:   JSON.stringify(payload),
  });
}

/**
 * POST /api/reports
 * Analyze and persist a single text description.
 */
export async function createReport(description: string): Promise<ApiReport> {
  return apiFetch<ApiReport>('/reports', {
    method:  'POST',
    body:    JSON.stringify({ description }),
  });
}

// ─── CSV Upload ───────────────────────────────────────────────────────────────

/**
 * POST /api/reports/upload
 * Upload a CSV or Excel file. Every row is analyzed and saved to the DB.
 * Returns processing statistics and a 5-row sample.
 *
 * Uses FormData (multipart) — do NOT set Content-Type header manually,
 * the browser sets it with the correct boundary.
 */
export async function uploadReportsCSV(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append('file', file, file.name);

  const res = await fetch('/api/reports/upload', {
    method: 'POST',
    body:   form,
    // No Content-Type header — browser adds multipart boundary automatically
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }

  return res.json() as Promise<UploadResult>;
}

// ─── Corrective Actions ───────────────────────────────────────────────────────

export interface ActionItem {
  id:          number;
  report_id:   number | null;
  description: string;
  owner:       string;
  status:      'OPEN' | 'IN_PROGRESS' | 'COMPLETED' | string;
  deadline:    string | null;
  created_at?: string | null;
}

export interface CreateActionPayload {
  report_id?:   number | null;
  description: string;
  owner:       string;
  status?:     string;
  deadline?:   string | null;
}

export interface UpdateActionPayload {
  report_id?:   number | null;
  description?: string;
  owner?:       string;
  status?:      string;
  deadline?:    string | null;
}

/**
 * GET /api/actions
 * Fetch all corrective actions from the database.
 */
export async function fetchActions(): Promise<ActionItem[]> {
  return apiFetch<ActionItem[]>('/actions');
}

/**
 * GET /api/actions/{report_id}
 * Fetch corrective actions for a specific safety report.
 */
export async function fetchActionsByReport(reportId: number): Promise<ActionItem[]> {
  return apiFetch<ActionItem[]>(`/actions/${reportId}`);
}

/**
 * POST /api/actions
 * Create a new corrective action in the database.
 */
export async function createAction(payload: CreateActionPayload): Promise<ActionItem> {
  return apiFetch<ActionItem>('/actions', {
    method: 'POST',
    body:   JSON.stringify(payload),
  });
}

/**
 * PATCH /api/actions/{id}
 * Update status or fields of an existing corrective action.
 */
export async function updateAction(id: number, payload: UpdateActionPayload): Promise<ActionItem> {
  return apiFetch<ActionItem>(`/actions/${id}`, {
    method: 'PATCH',
    body:   JSON.stringify(payload),
  });
}

// ─── Human-in-the-Loop (HITL) Reviews ─────────────────────────────────────────

export interface ReviewItem {
  id:         number;
  report_id:  number;
  decision:   'CONFIRMED' | 'CORRECTED' | 'REJECTED' | string;
  comment:    string | null;
  reviewer:   string;
  created_at: string;
}

export interface CreateReviewPayload {
  report_id: number;
  decision:  string;
  comment?:  string | null;
  reviewer?: string;
}

/**
 * GET /api/reviews/{report_id}
 * Fetch all audit review decisions for a safety report.
 */
export async function fetchReviewsByReport(reportId: number): Promise<ReviewItem[]> {
  return apiFetch<ReviewItem[]>(`/reviews/${reportId}`);
}

/**
 * POST /api/reviews
 * Record a new human review decision in the database.
 */
export async function createReview(payload: CreateReviewPayload): Promise<ReviewItem> {
  return apiFetch<ReviewItem>('/reviews', {
    method: 'POST',
    body:   JSON.stringify(payload),
  });
}

// ─── LLM Explanation & Observability ──────────────────────────────────────────

export interface LlmExplanationResponse {
  root_cause:           string;
  risk_explanation:     string;
  potential_consequence: string;
  recommended_actions:  string[];
  source:               'llm_verified' | 'fallback_rule_based' | string;
  explanation_source?:  string;
  validation_passed:    boolean;
  validation_reason:    string;
  model_used?:          string;
  cached:               boolean;
}

/**
 * GET /api/reports/{id}/explain or POST /api/reports/explain
 * Fetch grounded LLM explanation with observability metadata.
 */
export async function fetchReportExplanation(reportId?: string | number, reportData?: any): Promise<LlmExplanationResponse> {
  if (reportId) {
    return apiFetch<LlmExplanationResponse>(`/reports/${reportId}/explain`);
  }
  return apiFetch<LlmExplanationResponse>('/reports/explain', {
    method: 'POST',
    body:   JSON.stringify(reportData || {}),
  });
}

// ─── Analytics, Patterns, Sites & Command Center ──────────────────────────────

export interface PatternItem {
  category:     string;
  count:        number;
  name?:        string;
  description?: string;
  frequency?:   number;
  risk_level?:  'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | string;
  sites?:       string[];
  trend?:       'increasing' | 'stable' | 'decreasing' | string;
}

export interface SiteRiskItem {
  site:                 string;
  total:                number;
  critical:             number;
  sif:                  number;
  risk_score:           number;
  risk_level:           'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | string;
  top_precursor?:       string;
  top_barrier_failure?: string;
}

export interface ActivityRiskItem {
  activity:             string;
  total:                number;
  critical:             number;
  sif:                  number;
  risk_score:           number;
  risk_level:           'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | string;
  top_barrier_failure?: string;
}

export interface CommandCenterData {
  total_reports:         number;
  critical_alerts:       number;
  sif_potential:         number;
  high_risk_sites:       number;
  rising_precursors:     number;
  open_actions:          number;
  early_warnings_count:  number;
  high_priority_reports: ApiReport[];
}

export interface DebugCounts {
  total_reports: number;
  with_category: number;
  with_site:     number;
  with_activity: number;
}

export async function fetchAnalyticsPatterns(): Promise<PatternItem[]> {
  return apiFetch<PatternItem[]>('/analytics/patterns');
}

export async function fetchAnalyticsSites(): Promise<SiteRiskItem[]> {
  return apiFetch<SiteRiskItem[]>('/analytics/sites');
}

export async function fetchAnalyticsActivities(): Promise<ActivityRiskItem[]> {
  return apiFetch<ActivityRiskItem[]>('/analytics/activities');
}

export async function fetchCommandCenterData(): Promise<CommandCenterData> {
  return apiFetch<CommandCenterData>('/analytics/command-center');
}

export async function fetchDebugCounts(): Promise<DebugCounts> {
  return apiFetch<DebugCounts>('/debug/count');
}
