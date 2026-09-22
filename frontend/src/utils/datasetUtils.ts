import { DatasetInfo, DatasetQuality, ColumnMapping, SafetyReport } from '../types';
import { analyzeReport, calculateRiskScore, detectLSR, detectBarrierFailure, determineSIFPotential } from './riskEngine';
import { processDataset, TranslationResult } from './multilingualUtils';

// ─── Column auto-detection ────────────────────────────────────────────────────
const COLUMN_HINTS: Record<keyof ColumnMapping, string[]> = {
  report_text: ['report_text', 'text', 'description', 'observation', 'narrative', 'report', 'detail', 'comment'],
  sif_label: ['sif', 'sif_potential', 'sif_label', 'serious', 'fatality', 'label'],
  severity: ['severity', 'risk', 'level', 'criticality', 'priority'],
  report_type: ['report_type', 'type', 'category', 'classification'],
  site: ['site', 'plant', 'facility', 'installation'],
  unit: ['unit', 'operating_unit', 'plant_unit', 'refinery_unit'],
  area: ['area', 'zone', 'section', 'work_area', 'bay', 'sector'],
  location: ['location', 'place', 'loc'],
  activity: ['activity', 'task', 'work_type', 'job_type', 'operation'],
  date: ['date', 'incident_date', 'report_date', 'timestamp', 'created_at', 'reported_on'],
  barrier_failure: ['barrier', 'control_failure', 'failed_barrier', 'barrier_failure'],
  recommended_action: ['recommendation', 'action', 'corrective', 'recommended_action', 'remedy'],
  life_saving_rule: ['rule', 'lsr', 'life_saving_rule', 'safety_rule', 'critical_rule'],
};

/** Detect the optional 'language' hint column in uploaded data */
function detectLanguageColumn(columns: string[]): string | undefined {
  const lower = columns.map(c => c.toLowerCase().trim());
  const idx = lower.findIndex(c => c === 'language' || c === 'lang' || c === 'detected_language');
  return idx !== -1 ? columns[idx] : undefined;
}

export function detectColumnMapping(columns: string[]): ColumnMapping {
  const mapping: ColumnMapping = {};
  const lowerColumns = columns.map(c => c.toLowerCase().trim());

  for (const [field, hints] of Object.entries(COLUMN_HINTS)) {
    for (const hint of hints) {
      const idx = lowerColumns.findIndex(c => c === hint || c.includes(hint));
      if (idx !== -1) {
        (mapping as Record<string, string>)[field] = columns[idx];
        break;
      }
    }
  }
  return mapping;
}

// ─── Quality Analysis ─────────────────────────────────────────────────────────
export function analyzeDatasetQuality(
  rows: Record<string, unknown>[],
  columns: string[],
  mapping: ColumnMapping
): DatasetQuality {
  const total = rows.length;
  const missing: Record<string, number> = {};
  let emptyReports = 0;
  let totalLength = 0;

  for (const col of columns) {
    missing[col] = rows.filter(r => !r[col] || String(r[col]).trim() === '').length;
  }

  const textCol = mapping.report_text;
  if (textCol) {
    for (const row of rows) {
      const text = String(row[textCol] || '').trim();
      if (!text) emptyReports++;
      else totalLength += text.length;
    }
  }

  // Duplicate detection (based on text)
  const texts = textCol ? rows.map(r => String(r[textCol] || '').trim().toLowerCase()) : [];
  const uniqueTexts = new Set(texts);
  const duplicateRecords = texts.length - uniqueTexts.size;

  const reportTypeCol = mapping.report_type;
  const uniqueTypes = reportTypeCol
    ? new Set(rows.map(r => String(r[reportTypeCol] || ''))).size
    : 0;

  const activityCol = mapping.activity;
  const uniqueActivities = activityCol
    ? new Set(rows.map(r => String(r[activityCol] || ''))).size
    : 0;

  const siteCol = mapping.site;
  const uniqueSites = siteCol
    ? new Set(rows.map(r => String(r[siteCol] || ''))).size
    : 0;

  const locationCol = mapping.location;
  const uniqueLocations = locationCol
    ? new Set(rows.map(r => String(r[locationCol] || ''))).size
    : 0;

  const sifCol = mapping.sif_label;
  const hasSIFLabel = !!sifCol;
  let labelDist: Record<string, number> | undefined;
  if (sifCol) {
    labelDist = {};
    for (const row of rows) {
      const val = String(row[sifCol] || 'Unknown').trim();
      labelDist[val] = (labelDist[val] || 0) + 1;
    }
  }

  const warnings: string[] = [];
  if (!textCol) warnings.push('No report text column detected. Text-based analysis will be unavailable.');
  if (!sifCol) warnings.push('No SIF label column detected. Running AI/rule-based prototype analysis mode.');
  if (!mapping.date) warnings.push('No date column detected. Trend analysis will be unavailable.');
  if (!siteCol) warnings.push('No site column detected. Site-level risk analysis will be unavailable.');
  if (!activityCol) warnings.push('No activity column detected. Activity-level analysis may be limited.');
  if (emptyReports > 0) warnings.push(`${emptyReports} reports (${Math.round(emptyReports / total * 100)}%) have missing or empty text.`);
  if (duplicateRecords > 0) warnings.push(`${duplicateRecords} potential duplicate records detected.`);

  // Health score
  let health = 100;
  if (!textCol) health -= 30;
  if (!sifCol) health -= 10;
  if (!mapping.date) health -= 10;
  if (!siteCol) health -= 5;
  health -= Math.round((emptyReports / total) * 20);
  health -= Math.round((duplicateRecords / total) * 10);
  health = Math.max(0, Math.min(100, health));

  return {
    health_score: health,
    total_records: total,
    total_columns: columns.length,
    missing_values: missing,
    empty_reports: emptyReports,
    duplicate_records: duplicateRecords,
    avg_report_length: textCol && total > emptyReports ? Math.round(totalLength / (total - emptyReports)) : 0,
    unique_report_types: uniqueTypes,
    unique_activities: uniqueActivities,
    unique_sites: uniqueSites,
    unique_locations: uniqueLocations,
    label_distribution: labelDist,
    warnings,
    has_sif_label: hasSIFLabel,
    has_date: !!mapping.date,
    has_site: !!siteCol,
    has_activity: !!activityCol,
  };
}

// ─── Convert raw rows to SafetyReport[] (with multilingual support) ───────────
/**
 * Convert raw CSV/Excel rows to typed SafetyReport objects.
 *
 * Multilingual pipeline (runs automatically):
 *   1. Detect language for every report_text value
 *   2. Translate Kannada/Hindi → English using client-side dictionary
 *   3. Use the translated English text for risk scoring and LSR detection
 *   4. Preserve original_report_text and translated_report_text on every report
 *
 * If translateEnabled = false, only language detection runs (no translation).
 */
export function rowsToReports(
  rows: Record<string, unknown>[],
  mapping: ColumnMapping,
  translateEnabled = true
): SafetyReport[] {
  // ── Extract all report texts and optional language hints ──────────────────
  const langCol = detectLanguageColumn(Object.keys(rows[0] || {}));
  const texts = rows.map(row =>
    mapping.report_text ? String(row[mapping.report_text] || '') : ''
  );
  const hintLangs = langCol
    ? rows.map(row => String(row[langCol] || '').trim() || undefined)
    : undefined;

  // ── Run multilingual pipeline on all texts at once ────────────────────────
  const { results: mlResults } = processDataset(texts, hintLangs, translateEnabled);

  return rows.map((row, idx) => {
    const ml: TranslationResult = mlResults[idx];

    // The text fed into the existing NLP/risk engine is always English
    // (translated if non-English, original if already English)
    const analysisText = ml.translated_report_text || ml.original_report_text || '';

    const rawSIF = mapping.sif_label
      ? String(row[mapping.sif_label] || '').toUpperCase().trim()
      : undefined;
    let sifPotential: 'YES' | 'NO' | 'UNKNOWN' | undefined;
    if (rawSIF) {
      if (['YES', 'Y', '1', 'TRUE'].includes(rawSIF))  sifPotential = 'YES';
      else if (['NO', 'N', '0', 'FALSE'].includes(rawSIF)) sifPotential = 'NO';
      else sifPotential = 'UNKNOWN';
    }

    const severity = mapping.severity
      ? String(row[mapping.severity] || '')
      : undefined;

    // LSR and barrier are detected from the English analysis text
    const lsr = mapping.life_saving_rule
      ? String(row[mapping.life_saving_rule] || '') || detectLSR(analysisText)
      : detectLSR(analysisText);
    const barrier = mapping.barrier_failure
      ? String(row[mapping.barrier_failure] || '') || detectBarrierFailure(analysisText)
      : detectBarrierFailure(analysisText);

    const partialReport = {
      report_text: analysisText,
      sif_potential: sifPotential,
      severity,
      life_saving_rule: lsr,
      barrier_failure: barrier,
      report_type: mapping.report_type
        ? String(row[mapping.report_type] || 'Unknown')
        : 'Unknown',
      activity: mapping.activity
        ? String(row[mapping.activity] || '')
        : undefined,
    };

    const { score, level } = calculateRiskScore(partialReport);
    const computedSIF = sifPotential || determineSIFPotential(analysisText, score, lsr);

    return {
      id: `RPT-${String(idx + 1).padStart(4, '0')}`,
      report_id: `RPT-${String(idx + 1).padStart(4, '0')}`,
      report_type: partialReport.report_type,
      // report_text is the English text used for analysis
      report_text: analysisText,
      activity:  mapping.activity  ? String(row[mapping.activity]  || '') : undefined,
      location:  mapping.location  ? String(row[mapping.location]  || '') : undefined,
      site:      mapping.site      ? String(row[mapping.site]       || '') : undefined,
      date:      mapping.date      ? String(row[mapping.date]       || '') : undefined,
      severity,
      sif_potential:    computedSIF,
      risk_level:       level,
      risk_score:       score,
      life_saving_rule: lsr,
      barrier_failure:  barrier,
      recommended_action: mapping.recommended_action
        ? String(row[mapping.recommended_action] || '')
        : undefined,
      analyzed: true,
      // ── Multilingual fields ──────────────────────────────────────────────
      original_report_text:   ml.original_report_text,
      detected_language:      ml.detected_language,
      detected_language_name: ml.detected_language_name,
      translated_report_text: ml.translated_report_text,
      translation_method:     ml.translation_method,
      translation_error:      ml.translation_error,
      is_translated:          ml.is_translated,
    };
  });
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}
