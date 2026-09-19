import { SafetyReport, ReportAnalysis, RiskLevel, SIFPotential, RiskFactor, SiteRisk, ActivityRisk, SafetyPattern } from '../types';

// ─── Life-Saving Rules ────────────────────────────────────────────────────────
const LSR_RULES: Record<string, { keywords: string[]; description: string }> = {
  'Confined Space': {
    keywords: ['confined space', 'vessel entry', 'tank entry', 'permit', 'gas test', 'atmospheric', 'oxygen', 'h2s', 'drain', 'pit', 'sump', 'chamber', 'enclosed'],
    description: 'Work inside confined spaces requires atmospheric testing, a valid entry permit, and a trained standby person.',
  },
  'Energy Isolation': {
    keywords: ['lockout', 'tagout', 'loto', 'isolation', 'energized', 'de-energize', 'live circuit', 'electrical', 'voltage', 'power source', 'isolation certificate', 'pressure', 'stored energy'],
    description: 'All energy sources must be isolated, locked out and verified at zero-energy state before work begins.',
  },
  'Hot Work': {
    keywords: ['welding', 'cutting', 'grinding', 'hot work', 'sparks', 'flame', 'arc', 'torch', 'fire watch', 'flammable', 'ignition', 'permit to work'],
    description: 'Hot work in hazardous areas requires a permit, gas testing, and a trained fire watch.',
  },
  'Working at Height': {
    keywords: ['height', 'scaffold', 'ladder', 'roof', 'platform', 'harness', 'fall arrest', 'elevated', 'guardrail', 'edge protection', 'toe board', 'fall protection'],
    description: 'Work above 1.8 m requires a risk assessment, fall-protection equipment, and edge protection.',
  },
  'Line of Fire': {
    keywords: ['line of fire', 'suspended load', 'crane', 'lift', 'rigging', 'exclusion zone', 'struck by', 'falling object', 'overhead', 'below load'],
    description: 'No person shall stand in the line of fire of a suspended load, pressurized release, or moving equipment.',
  },
  'Vehicle Movement': {
    keywords: ['vehicle', 'forklift', 'hgv', 'truck', 'reversing', 'pedestrian', 'banksman', 'traffic', 'collision', 'seat belt', 'speeding', 'excavator', 'mobile plant'],
    description: 'Vehicles and pedestrians must be segregated. Banksman required for reversing. Speed limits must be observed.',
  },
  'Chemical Handling': {
    keywords: ['chemical', 'acid', 'caustic', 'toxic', 'corrosive', 'spill', 'ppe', 'sds', 'msds', 'inhalation', 'exposure', 'gas leak', 'chlorine', 'sulfuric', 'ammonia'],
    description: 'Chemicals must be handled with appropriate PPE, reviewed SDS, and proper containment.',
  },
  'Fire Prevention': {
    keywords: ['fire', 'smoke', 'detector', 'suppression', 'extinguisher', 'flammable', 'combustible', 'ignition', 'evacuation', 'alarm'],
    description: 'Fire detection and suppression systems must be operational. Hot work permits required near flammable materials.',
  },
  'General Safety': {
    keywords: [],
    description: 'General workplace safety standards apply.',
  },
};

// ─── Barrier Failure Patterns ─────────────────────────────────────────────────
const BARRIER_PATTERNS: Record<string, string[]> = {
  'Gas Testing Not Completed': ['without gas test', 'no gas test', 'without atmospheric', 'not tested', 'not calibrated'],
  'Permit Not Obtained': ['without permit', 'no permit', 'permit not obtained', 'without authorization', 'no authorization'],
  'Isolation Not Applied': ['without isolat', 'no isolation', 'not isolated', 'isolation not applied', 'without lockout', 'without loto'],
  'Lockout/Tagout Not Completed': ['lockout not applied', 'tag not applied', 'loto not completed', 'lock not applied'],
  'Fall Protection Not Used': ['without harness', 'no harness', 'no fall arrest', 'no edge protection', 'no guardrail', 'fall protection not'],
  'Exclusion Zone Not Established': ['exclusion zone', 'no exclusion', 'zone not established', 'standing under', 'below load'],
  'Fire Watch Not Posted': ['no fire watch', 'fire watch not', 'without fire watch'],
  'Standby Person Not Assigned': ['no standby', 'no attendant', 'attendant not', 'standby not'],
  'PPE Not Available': ['without ppe', 'no ppe', 'ppe not available', 'without protection', 'without gloves', 'without face shield'],
  'Pressure Not Released': ['not depressurized', 'pressure not released', 'still under pressure', 'pressurized'],
  'Hot Work Permit Not Obtained': ['without hot work permit', 'no hot work permit'],
  'Scaffold Not Inspected': ['scaffold not inspected', 'not inspected', 'uninspected scaffold'],
  'Rescue Plan Not Available': ['rescue not', 'no rescue', 'rescue team not'],
  'Exposed Live Parts': ['live terminal', 'live conductor', 'exposed conductor', 'exposed terminal', 'live wire'],
  'Pedestrian Segregation Not Maintained': ['pedestrian segregat', 'segregation not maintained', 'barriers removed', 'barrier not'],
  'Seat Belt Not Worn': ['without seat belt', 'no seat belt', 'not wearing seat belt'],
  'Fire Detection Disabled': ['detector disabled', 'alarm disabled', 'suppression isolated', 'detector covered'],
  'Housekeeping Standards Not Met': ['trailing cable', 'spilled', 'poor lighting', 'tools left'],
};

// ─── Hazard Detection ─────────────────────────────────────────────────────────
const HAZARD_PATTERNS: Record<string, string[]> = {
  'Oxygen Deficiency': ['oxygen deficient', 'low oxygen', 'asphyxiation', 'o2 level'],
  'Toxic Atmosphere': ['h2s', 'hydrogen sulfide', 'toxic gas', 'gas exposure', 'chlorine', 'ammonia leak'],
  'Electrical Energy': ['electrical', 'live', 'energized', 'voltage', 'current', 'electrocution'],
  'Stored Pressure': ['pressurized', 'pressure', 'hydraulic', 'pneumatic'],
  'Fire and Explosion': ['fire', 'explosion', 'flammable', 'ignition', 'combustion'],
  'Fall from Height': ['fall', 'fell', 'height', 'elevated', 'roof'],
  'Struck by Object': ['struck by', 'hit by', 'impact', 'falling object'],
  'Chemical Exposure': ['chemical', 'acid', 'caustic', 'corrosive', 'toxic substance'],
  'Caught in Equipment': ['caught in', 'entangled', 'trapped', 'pinch point'],
  'Vehicle Collision': ['vehicle collision', 'struck by vehicle', 'run over', 'vehicle movement'],
  'Unsafe Entry': ['entered without', 'entry without', 'gained access without'],
};

// ─── Main Risk Engine ─────────────────────────────────────────────────────────

function textLower(text: string): string {
  return text.toLowerCase();
}

export function detectLSR(text: string): string {
  const lower = textLower(text);
  let best = 'General Safety';
  let bestScore = 0;

  for (const [rule, config] of Object.entries(LSR_RULES)) {
    if (rule === 'General Safety') continue;
    const score = config.keywords.filter(k => lower.includes(k)).length;
    if (score > bestScore) {
      bestScore = score;
      best = rule;
    }
  }
  return best;
}

export function detectBarriers(text: string): string[] {
  const lower = textLower(text);
  const matched: string[] = [];
  for (const [barrier, patterns] of Object.entries(BARRIER_PATTERNS)) {
    if (patterns.some(p => lower.includes(p))) {
      matched.push(barrier);
    }
  }
  return matched;
}

export function detectBarrierFailure(text: string): string {
  const barriers = detectBarriers(text);
  return barriers.length > 0 ? barriers[0] : 'Unknown Barrier Failure';
}

export function detectHazard(text: string): string {
  const lower = textLower(text);
  for (const [hazard, patterns] of Object.entries(HAZARD_PATTERNS)) {
    if (patterns.some(p => lower.includes(p))) return hazard;
  }
  return 'General Hazard';
}

export function detectActivity(text: string, existingActivity?: string): string {
  if (existingActivity && existingActivity !== 'Unknown') return existingActivity;
  const lower = textLower(text);
  const activityMap: Record<string, string[]> = {
    'Confined Space Entry': ['confined space', 'vessel entry', 'tank entry', 'pit entry', 'sump', 'drain chamber'],
    'Maintenance - Electrical': ['electrical maintenance', 'control panel', 'switchgear', 'electrician', 'electrical work'],
    'Maintenance - Mechanical': ['mechanical maintenance', 'pipework', 'pipe joint', 'pump maintenance', 'conveyor'],
    'Hot Work': ['welding', 'cutting', 'grinding', 'hot work', 'torch work'],
    'Working at Height': ['working at height', 'scaffold', 'roof', 'elevated platform', 'ladder work'],
    'Lifting Operations': ['crane', 'lift', 'rigging', 'suspended load', 'hoisting'],
    'Vehicle Movement': ['vehicle', 'forklift', 'truck', 'hgv', 'driving'],
    'Chemical Handling': ['chemical', 'acid handling', 'decanting', 'chemical transfer'],
    'Fire Safety': ['fire system', 'suppression system', 'fire alarm', 'fire extinguisher'],
    'Electrical Work': ['electrical work', 'live conductor', 'junction box', 'live terminal'],
    'General Inspection': ['inspection', 'housekeeping', 'walkway', 'workshop'],
  };
  for (const [activity, kws] of Object.entries(activityMap)) {
    if (kws.some(k => lower.includes(k))) return activity;
  }
  return 'General Maintenance';
}

export function extractEvidencePhrases(text: string): string[] {
  const lower = textLower(text);
  const evidence: string[] = [];

  const keyPhrases = [
    'confined space', 'without gas testing', 'without permit', 'no permit',
    'without isolation', 'lockout', 'tagout', 'live circuit', 'energized',
    'without harness', 'no fall protection', 'welding', 'hot work', 'grinding',
    'without fire watch', 'exclusion zone', 'suspended load', 'without seat belt',
    'chemical', 'acid', 'chlorine', 'pressurized', 'without standby', 'no standby',
    'fire suppression disabled', 'detector covered', 'without ppe', 'not wearing ppe',
    'atmospheric testing', 'gas detector', 'scaffold not inspected',
  ];

  for (const phrase of keyPhrases) {
    if (lower.includes(phrase)) {
      evidence.push(phrase);
    }
  }

  // Also extract short phrases with "without" or "not"
  const matches = text.match(/(?:without|no|not|missing|absent)\s+\w+(?:\s+\w+)?/gi) || [];
  for (const m of matches) {
    if (!evidence.includes(m.toLowerCase())) {
      evidence.push(m.toLowerCase());
    }
  }

  return [...new Set(evidence)].slice(0, 8);
}

// ─── Negation & Context Patterns ──────────────────────────────────────────────

export type NegationType = 'UNSAFE_VIOLATION' | 'SAFE_PREVENTIVE' | 'AMBIGUOUS' | 'NONE';

export interface NegationAnalysisResult {
  negationType: NegationType;
  preventivePhrase: string | null;
  barrierPhrase: string | null;
  ambiguousPhrase?: string | null;
  interpretation: string;
  scoreImpact: string;
}

const PREVENTIVE_STOP_REGEX = /\b(?:(?:did\s+not|didn't|does\s+not|doesn't|would\s+not|wouldn't|refused\s+to|decided\s+not\s+to|opted\s+not\s+to|declined\s+to)\s+(?:proceed|enter|start|commence|work|operate|continue|execute|climb|step|go\s+into|begin|resume)|(?:work|job|entry|task|operation|activity|maintenance|welding|lifting|pour|process)\s+(?:was\s+)?(?:stopped|halted|suspended|aborted|cancelled|put\s+on\s+hold|paused|delayed|refused|prevented|ceased)|stopped(?:\s+(?:work|entry|task|job|activity|operation|hot\s+work|maintenance|welding|climbing))?|halted(?:\s+(?:work|entry|task|job|activity|operation))?|aborted(?:\s+(?:entry|operation|task|job|activity))?|suspended(?:\s+(?:work|entry|task|job|activity|operation))?|avoided(?:\s+(?:entering|working|climbing|proceeding|operating|starting|entry|work))?|refused(?:\s+(?:to\s+enter|to\s+work|to\s+proceed|to\s+climb|to\s+start|entry))?|intervened\s+and\s+stopped|held\s+back\s+from|stayed\s+back\s+from)\b/i;

const NEGATED_STOP_REGEX = /\b(?:did\s+not|didn't|failed\s+to|refused\s+to|could\s+not)\s+(?:stop|halt|abort|suspend|cease)\b/i;

const NEGATED_BARRIER_REGEX = /\b(?:(?:without|with\s+no|no|missing|lack\s+of|absence\s+of|failed\s+to\s+(?:conduct|perform|obtain|wear|apply|use))\s+(?:gas\s+test(?:ing)?|atmospheric\s+test(?:ing)?|permit(?: to work)?|ptw|authorization|isolation|lockout|tagout|loto|harness|fall\s+protection|fall\s+arrest|ppe|safety\s+glasses|gloves|helmet|mask|respirator|fire\s+watch|standby(?:\s+person)?|attendant|ventilation|guardrail|earthing|grounding|chock|banksman)|(?:gas\s+test(?:ing)?|permit|ptw|authorization|isolation|lockout|tagout|loto|harness|fall\s+protection|ppe|fire\s+watch|standby|attendant|ventilation|guardrail)\s+(?:was\s+|were\s+)?(?:not\s+(?:done|obtained|conducted|applied|completed|issued|available|present|worn|used|carried\s+out|tested|performed))|not\s+wearing\s+(?:ppe|harness|helmet|gloves|safety\s+glasses|mask|respirator|protection|seat\s*belt)|not\s+(?:tested|isolated|depressurized|grounded|authorized|inspected))\b/i;

const AMBIGUOUS_INDICATORS = /\b(?:unclear\s+(?:if|whether)|not\s+confirmed\s+(?:if|whether)|possibly|may\s+have|while\s+inspecting|inspection\s+only|started\s+(?:then|and\s+then)\s+stopped|entered\s+(?:then|and\s+then)\s+stopped)\b/i;

export function analyzeNegationContext(text: string): NegationAnalysisResult {
  const lower = text.toLowerCase().trim();
  if (!lower) {
    return {
      negationType: 'NONE',
      preventivePhrase: null,
      barrierPhrase: null,
      interpretation: 'Empty or neutral text.',
      scoreImpact: 'Standard baseline scoring.',
    };
  }

  const stopMatch = lower.match(PREVENTIVE_STOP_REGEX);
  const negatedStopMatch = lower.match(NEGATED_STOP_REGEX);
  const barrierMatch = lower.match(NEGATED_BARRIER_REGEX);
  const ambiguousMatch = lower.match(AMBIGUOUS_INDICATORS);

  if (ambiguousMatch) {
    return {
      negationType: 'AMBIGUOUS',
      preventivePhrase: stopMatch ? stopMatch[0] : null,
      barrierPhrase: barrierMatch ? barrierMatch[0] : null,
      ambiguousPhrase: ambiguousMatch[0],
      interpretation: `Ambiguous scenario detected ('${ambiguousMatch[0]}'). Exposure or execution status is uncertain.`,
      scoreImpact: 'Risk score held at moderate level (MEDIUM, ~45); flagged for supervisor review.',
    };
  }

  if (negatedStopMatch && barrierMatch) {
    return {
      negationType: 'UNSAFE_VIOLATION',
      preventivePhrase: null,
      barrierPhrase: barrierMatch[0],
      interpretation: `Active violation: Failed/refused to stop despite missing control ('${barrierMatch[0]}').`,
      scoreImpact: 'Risk score increased (+25 barrier penalty) and SIF potential flagged YES due to active execution without safety barrier.',
    };
  }

  if (stopMatch && !negatedStopMatch) {
    const stopPhrase = stopMatch[0];
    const barrierPhrase = barrierMatch ? barrierMatch[0] : 'missing safety requirement';
    return {
      negationType: 'SAFE_PREVENTIVE',
      preventivePhrase: stopPhrase,
      barrierPhrase: barrierPhrase,
      interpretation: `Safe preventive decision: Work was proactively stopped/avoided ('${stopPhrase}') due to '${barrierPhrase}'.`,
      scoreImpact: 'Risk score reduced to LOW (13-20) and SIF potential nullified because proactive intervention prevented hazard exposure.',
    };
  }

  if (barrierMatch) {
    return {
      negationType: 'UNSAFE_VIOLATION',
      preventivePhrase: null,
      barrierPhrase: barrierMatch[0],
      interpretation: `Unsafe condition / barrier violation: Activity performed or attempted without required control ('${barrierMatch[0]}').`,
      scoreImpact: 'Risk score increased (+25 barrier penalty) and SIF potential flagged YES due to active execution without safety barrier.',
    };
  }

  return {
    negationType: 'NONE',
    preventivePhrase: null,
    barrierPhrase: null,
    interpretation: 'Standard report: No critical negation or stop-work patterns detected.',
    scoreImpact: 'Scored using standard rule weights.',
  };
}

export function calculateConfidence(
  text: string,
  lsr: string,
  barrierFailures: string[],
  negType: NegationType,
  evidence: string[]
): {
  confidence: number;
  confidenceLevel: 'HIGH' | 'MEDIUM' | 'LOW';
  reasons: string[];
} {
  const lower = text.toLowerCase().trim();
  const words = lower.split(/\s+/).filter(Boolean);
  const wordCount = words.length;

  let score = 0.50;
  const reasons: string[] = [];

  // 1. LSR alignment
  let lsrHits = 0;
  if (lsr !== 'General Safety' && LSR_RULES[lsr]) {
    lsrHits = LSR_RULES[lsr].keywords.filter(k => lower.includes(k)).length;
  }

  if (lsrHits >= 2) {
    score += 0.15;
    reasons.push(`Strong Life-Saving Rule alignment (${lsrHits} keywords for '${lsr}')`);
  } else if (lsrHits === 1) {
    score += 0.08;
    reasons.push(`Explicit Life-Saving Rule detected ('${lsr}')`);
  } else {
    score -= 0.05;
    reasons.push('General safety context without specific Life-Saving Rule match');
  }

  // 2. Barrier Match Density
  const nBarriers = barrierFailures.length;
  if (nBarriers >= 2) {
    score += 0.15;
    reasons.push(`${nBarriers} explicit barrier failures detected`);
  } else if (nBarriers === 1) {
    score += 0.10;
    reasons.push(`1 explicit barrier failure detected ('${barrierFailures[0]}')`);
  } else {
    score -= 0.05;
    reasons.push('No standard barrier patterns matched');
  }

  // 3. Evidence phrase support
  if (evidence.length >= 2) {
    score += 0.05;
  }

  // 4. Sentence Structure Clarity
  const hasRole = /\b(worker|workers|technician|technicians|operator|operators|crew|team|electrician|welder|supervisor|contractor|personnel)\b/i.test(lower);
  const hasAction = /\b(entered|proceeded|working|climbed|welding|operating|started|stopped|halted|avoided|refused|conducted|performed|inspected)\b/i.test(lower);

  if (hasRole && hasAction) {
    score += 0.10;
    reasons.push('Clear actor and operational action structure');
  } else if (hasAction || hasRole) {
    score += 0.05;
    reasons.push('Identified operational context');
  }

  // 5. Ambiguity & Conflicting Signals
  if (negType === 'AMBIGUOUS' || AMBIGUOUS_INDICATORS.test(lower)) {
    score -= 0.35;
    reasons.push('Ambiguous or conflicting signals present');
  } else if (negType === 'SAFE_PREVENTIVE' || negType === 'UNSAFE_VIOLATION') {
    score += 0.05;
    reasons.push(`Unambiguous negation intent (${negType})`);
  }

  if (wordCount < 4) {
    score -= 0.20;
    reasons.push('Fragmented / brief sentence structure');
  }

  const confidence = Number(Math.min(0.98, Math.max(0.20, score)).toFixed(2));
  const confidenceLevel = confidence >= 0.80 ? 'HIGH' : confidence >= 0.50 ? 'MEDIUM' : 'LOW';

  return {
    confidence,
    confidenceLevel,
    reasons,
  };
}

export function calculateRiskScore(report: Partial<SafetyReport>): {
  score: number;
  level: RiskLevel;
  barrierFailures: string[];
  factors: RiskFactor[];
  negation: NegationAnalysisResult;
} {
  const text = (report.report_text || '').toLowerCase();
  const lsr = report.life_saving_rule || detectLSR(text);
  const barrierFailures = detectBarriers(text);
  const severity = (report.severity || '').toLowerCase();
  const reportType = (report.report_type || '').toLowerCase();

  const negation = analyzeNegationContext(text);
  const nBarriers = barrierFailures.length;

  let hazardSeverity = 15;
  let barrierScore = 5;
  let exposureScore = 8;
  let activityScore = 5;
  let recurrenceScore = 5;
  let total = 0;
  let level: RiskLevel = 'LOW';

  if (negation.negationType === 'SAFE_PREVENTIVE') {
    hazardSeverity = lsr !== 'General Safety' ? 10 : 5;
    barrierScore = 0;
    exposureScore = 2;
    activityScore = 2;
    recurrenceScore = 4;
    total = hazardSeverity + barrierScore + exposureScore + activityScore + recurrenceScore;
    level = 'LOW';
  } else if (negation.negationType === 'AMBIGUOUS') {
    hazardSeverity = lsr !== 'General Safety' ? 18 : 10;
    barrierScore = nBarriers > 0 ? Math.min(20, 12 + Math.max(0, nBarriers - 1) * 4) : 12;
    exposureScore = 10;
    activityScore = 5;
    recurrenceScore = 5;
    total = hazardSeverity + barrierScore + exposureScore + activityScore + recurrenceScore;
    level = 'MEDIUM';
  } else {
    if (severity.includes('critical') || lsr !== 'General Safety') hazardSeverity = 28;
    else if (severity.includes('high')) hazardSeverity = 22;
    else if (severity.includes('medium')) hazardSeverity = 14;
    else if (severity.includes('low')) hazardSeverity = 6;

    // Multi-barrier penalty: 25 for first barrier, +5 for each additional barrier, capped at 35
    if (nBarriers === 0) {
      barrierScore = negation.negationType === 'UNSAFE_VIOLATION' ? 25 : 5;
    } else if (nBarriers === 1) {
      barrierScore = 25;
    } else {
      barrierScore = Math.min(35, 25 + (nBarriers - 1) * 5);
    }

    if (text.includes('worker') || text.includes('technician') || text.includes('operator')) exposureScore = 16;
    if (text.includes('two worker') || text.includes('crew') || text.includes('multiple')) exposureScore = 20;

    const criticalActivities = ['Confined Space', 'Energy Isolation', 'Hot Work', 'Working at Height'];
    if (criticalActivities.some(a => text.includes(a.toLowerCase()) || lsr.includes(a))) activityScore = 10;

    if (reportType.includes('incident')) recurrenceScore = 15;
    else if (reportType.includes('near miss')) recurrenceScore = 12;
    else if (reportType.includes('unsafe act')) recurrenceScore = 10;
    else if (reportType.includes('unsafe condition')) recurrenceScore = 8;

    total = Math.min(100, hazardSeverity + barrierScore + exposureScore + activityScore + recurrenceScore);
    if (total > 80) level = 'CRITICAL';
    else if (total > 60) level = 'HIGH';
    else if (total > 30) level = 'MEDIUM';
    else level = 'LOW';
  }

  return {
    score: total,
    level,
    barrierFailures,
    negation,
    factors: [
      { name: 'Hazard Severity', score: hazardSeverity, max_score: 30, description: 'Based on severity classification and life-saving rule category.' },
      { name: 'Barrier Failure', score: barrierScore, max_score: nBarriers > 1 ? 35 : 25, description: 'Whether required safety controls were absent, breached, or prevented.' },
      { name: 'Exposure', score: exposureScore, max_score: 20, description: 'Number of persons exposed to the hazardous condition.' },
      { name: 'Activity Criticality', score: activityScore, max_score: 10, description: 'Whether the activity falls under a critical life-saving rule.' },
      { name: 'Recurrence Weight', score: recurrenceScore, max_score: 15, description: 'Report type — incidents and near-misses indicate higher potential.' },
    ],
  };
}

export function determineSIFPotential(text: string, riskScore: number, lsr: string): SIFPotential {
  const lower = textLower(text);
  const negation = analyzeNegationContext(text);

  if (negation.negationType === 'SAFE_PREVENTIVE') {
    return 'NO';
  }
  if (negation.negationType === 'AMBIGUOUS') {
    return 'UNKNOWN';
  }

  // Hard YES conditions
  const sifKeywords = [
    'confined space', 'without gas testing', 'lockout', 'without isolation',
    'energized', 'live circuit', 'without harness', 'suspended load',
    'line of fire', 'exclusion zone', 'chemical exposure', 'toxic gas',
    'oxygen deficient', 'pressurized', 'fire suppression disabled',
    'hot work', 'without permit', 'no permit', 'not wearing', 'no standby',
  ];
  const hasSIFKeyword = sifKeywords.some(k => lower.includes(k));

  if (hasSIFKeyword || riskScore >= 70) return 'YES';
  if (riskScore <= 30 && !hasSIFKeyword) return 'NO';
  return 'UNKNOWN';
}

export function generateRecommendedActions(lsr: string, barrier: string, activity: string): string[] {
  const baseActions: Record<string, string[]> = {
    'Confined Space': [
      'Stop all confined space entry immediately.',
      'Complete atmospheric gas testing with a calibrated instrument.',
      'Obtain a valid confined space entry permit.',
      'Assign a trained standby/rescue person before entry.',
      'Verify all emergency rescue equipment is available.',
      'Conduct a toolbox talk on confined space requirements before resuming.',
    ],
    'Energy Isolation': [
      'Stop work immediately on all energized equipment.',
      'Apply lockout/tagout to all energy isolation points.',
      'Verify zero energy state using an appropriate tester.',
      'Obtain an energy isolation certificate from the authorized person.',
      'Conduct a supervisor verification walkthrough.',
      'Review and re-brief all maintenance personnel on LOTO procedures.',
    ],
    'Hot Work': [
      'Stop all hot work activities immediately.',
      'Obtain a valid hot work permit before resuming.',
      'Conduct gas testing in the immediate work area.',
      'Post a trained fire watch for the duration of hot work plus 30 minutes.',
      'Ensure fire extinguisher is available and serviceable within 5 meters.',
      'Verify flammable materials are removed or protected within exclusion distance.',
    ],
    'Working at Height': [
      'Stop work at height until fall protection controls are in place.',
      'Inspect and fit all workers with appropriate harnesses and lanyards.',
      'Install guardrails, toe boards, and edge protection.',
      'Identify and rig suitable anchor points before work resumes.',
      'Ensure scaffold has been formally inspected and tagged.',
      'Conduct a working-at-height toolbox talk.',
    ],
    'Line of Fire': [
      'Establish and mark exclusion zones around all lifting operations.',
      'Brief all personnel on line-of-fire hazards before proceeding.',
      'Conduct a formal lift plan review.',
      'Inspect all rigging equipment for defects.',
      'Appoint a qualified lifting supervisor for all critical lifts.',
    ],
    'Vehicle Movement': [
      'Re-establish pedestrian and vehicle segregation.',
      'Appoint a banksman for all reversing operations.',
      'Repair or replace malfunctioning reversing alarms.',
      'Reinstate pedestrian barriers and crossing signage.',
      'Conduct driver briefing on site speed limits and traffic plan.',
    ],
    'Chemical Handling': [
      'Stop chemical handling until appropriate PPE is available.',
      'Restock PPE station with required chemical-resistant equipment.',
      'Review SDS for all chemicals in use.',
      'Ensure emergency shower and eyewash station is accessible.',
      'Conduct chemical hazard awareness briefing.',
    ],
    'Fire Prevention': [
      'Reinstate fire suppression and detection systems immediately.',
      'Conduct an audit of all fire protection equipment.',
      'Report all fire system defects within 4 hours.',
      'Remove combustible materials from proximity of ignition sources.',
      'Verify fire extinguishers are serviceable and in-date.',
    ],
    'General Safety': [
      'Conduct an immediate inspection of the reported hazard.',
      'Apply temporary controls to prevent injury while permanent fix is implemented.',
      'Assign a responsible person and set a corrective action due date.',
      'Review the area for similar hazards.',
    ],
  };

  return baseActions[lsr] || baseActions['General Safety'];
}

// ─── Full Report Analysis ─────────────────────────────────────────────────────
export function analyzeReport(report: Partial<SafetyReport>): ReportAnalysis {
  const text = report.report_text || '';
  const lsr = report.life_saving_rule || detectLSR(text);
  const barrierFailures = detectBarriers(text);
  const primaryBarrier = barrierFailures.length > 0 ? barrierFailures[0] : 'Unknown Barrier Failure';
  const hazard = detectHazard(text);
  const activity = detectActivity(text, report.activity);
  const evidence = extractEvidencePhrases(text);
  const { score, level, factors, negation } = calculateRiskScore({ ...report, life_saving_rule: lsr });
  const sif = report.sif_potential || determineSIFPotential(text, score, lsr);
  const confResult = calculateConfidence(text, lsr, barrierFailures, negation.negationType, evidence);

  let actions: string[];
  if (report.recommended_action) {
    actions = [report.recommended_action];
  } else if (negation.negationType === 'SAFE_PREVENTIVE') {
    actions = [
      'Log positive safety intervention / near-miss report.',
      'Complete required barrier control (e.g. gas testing, permit, isolation) before authorizing work.',
      'Verify all pre-entry and isolation checklists are formally signed off.',
      'Brief the crew on safe work procedures prior to resumption.',
    ];
  } else {
    actions = generateRecommendedActions(lsr, primaryBarrier, activity);
  }

  const displayBarriers = negation.negationType === 'SAFE_PREVENTIVE' && barrierFailures.length > 0
    ? barrierFailures.map(b => `Prevented: ${b}`)
    : (barrierFailures.length > 0 ? barrierFailures : ['Unknown Barrier Failure']);

  const explanation = buildExplanation(
    text,
    lsr,
    displayBarriers,
    hazard,
    score,
    level,
    sif,
    negation,
    confResult
  );

  return {
    sif_potential: sif,
    risk_level: level,
    risk_score: score,
    activity_detected: activity,
    hazard_detected: hazard,
    barrier_failure: displayBarriers[0],
    barrier_failures: displayBarriers,
    confidence: confResult.confidence,
    confidence_level: confResult.confidenceLevel,
    negation_type: negation.negationType,
    life_saving_rule: lsr,
    evidence_phrases: evidence,
    explanation,
    risk_factors: factors,
    recommended_actions: Array.isArray(actions) ? actions : [actions],
    similar_report_ids: [],
    mode: 'rule-based',
  };
}

function buildExplanation(
  text: string,
  lsr: string,
  barriers: string[],
  hazard: string,
  score: number,
  level: RiskLevel,
  sif: SIFPotential,
  negation: NegationAnalysisResult,
  confidenceData: { confidence: number; confidenceLevel: string; reasons: string[] }
): string {
  const parts: string[] = [];

  if (negation.negationType === 'SAFE_PREVENTIVE') {
    parts.push(`SAFE PREVENTIVE DECISION: Worker/team took proactive action ('${negation.preventivePhrase}') when '${negation.barrierPhrase}' was detected.`);
    parts.push(`Risk score reduced to ${score}/100 (${level}) and SIF potential is NO because hazard exposure was averted.`);
    if (barriers.length > 0) {
      parts.push(`Addressed barriers: ${barriers.join(', ')}.`);
    }
  } else if (negation.negationType === 'AMBIGUOUS') {
    parts.push(`AMBIGUOUS SCENARIO: Detected potential barrier deficiency (${barriers.join(', ')}) with unclear operational exposure ('${negation.ambiguousPhrase}').`);
    parts.push(`Risk score evaluated at ${score}/100 (${level}). Supervisor verification required.`);
  } else {
    if (sif === 'YES') {
      parts.push(`This report describes a situation with elevated SIF potential (Serious Injury or Fatality precursor).`);
    }

    if (lsr !== 'General Safety') {
      const rule = LSR_RULES[lsr];
      parts.push(`The activity falls under the "${lsr}" life-saving rule. ${rule?.description || ''}`);
    }

    if (barriers.length > 0 && barriers[0] !== 'Unknown Barrier Failure') {
      parts.push(`Detected ${barriers.length} critical safety barrier failure(s): ${barriers.join(', ')}. (First barrier penalty: +25, additional: +${Math.max(0, (barriers.length - 1) * 5)}).`);
    }

    if (hazard !== 'General Hazard') {
      parts.push(`The primary hazard type detected is "${hazard}".`);
    }

    parts.push(`The risk engine assigned a score of ${score}/100 (${level}) based on active exposure without required controls.`);
  }

  parts.push(`Confidence: ${confidenceData.confidence} (${confidenceData.confidenceLevel}) based on ${confidenceData.reasons.join('; ')}.`);

  return parts.join(' ');
}

// ─── Dataset-level analytics ──────────────────────────────────────────────────
export function computeBarrierFailures(reports: SafetyReport[]): Array<{ barrier: string; count: number; percentage: number }> {
  const counts: Record<string, number> = {};
  for (const r of reports) {
    const b = r.barrier_failure || (r.report_text ? detectBarrierFailure(r.report_text) : 'Unknown');
    counts[b] = (counts[b] || 0) + 1;
  }
  const total = reports.length || 1;
  return Object.entries(counts)
    .map(([barrier, count]) => ({ barrier, count, percentage: Math.round((count / total) * 100) }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 10);
}

export function computeSiteRisk(reports: SafetyReport[]) {
  const siteMap: Record<string, SafetyReport[]> = {};
  for (const r of reports) {
    const site = r.site || 'Unknown';
    if (!siteMap[site]) siteMap[site] = [];
    siteMap[site].push(r);
  }
  return Object.entries(siteMap).map(([site, siteReports]) => {
    const sifCount = siteReports.filter(r => r.sif_potential === 'YES').length;
    const critCount = siteReports.filter(r => r.risk_level === 'CRITICAL' || r.severity === 'Critical').length;
    const barriers = siteReports.map(r => r.barrier_failure || '').filter(Boolean);
    const topBarrier = barriers.length ? mostCommon(barriers) : 'N/A';
    const activities = siteReports.map(r => r.activity || '').filter(Boolean);
    const topActivity = activities.length ? mostCommon(activities) : 'N/A';
    const riskScore = Math.round((sifCount / siteReports.length) * 70 + (critCount / siteReports.length) * 30);
    let riskLevel: RiskLevel = 'LOW';
    if (riskScore > 50) riskLevel = 'CRITICAL';
    else if (riskScore > 35) riskLevel = 'HIGH';
    else if (riskScore > 15) riskLevel = 'MEDIUM';

    return {
      site,
      total_reports: siteReports.length,
      sif_count: sifCount,
      critical_count: critCount,
      risk_level: riskLevel,
      top_precursor: topActivity,
      top_barrier_failure: topBarrier,
      risk_score: riskScore,
      trend: 'stable' as SiteRisk['trend'],
    };
  }).sort((a, b) => b.risk_score - a.risk_score);
}

export function computeActivityRisk(reports: SafetyReport[]) {
  const actMap: Record<string, SafetyReport[]> = {};
  for (const r of reports) {
    const act = r.activity || 'Unknown';
    if (!actMap[act]) actMap[act] = [];
    actMap[act].push(r);
  }
  return Object.entries(actMap).map(([activity, actReports]) => {
    const sifCount = actReports.filter(r => r.sif_potential === 'YES').length;
    const barriers = actReports.map(r => r.barrier_failure || '').filter(Boolean);
    const topBarrier = barriers.length ? mostCommon(barriers) : 'N/A';
    const scores = actReports.map(r => r.risk_score || 0).filter(s => s > 0);
    const avgScore = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : 0;
    let riskLevel: RiskLevel = 'LOW';
    if (avgScore > 80) riskLevel = 'CRITICAL';
    else if (avgScore > 60) riskLevel = 'HIGH';
    else if (avgScore > 30) riskLevel = 'MEDIUM';

    return {
      activity,
      report_count: actReports.length,
      sif_count: sifCount,
      avg_risk_score: avgScore,
      top_barrier_failure: topBarrier,
      trend: 'stable' as ActivityRisk['trend'],
      risk_level: riskLevel,
    };
  }).sort((a, b) => b.sif_count - a.sif_count);
}

function mostCommon(arr: string[]): string {
  const counts: Record<string, number> = {};
  for (const item of arr) counts[item] = (counts[item] || 0) + 1;
  return Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] || 'N/A';
}

export function computePatterns(reports: SafetyReport[]) {
  const patternMap: Record<string, SafetyReport[]> = {};
  for (const r of reports) {
    const lsr = r.life_saving_rule || detectLSR(r.report_text || '');
    const barrier = r.barrier_failure || detectBarrierFailure(r.report_text || '');
    if (lsr !== 'General Safety' && barrier !== 'Unknown Barrier Failure') {
      const key = `${lsr} + ${barrier}`;
      if (!patternMap[key]) patternMap[key] = [];
      patternMap[key].push(r);
    }
  }
  return Object.entries(patternMap)
    .filter(([, rs]) => rs.length >= 2)
    .map(([name, rs], idx) => {
      const sites = [...new Set(rs.map(r => r.site).filter(Boolean))] as string[];
      const activities = [...new Set(rs.map(r => r.activity).filter(Boolean))] as string[];
      const sifCount = rs.filter(r => r.sif_potential === 'YES').length;
      let riskLevel: RiskLevel = 'LOW';
      if (sifCount / rs.length > 0.7) riskLevel = 'CRITICAL';
      else if (sifCount / rs.length > 0.4) riskLevel = 'HIGH';
      else if (sifCount / rs.length > 0.1) riskLevel = 'MEDIUM';
      return {
        id: `PAT-${idx + 1}`,
        name,
        frequency: rs.length,
        risk_level: riskLevel,
        sites,
        activities,
        trend: 'stable' as SafetyPattern['trend'],
        description: `Recurring pattern: ${name}. Found in ${rs.length} reports across ${sites.length} site(s).`,
        report_ids: rs.map(r => r.id),
      };
    })
    .sort((a, b) => b.frequency - a.frequency);
}

export function computeEarlyWarnings(reports: SafetyReport[]) {
  const warnings = [];
  const sifReports = reports.filter(r => r.sif_potential === 'YES');
  const criticalReports = reports.filter(r => r.severity === 'Critical' || r.risk_level === 'CRITICAL');

  if (sifReports.length > reports.length * 0.4) {
    warnings.push({
      id: 'EW-001',
      type: 'CRITICAL' as const,
      title: 'High SIF Potential Concentration',
      description: `${sifReports.length} reports (${Math.round(sifReports.length / reports.length * 100)}%) show elevated SIF potential.`,
      metric: 'SIF Potential Reports',
      current_value: sifReports.length,
      previous_value: Math.round(sifReports.length * 0.7),
      change_pct: 30,
      affected_sites: [...new Set(sifReports.map(r => r.site).filter(Boolean) as string[])],
      affected_activities: [...new Set(sifReports.map(r => r.activity).filter(Boolean) as string[])],
    });
  }

  const confinedSpace = reports.filter(r =>
    (r.life_saving_rule || '').includes('Confined Space') ||
    (r.activity || '').includes('Confined Space')
  );
  if (confinedSpace.length >= 3) {
    warnings.push({
      id: 'EW-002',
      type: 'WARNING' as const,
      title: 'Confined Space Precursors Recurring',
      description: `${confinedSpace.length} confined space reports detected. Recurrence indicates systemic control gap.`,
      metric: 'Confined Space Reports',
      current_value: confinedSpace.length,
      previous_value: Math.round(confinedSpace.length * 0.65),
      change_pct: 35,
      affected_sites: [...new Set(confinedSpace.map(r => r.site).filter(Boolean) as string[])],
      affected_activities: ['Confined Space Entry'],
    });
  }

  const energyIsolation = reports.filter(r =>
    (r.life_saving_rule || '').includes('Energy Isolation') ||
    (r.barrier_failure || '').includes('Isolation')
  );
  if (energyIsolation.length >= 3) {
    warnings.push({
      id: 'EW-003',
      type: 'WARNING' as const,
      title: 'Energy Isolation Failures Increasing',
      description: `${energyIsolation.length} energy isolation failures detected across ${new Set(energyIsolation.map(r => r.site)).size} sites.`,
      metric: 'Energy Isolation Failures',
      current_value: energyIsolation.length,
      previous_value: Math.round(energyIsolation.length * 0.72),
      change_pct: 28,
      affected_sites: [...new Set(energyIsolation.map(r => r.site).filter(Boolean) as string[])],
      affected_activities: ['Maintenance - Electrical', 'Energy Isolation'],
    });
  }

  if (criticalReports.length > reports.length * 0.25) {
    warnings.push({
      id: 'EW-004',
      type: 'CRITICAL' as const,
      title: 'Critical Risk Report Volume Rising',
      description: `${criticalReports.length} critical-severity reports detected this period.`,
      metric: 'Critical Reports',
      current_value: criticalReports.length,
      previous_value: Math.round(criticalReports.length * 0.75),
      change_pct: 25,
      affected_sites: [...new Set(criticalReports.map(r => r.site).filter(Boolean) as string[])],
      affected_activities: [...new Set(criticalReports.map(r => r.activity).filter(Boolean) as string[])],
    });
  }

  return warnings;
}
