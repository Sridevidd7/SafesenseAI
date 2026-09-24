// ─── Core Types ───────────────────────────────────────────────────────────────

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type SIFPotential = 'YES' | 'NO' | 'UNKNOWN';
export type ReportType = 'Unsafe Act' | 'Unsafe Condition' | 'Near Miss' | 'Incident';

// ─── Multilingual Types ───────────────────────────────────────────────────────
export type DetectedLanguage = 'en' | 'kn' | 'hi' | 'unknown';

export const LANGUAGE_DISPLAY: Record<DetectedLanguage, string> = {
  en: 'English',
  kn: 'Kannada',
  hi: 'Hindi',
  unknown: 'Unknown',
};

export const LANGUAGE_FLAG: Record<DetectedLanguage, string> = {
  en: '🇬🇧',
  kn: '🇮🇳',
  hi: '🇮🇳',
  unknown: '❓',
};

export interface MultilingualStats {
  total: number;
  english: number;
  kannada: number;
  hindi: number;
  unknown: number;
  translated: number;
  translation_errors: number;
  translate_enabled: boolean;
}

export const EMPTY_MULTILINGUAL_STATS: MultilingualStats = {
  total: 0,
  english: 0,
  kannada: 0,
  hindi: 0,
  unknown: 0,
  translated: 0,
  translation_errors: 0,
  translate_enabled: true,
};

export interface SafetyReport {
  id: string;
  report_id?: string;
  report_type: ReportType | string;
  report_text: string;
  activity?: string;
  location?: string;
  site?: string;
  unit?: string;
  area?: string;
  date?: string;
  severity?: string;
  sif_potential?: SIFPotential;
  risk_level?: RiskLevel;
  risk_score?: number;
  life_saving_rule?: string;
  barrier_failure?: string;
  pii_detected?: boolean;
  pii_count?: number;
  pii_types?: string;
  recommended_action?: string;
  analyzed?: boolean;
  analysis?: ReportAnalysis;
  reviewer_status?: 'Pending' | 'Confirmed' | 'Corrected' | 'Rejected';
  reviewer_comment?: string;
  // ─── Multilingual fields ──────────────────────────────────────────────────
  original_report_text?: string;       // Raw text in original language
  detected_language?: DetectedLanguage; // 'en' | 'kn' | 'hi' | 'unknown'
  detected_language_name?: string;     // Display name e.g. "Kannada"
  translated_report_text?: string;     // English translation (used by ML model)
  translation_method?: string;         // 'passthrough' | 'deep_translator' | 'offline_dict'
  translation_error?: string | null;   // Error message or null
  is_translated?: boolean;             // True if translation was applied
}

export interface ReportAnalysis {
  sif_potential: SIFPotential;
  risk_level: RiskLevel;
  risk_score: number;
  activity_detected: string;
  hazard_detected: string;
  barrier_failure: string;
  barrier_failures?: string[];
  risk_reason?: string;
  confidence?: number;
  confidence_level?: 'HIGH' | 'MEDIUM' | 'LOW' | string;
  negation_type?: string;
  life_saving_rule: string;
  evidence_phrases: string[];
  explanation: string;
  source?: string;
  fallback_indicator?: string | null;
  input_feedback?: string;
  confidence_reason?: string;
  confidence_reason_user?: string;
  system_confidence?: 'HIGH' | 'MEDIUM' | 'LOW' | string;
  system_confidence_score?: number;
  analysis_quality?: 'HIGH' | 'MEDIUM' | 'LOW' | string;
  adversarial_flags?: string[];
  temporal_sequence?: string;
  temporal_timeline?: string[];
  raw_score?: number;
  normalized_score?: number;
  normalization_applied?: boolean;
  safety_concepts?: string[];
  structured_evidence?: StructuredEvidenceItem[];
  factor_breakdown?: Record<string, FactorBreakdownDetail>;
  barrier_evidence?: BarrierEvidenceDetail[];
  risk_factors: RiskFactor[];
  recommended_actions: string[];
  similar_report_ids: string[];
  pattern_name?: string;
  mode: 'rule-based' | 'ml' | string;
  pii_detected?: boolean;
  pii_count?: number;
  pii_types?: string[];
  redacted_text?: string;
}

export interface StructuredEvidenceItem {
  concept: string;
  source_phrase: string;
  evidence_type: string;
  state: 'ACTIVE_VIOLATION' | 'PREVENTED' | 'POSITIVE_CONTROL' | 'CONTEXT_ONLY' | string;
  related_barrier?: string | null;
  related_rule?: string | null;
}

export interface FactorBreakdownDetail {
  name: string;
  score: number;
  max_score: number;
  reason?: string;
  evidence?: string[];
}

export interface BarrierEvidenceDetail {
  barrier: string;
  confidence_score?: number;
  confidence?: number;
  method?: string;
  evidence?: string[];
  detection_reason?: string;
  confidence_level?: string;
}

export interface RiskFactor {
  name: string;
  score: number;
  max_score: number;
  description?: string;
  reason?: string;
  evidence?: string[];
}

export interface DatasetInfo {
  filename: string;
  filesize: number;
  rows: number;
  columns: string[];
  preview: Record<string, unknown>[];
  column_mapping: ColumnMapping;
  quality: DatasetQuality;
  is_demo: boolean;
}

export interface ColumnMapping {
  report_text?: string;
  sif_label?: string;
  severity?: string;
  report_type?: string;
  location?: string;
  site?: string;
  unit?: string;
  area?: string;
  activity?: string;
  date?: string;
  barrier_failure?: string;
  recommended_action?: string;
  life_saving_rule?: string;
}

export interface DatasetQuality {
  health_score: number;
  total_records: number;
  total_columns: number;
  missing_values: Record<string, number>;
  empty_reports: number;
  duplicate_records: number;
  avg_report_length: number;
  unique_report_types: number;
  unique_activities: number;
  unique_sites: number;
  unique_locations: number;
  label_distribution?: Record<string, number>;
  warnings: string[];
  has_sif_label: boolean;
  has_date: boolean;
  has_site: boolean;
  has_activity: boolean;
}

export interface SiteRisk {
  site: string;
  total_reports: number;
  sif_count: number;
  critical_count: number;
  high_count: number;
  risk_level: RiskLevel;
  top_precursor: string;
  top_barrier_failure: string;
  risk_score: number;
  trend: 'increasing' | 'decreasing' | 'stable';
}

export interface ActivityRisk {
  activity: string;
  report_count: number;
  sif_count: number;
  avg_risk_score: number;
  top_barrier_failure: string;
  trend: 'increasing' | 'decreasing' | 'stable';
  risk_level: RiskLevel;
}

export interface SafetyPattern {
  id: string;
  name: string;
  frequency: number;
  risk_level: RiskLevel;
  sites: string[];
  activities: string[];
  trend: 'increasing' | 'decreasing' | 'stable';
  description: string;
  report_ids: string[];
}

export interface EarlyWarning {
  id: string;
  type: 'WATCH' | 'WARNING' | 'CRITICAL';
  title: string;
  description: string;
  metric: string;
  current_value: number;
  previous_value: number;
  change_pct: number;
  affected_sites: string[];
  affected_activities: string[];
}

export interface BarrierFailure {
  barrier: string;
  count: number;
  percentage: number;
  risk_level: RiskLevel;
}

export interface CorrectiveAction {
  id: string;
  report_id: string;
  action: string;
  owner: string;
  priority: 'Critical' | 'High' | 'Medium' | 'Low';
  due_date: string;
  status: 'Open' | 'In Progress' | 'Completed' | 'Overdue';
  created_at: string;
}

export interface DashboardMetrics {
  total_reports: number;
  sif_potential_count: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  early_warnings: number;
  open_actions: number;
  sif_percentage: number;
  top_rule: string;
  top_barrier: string;
  top_site: string;
  is_demo: boolean;
}

export interface User {
  id: string;
  name: string;
  email: string;
  role: 'HSE Officer' | 'Safety Manager' | 'Site Manager' | 'Administrator';
  site?: string;
  token?: string;
}

export interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
}

export interface CopilotMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  source_reports?: string[];
  model?: string;
  isError?: boolean;
}


export interface KnowledgeNode {
  id: string;
  label: string;
  type: 'site' | 'activity' | 'hazard' | 'barrier' | 'rule' | 'risk';
  risk_level?: RiskLevel;
  count?: number;
}

export interface KnowledgeLink {
  source: string;
  target: string;
  label?: string;
  weight?: number;
}

// ─── SIF Risk Concentration Heatmap Types ─────────────────────────────────────
export type HeatmapRiskLevel = 'HIGH' | 'EMERGING' | 'MEDIUM' | 'LOW';

export interface SifHeatmapNode {
  id: string;
  name: string;
  level: 'site' | 'unit' | 'area' | 'activity' | 'lsr' | 'barrier';
  total_reports: number;
  sif_count: number;
  precursor_density: number;
  risk_level: HeatmapRiskLevel;
  avg_risk_score: number;
  trend_pct: number | null;
  trend_label: string;
  top_barrier: string;
  is_fallback: boolean;
  report_ids: string[];
  children?: SifHeatmapNode[];
}

export interface SifHeatmapSummary {
  total_reports: number;
  total_precursors: number;
  overall_density: number;
  high_risk_concentrations: number;
  emerging_concentrations: number;
  top_concentration: string;
}

export interface HeatmapReportItem {
  report_id: string;
  id?: string | number;
  description: string;
  category: string;
  risk_score: number;
  risk_level: string;
  sif_potential: string;
  site?: string;
  unit?: string;
  area?: string;
  activity?: string;
  barrier_failure?: string;
  pii_detected?: boolean;
  pii_count?: number;
  pii_types?: string;
  date?: string | null;
  created_at?: string | null;
}

export interface SifHeatmapResponse {
  summary: SifHeatmapSummary;
  tree: SifHeatmapNode[];
  reports: HeatmapReportItem[];
}

export interface SifHeatmapFilter {
  site?: string;
  unit?: string;
  area?: string;
  activity?: string;
  lsr?: string;
  barrier?: string;
}
