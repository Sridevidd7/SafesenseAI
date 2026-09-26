/// <reference types="vite/client" />
/**
 * api.ts ─ Typed HTTP client for the SafeSense AI FastAPI backend.
 *
 * All calls go through the Vite dev-server proxy:
 *   /api/* â†’ http://localhost:8000/api/*
 *
 * No mock data. No hardcoded values. Every function returns typed data
 * from the real backend.
 */

import { SifHeatmapResponse, SifHeatmapFilter } from '../types';
import { clearStoredSession, getStoredToken } from './authClient';

// â”€â”€â”€ Response types (mirror backend Pydantic schemas) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
  site?:         string;
  unit?:         string;
  area?:         string;
  activity?:     string;
  barrier_failure?: string;
  pii_detected?: boolean;
  pii_count?:    number;
  pii_types?:    string[];
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
  pii_detected_count?: number;
  risk_summary?:      Record<string, number>;
  description_column?: string;
  success?:            boolean;
  database_total?:     number;
  sample?: Array<{
    row_index:     number;
    saved_id:      string;
    report_id?:    string;
    description:   string;
    category:      string;
    risk_score:    number;
    risk_level:    string;
    sif_potential: string;
    site?:         string;
    activity?:     string;
    date?:         string;
  }>;
}

export class UploadApiError extends Error {
  status?: number;
  isAmbiguous: boolean;

  constructor(message: string, status?: number, isAmbiguous: boolean = false) {
    super(message);
    this.name = 'UploadApiError';
    this.status = status;
    this.isAmbiguous = isAmbiguous;
  }
}

export function isAmbiguousUploadError(error: unknown): boolean {
  if (error instanceof UploadApiError) {
    return error.isAmbiguous;
  }
  if (error instanceof Error) {
    const msg = error.message.toLowerCase();
    return (
      msg.includes('502') ||
      msg.includes('503') ||
      msg.includes('504') ||
      msg.includes('failed to fetch') ||
      msg.includes('network') ||
      msg.includes('temporarily unavailable') ||
      msg.includes('connection timed out')
    );
  }
  return false;
}

// â”€â”€â”€ Base fetch wrapper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const BASE_API_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '');

export function getApiUrl(path: string): string {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  const apiPath = cleanPath.startsWith('/api')
    ? cleanPath
    : `/api${cleanPath}`;

  return `${BASE_API_URL}${apiPath}`;
}

function getAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  try {
    const token = getStoredToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  } catch {
    // ignore
  }
  return headers;
}

/** Global 401 handling: discard invalid sessions and return to login. */
function handleUnauthorized(): void {
  clearStoredSession();
  if (!window.location.pathname.startsWith('/login')) {
    window.location.assign('/login?expired=1');
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const authHeaders = getAuthHeaders();
  const res = await fetch(getApiUrl(path), {
    ...init,
    headers: {
      ...authHeaders,
      ...(init?.headers as Record<string, string> || {}),
    },
  });

  if (!res.ok) {
    if (res.status === 401) {
      handleUnauthorized();
    }
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore parse error â€” use status code message
    }
    throw new Error(detail);
  }

  const json = await res.json();
  // If backend returns { data: ..., meta: ... }, extract data if present
  if (json && typeof json === 'object' && 'data' in json && json.data !== undefined) {
    return json.data as T;
  }
  return json as T;
}

// â”€â”€â”€ Dashboard â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

/**
 * GET /api/dashboard/stats or /api/dashboard/summary
 * Returns aggregated metrics from the reports table.
 */
export async function fetchDashboardStats(): Promise<DashboardStats> {
  return apiFetch<DashboardStats>('/dashboard/summary');
}

export interface PatternAnomaly {
  type:    'TEMPORAL_SPIKE' | 'SITE_CONCENTRATION_SPIKE' | string;
  site?:   string;
  anomaly?: boolean;
  ratio?:  number;
  reason?: string;
}

export interface TrendsIntelligenceResponse {
  data:         TrendPoint[];
  trend:        string;
  trend_reason: string;
  anomalies:    PatternAnomaly[];
  insights:     AIInsight[];
  meta?: {
    total_reports?: number;
    last_updated?:  string;
    source?:        string;
    is_empty?:      boolean;
  };
}

/**
 * GET /api/risk-intelligence/trends
 * Returns time-series monthly trend aggregated by the backend.
 */
export async function fetchRiskIntelligenceTrends(): Promise<TrendPoint[]> {
  return apiFetch<TrendPoint[]>('/risk-intelligence/trends');
}

/**
 * GET /api/risk-intelligence/trends (Full envelope)
 * Returns monthly trend data along with AI trend classifications, reasons, and anomalies.
 */
export async function fetchTrendsIntelligence(): Promise<TrendsIntelligenceResponse> {
  const authHeaders = getAuthHeaders();
  const res = await fetch(getApiUrl('/risk-intelligence/trends'), { headers: authHeaders });
  if (res.status === 401) handleUnauthorized();
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}



/**
 * POST /api/admin/reset-db
 * Hard resets the database and clears caches (requires confirmation flag).
 */
export async function resetDatabase(): Promise<{ status: string; total_deleted: number }> {
  return apiFetch<{ status: string; total_deleted: number }>('/admin/reset-db?confirm=true', {
    method: 'POST',
    body:   JSON.stringify({ confirm: true }),
  });
}

/**
 * POST /api/refresh-analytics
 * Force refresh analytics cache and recompute aggregations.
 */
export async function refreshAnalytics(): Promise<{ status: string; total_reports: number }> {
  return apiFetch<{ status: string; total_reports: number }>('/refresh-analytics', {
    method: 'POST',
  });
}

// â”€â”€â”€ Reports â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

  const authHeaders = getAuthHeaders();
  const res = await fetch(getApiUrl(`/reports${qs}`), { headers: authHeaders });
  if (!res.ok) {
    if (res.status === 401) handleUnauthorized();
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }

  const json = await res.json();
  if (Array.isArray(json)) {
    return { total: json.length, reports: json };
  }
  if (json && typeof json === 'object') {
    const list = Array.isArray(json.reports)
      ? json.reports
      : (Array.isArray(json.data) ? json.data : []);
    const totalCount = typeof json.total === 'number'
      ? json.total
      : list.length;
    return { total: totalCount, reports: list };
  }
  return { total: 0, reports: [] };
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

// â”€â”€â”€ CSV Upload â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

/**
 * POST /api/reports/upload
 * Upload a CSV or Excel file. Every row is analyzed and saved to the DB.
 * Returns processing statistics and a 5-row sample.
 */
export async function uploadReportsCSV(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append('file', file, file.name);

  const headers: Record<string, string> = {};
  try {
    const token = getStoredToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
  } catch {
    // ignore
  }

  let res: Response;
  try {
    res = await fetch(getApiUrl('/reports/upload'), {
      method: 'POST',
      body:   form,
      headers,
    });
  } catch {
    // Network failure, connection drop, or reverse-proxy 502 where CORS headers were omitted
    throw new UploadApiError(
      'Could not reach SafeSense backend or the upload status could not be confirmed. Check the connection and refresh before retrying.',
      undefined,
      true // ambiguous failure: database commit may already have succeeded
    );
  }

  if (!res.ok) {
    if (res.status === 401) {
      handleUnauthorized();
      throw new UploadApiError('Your session has expired. Please sign in again.', 401, false);
    }
    if (res.status === 403) {
      throw new UploadApiError('You do not have permission to upload reports.', 403, false);
    }
    if (res.status === 413) {
      throw new UploadApiError('File is too large. Maximum allowed size is 15 MB.', 413, false);
    }
    if (res.status === 429) {
      throw new UploadApiError('Too many requests. Please wait and try again.', 429, false);
    }
    if (res.status === 502 || res.status === 503 || res.status === 504) {
      throw new UploadApiError(
        'SafeSense backend is temporarily unavailable or the upload status could not be confirmed. Refresh before retrying.',
        res.status,
        true // ambiguous failure
      );
    }

    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore
    }

    if (res.status === 422) {
      throw new UploadApiError(`Upload validation failed: ${detail}`, 422, false);
    }
    if (res.status >= 500) {
      throw new UploadApiError('SafeSense backend encountered an internal error.', res.status, true);
    }

    throw new UploadApiError(detail, res.status, false);
  }

  const json = await res.json();
  if (json && typeof json === 'object' && 'data' in json && json.data !== undefined) {
    return json.data as UploadResult;
  }
  return json as UploadResult;
}

// â”€â”€â”€ Corrective Actions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export interface ActionItem {
  id:          number;
  report_id:   number | string | null;
  description: string;
  owner:       string;
  status:      'OPEN' | 'IN_PROGRESS' | 'COMPLETED' | string;
  deadline:    string | null;
  created_at?: string | null;
}

export interface CreateActionPayload {
  report_id?:   number | string | null;
  description: string;
  owner:       string;
  status?:     string;
  deadline?:   string | null;
}

export interface UpdateActionPayload {
  report_id?:   number | string | null;
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
export async function fetchActionsByReport(reportId: string | number): Promise<ActionItem[]> {
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

// â”€â”€â”€ Human-in-the-Loop (HITL) Reviews â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export interface ReviewItem {
  id:         number;
  report_id:  string | number;
  decision:   'CONFIRMED' | 'CORRECTED' | 'REJECTED' | string;
  comment:    string | null;
  reviewer:   string;
  created_at: string;
}

export interface CreateReviewPayload {
  report_id: string | number;
  decision:  string;
  comment?:  string | null;
  reviewer?: string;
}

/**
 * GET /api/reviews/{report_id}
 * Fetch all audit review decisions for a safety report.
 */
export async function fetchReviewsByReport(reportId: string | number): Promise<ReviewItem[]> {
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

// â”€â”€â”€ LLM Explanation & Observability â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

// â”€â”€â”€ Analytics, Patterns, Sites & Command Center â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export interface AIInsight {
  type:        'RECURRING_PATTERN' | 'ANOMALY' | 'CROSS_SITE_RISK' | 'TREND' | string;
  title:       string;
  message:     string;
  severity:    'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | string;
  sites?:      string[];
  site?:       string;
  metric?:     string;
  cluster_id?: string;
}

export interface PatternItem {
  cluster_id?:          string;
  theme?:               string;
  category:             string;
  barrier?:             string;
  count:                number;
  name?:                string;
  description?:         string;
  frequency?:           number;
  risk_level?:          'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | string;
  risk_score?:          number;
  avg_risk?:            number;
  sif_count?:           number;
  is_repeated?:         boolean;
  sample_descriptions?: string[];
  sites?:               string[];
  trend?:               'increasing' | 'stable' | 'decreasing' | string;
  simplified_insight?:  string;
  human_insight?:       string;
}

export interface PatternIntelligenceEnvelope {
  data:              PatternItem[];
  repeated_failures: PatternItem[];
  insights:          AIInsight[];
  meta?: {
    total_reports?: number;
    last_updated?:  string;
    source?:        string;
  };
}

export async function fetchAnalyticsPatterns(): Promise<PatternItem[]> {
  return apiFetch<PatternItem[]>('/analytics/patterns');
}

/**
 * GET /api/analytics/patterns (Full Envelope)
 * Returns clusters, repeated failures, and insights synthesized from pattern engine.
 */
export async function fetchPatternIntelligence(): Promise<PatternIntelligenceEnvelope> {
  const authHeaders = getAuthHeaders();
  const res = await fetch(getApiUrl('/analytics/patterns'), { headers: authHeaders });
  if (res.status === 401) handleUnauthorized();
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
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

export async function fetchAnalyticsInsights(): Promise<AIInsight[]> {
  return apiFetch<AIInsight[]>('/analytics/insights');
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

/**
 * GET /api/analytics/sif-heatmap
 * Fetches operational SIF risk concentration tree and reports from the safety database.
 */
export async function fetchSifHeatmap(filter?: SifHeatmapFilter): Promise<SifHeatmapResponse> {
  const query = new URLSearchParams();
  if (filter?.site) query.set('site', filter.site);
  if (filter?.unit) query.set('unit', filter.unit);
  if (filter?.area) query.set('area', filter.area);
  if (filter?.activity) query.set('activity', filter.activity);
  if (filter?.lsr) query.set('lsr', filter.lsr);
  if (filter?.barrier) query.set('barrier', filter.barrier);
  const qs = query.toString() ? `?${query.toString()}` : '';
  return apiFetch<SifHeatmapResponse>(`/analytics/sif-heatmap${qs}`);
}

// â”€â”€â”€ Safety Copilot â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export interface CopilotHistoryMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface CopilotChatPayload {
  message: string;
  history?: CopilotHistoryMessage[];
}

// Phase 3 grounding types (mirror backend schemas.py)
export interface CopilotAggregate {
  metric: string;
  value: number | string;
  scope: string;
}

export interface CopilotPatternInfo {
  pattern_id: string;
  pattern_type: string;
  description: string;
  frequency: number;
  trend?: string | null;
  sites: string[];
  activities: string[];
  barriers: string[];
  evidence_report_ids: string[];
  confidence?: number | null;
}

export interface CopilotGrounding {
  reports_examined: number;
  sif_count: number;
  date_range?: string | null;
  filters_applied: Record<string, string>;
  filters_unapplied: string[];
  aggregates: CopilotAggregate[];
  source_reports: string[];
  patterns: CopilotPatternInfo[];
  pattern_source?: string | null;
}

export interface CopilotChatResponse {
  answer: string;
  source_reports: string[];
  data_source: string;
  model: string;
  grounding?: CopilotGrounding | null;
}

/**
 * POST /api/copilot/chat
 * Sends user question to backend Safety Copilot grounded on the verified safety database (LLM synthesis via Groq).
 */
export async function sendCopilotMessage(payload: CopilotChatPayload): Promise<CopilotChatResponse> {
  return apiFetch<CopilotChatResponse>('/copilot/chat', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
