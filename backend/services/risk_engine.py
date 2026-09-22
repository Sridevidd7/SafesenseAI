"""
SafeSense AI — Backend Risk Engine
===================================
Production-Ready NLP Safety Analysis Engine with:
1. Temporal & Contradiction Awareness (Sentence segmentation & state sequence analysis)
2. Noise Reduction & Prioritization for Long Reports
3. Context-Aware Negation & Preventive Stop Detection
4. Adversarial Input Guard & Text Clarity Scoring
5. Calibrated System Confidence & Risk Normalization
6. Strict Validation & Deterministic Safe Fallback
"""
from typing import Dict, Any, List, Optional, Tuple, Set
import re
import logging

logger = logging.getLogger("safesense.risk_engine")

# ─── Life-Saving Rules ────────────────────────────────────────────────────────
LSR_RULES = {
    "Confined Space": ["confined space", "vessel", "vessel entry", "tank", "tank entry", "gas test", "atmospheric", "oxygen", "h2s", "drain", "pit", "sump", "chamber", "manhole", "column", "reactor"],
    "Energy Isolation": ["lockout", "tagout", "loto", "isolation", "energized", "de-energize", "live circuit", "electrical", "voltage", "stored energy", "switchgear", "breaker"],
    "Hot Work": ["welding", "cutting", "grinding", "hot work", "sparks", "flame", "arc", "torch", "fire watch", "flammable", "brazing"],
    "Working at Height": ["height", "scaffold", "ladder", "roof", "platform", "harness", "fall arrest", "elevated", "guardrail", "edge protection", "manlift", "cherry picker"],
    "Line of Fire": ["line of fire", "suspended load", "crane", "lift", "rigging", "exclusion zone", "struck by", "falling object", "below load", "overhead load"],
    "Vehicle Movement": ["vehicle", "forklift", "hgv", "truck", "reversing", "pedestrian", "banksman", "traffic", "collision", "seat belt", "speeding", "excavator"],
    "Chemical Handling": ["chemical", "acid", "caustic", "toxic", "corrosive", "spill", "ppe", "inhalation", "exposure", "gas leak", "chlorine", "ammonia"],
    "Fire Prevention": ["fire", "smoke", "detector", "suppression", "extinguisher", "flammable", "combustible", "sprinkler"],
}

from services.barrier_dictionary import (
    BARRIER_SYNONYMS,
    BARRIER_KEYWORDS,
    POSITIVE_COMPLETION_PATTERNS,
    normalize_text,
    detect_barriers_with_evidence,
    detect_barriers,
    detect_barrier,
)

# Backward-compatibility alias
BARRIER_PATTERNS = BARRIER_SYNONYMS

from services.rule_classifier import (
    RULE_DEFINITIONS,
    classify_life_saving_rule,
    detect_lsr,
)

from utils.analysis_utils import (
    detect_adversarial_patterns,
    calculate_system_confidence,
    normalize_risk_score,
    validate_analysis_output,
    safe_fallback_analysis,
    generate_input_feedback,
)



# ─── Negation & Context Patterns ──────────────────────────────────────────────

PREVENTIVE_STOP_REGEX = re.compile(
    r"\b("
    r"(?:did\s+not|didn't|does\s+not|doesn't|would\s+not|wouldn't|refused\s+to|decided\s+not\s+to|opted\s+not\s+to|declined\s+to)\s+(?:proceed|enter|start|commence|work|operate|continue|execute|climb|step|go\s+into|begin|resume)|"
    r"(?:work|job|entry|task|operation|activity|maintenance|welding|lifting|pour|process)\s+(?:was\s+)?(?:stopped|halted|suspended|aborted|cancelled|put\s+on\s+hold|paused|delayed|refused|prevented|ceased)|"
    r"stopped\s+(?:work|entry|task|job|activity|operation|hot\s+work|maintenance|welding|climbing)?|"
    r"halted\s+(?:work|entry|task|job|activity|operation)?|"
    r"aborted\s+(?:entry|operation|task|job|activity)?|"
    r"suspended\s+(?:work|entry|task|job|activity|operation)?|"
    r"avoided\s+(?:entering|working|climbing|proceeding|operating|starting|entry|work)?|"
    r"refused\s+(?:to\s+enter|to\s+work|to\s+proceed|to\s+climb|to\s+start|entry)?|"
    r"intervened\s+and\s+stopped|"
    r"held\s+back\s+from|"
    r"stayed\s+back\s+from"
    r")\b",
    re.IGNORECASE
)

NEGATED_STOP_REGEX = re.compile(
    r"\b(?:did\s+not|didn't|failed\s+to|refused\s+to|could\s+not)\s+(?:stop|halt|abort|suspend|cease)\b",
    re.IGNORECASE
)

NEGATED_BARRIER_REGEX = re.compile(
    r"\b("
    r"(?:without|with\s+no|no|missing|lack\s+of|absence\s+of|failed\s+to\s+(?:conduct|perform|obtain|wear|apply|use))\s+"
    r"(?:gas\s+test(?:ing)?|atmospheric\s+test(?:ing)?|testing|permit(?: to work)?|ptw|authorization|clearance|isolation|lockout|tagout|loto|harness|fall\s+protection|fall\s+arrest|ppe|safety\s+glasses|gloves|helmet|mask|respirator|fire\s+watch|standby(?:\s+person)?|attendant|ventilation|guardrail|earthing|grounding|chock|banksman)|"
    r"(?:gas\s+test(?:ing)?|testing|permit|ptw|authorization|isolation|lockout|tagout|loto|harness|fall\s+protection|ppe|fire\s+watch|standby|attendant|ventilation|guardrail)\s+(?:was\s+|were\s+)?(?:not\s+(?:done|obtained|conducted|applied|completed|issued|available|present|worn|used|carried\s+out|tested|performed))|"
    r"not\s+wearing\s+(?:ppe|harness|helmet|gloves|safety\s+glasses|mask|respirator|protection|seat\s*belt)|"
    r"not\s+(?:tested|isolated|depressurized|grounded|authorized|inspected)|"
    r"entry\s+without\s+testing"
    r")\b",
    re.IGNORECASE
)

AMBIGUOUS_INDICATORS = re.compile(
    r"\b("
    r"unclear\s+(?:if|whether)|"
    r"not\s+confirmed\s+(?:if|whether)|"
    r"possibly|"
    r"maybe|"
    r"not\s+sure|"
    r"may\s+have|"
    r"while\s+inspecting|"
    r"inspection\s+only|"
    r"started\s+(?:then|and\s+then)\s+stopped|"
    r"entered\s+(?:then|and\s+then)\s+stopped"
    r")\b",
    re.IGNORECASE
)


# ─── TEMPORAL TRANSITION KEYWORDS ─────────────────────────────────────────────

TEMPORAL_CONNECTIVES = [
    "but later", "and then", "subsequently", "followed by", "after that",
    "however", "prior to", "initially", "later", "then", "afterwards",
    "before", "after", "meanwhile", "eventually"
]

TEMPORAL_SPLIT_PATTERN = re.compile(
    r"\b(but\s+later|and\s+then|subsequently|followed\s+by|after\s+that|however|later|then|afterwards)\b",
    re.IGNORECASE
)


def extract_evidence(text: str) -> List[str]:
    lower = text.lower()
    key_phrases = [
        "confined space", "without gas testing", "without permit", "no permit",
        "without isolation", "lockout", "live circuit", "without harness",
        "welding", "without fire watch", "exclusion zone", "without standby",
        "no standby", "not wearing ppe", "entry without testing", "without testing"
    ]
    evidence = [p for p in key_phrases if p in lower]
    pattern_matches = re.findall(r"(?:without|no|not|missing)\s+\w+(?:\s+\w+)?", lower)
    evidence += [m for m in pattern_matches if m not in evidence]
    return list(set(evidence))[:8]


def analyze_negation_context(text: str) -> Dict[str, Any]:
    """
    Differentiates between:
    1. UNSAFE_VIOLATION: Missing barrier during execution
    2. SAFE_PREVENTIVE: Proactive stop-work or avoidance decision
    3. AMBIGUOUS: Uncertain exposure or mixed execution context
    4. NONE: Standard report without prominent negation
    """
    lower = text.lower().strip()
    if not lower:
        return {
            "negation_type": "NONE",
            "preventive_phrase": None,
            "barrier_phrase": None,
            "interpretation": "Empty or neutral text.",
            "score_impact": "Standard baseline scoring."
        }

    stop_match = PREVENTIVE_STOP_REGEX.search(lower)
    negated_stop_match = NEGATED_STOP_REGEX.search(lower)
    barrier_match = NEGATED_BARRIER_REGEX.search(lower)
    ambiguous_match = AMBIGUOUS_INDICATORS.search(lower)

    # 1. Check for Ambiguity
    if ambiguous_match:
        return {
            "negation_type": "AMBIGUOUS",
            "preventive_phrase": stop_match.group(0) if stop_match else None,
            "barrier_phrase": barrier_match.group(0) if barrier_match else None,
            "ambiguous_phrase": ambiguous_match.group(0),
            "interpretation": f"Ambiguous scenario detected ('{ambiguous_match.group(0)}'). Exposure or execution status is uncertain.",
            "score_impact": "Risk score held at moderate level (MEDIUM, ~45); flagged for supervisor review."
        }

    # 2. Check if a stop was negated (e.g. "did not stop despite no permit")
    if negated_stop_match and barrier_match:
        return {
            "negation_type": "UNSAFE_VIOLATION",
            "preventive_phrase": None,
            "barrier_phrase": barrier_match.group(0),
            "interpretation": f"Active violation: Failed/refused to stop despite missing control ('{barrier_match.group(0)}').",
            "score_impact": "Risk score increased (+25 barrier penalty) and SIF potential flagged YES due to active execution without safety barrier."
        }

    # 3. Preventive Stop Action Detected (Safe decision)
    if stop_match and not negated_stop_match:
        stop_phrase = stop_match.group(0)
        barrier_phrase = barrier_match.group(0) if barrier_match else "missing safety requirement"
        return {
            "negation_type": "SAFE_PREVENTIVE",
            "preventive_phrase": stop_phrase,
            "barrier_phrase": barrier_phrase,
            "interpretation": f"Safe preventive decision: Work was proactively stopped/avoided ('{stop_phrase}') due to '{barrier_phrase}'.",
            "score_impact": "Risk score reduced to LOW (13-20) and SIF potential nullified because proactive intervention prevented hazard exposure."
        }

    # 4. Negated Barrier / Unsafe Condition without Stop Action
    if barrier_match:
        barrier_phrase = barrier_match.group(0)
        return {
            "negation_type": "UNSAFE_VIOLATION",
            "preventive_phrase": None,
            "barrier_phrase": barrier_phrase,
            "interpretation": f"Unsafe condition / barrier violation: Activity performed or attempted without required control ('{barrier_phrase}').",
            "score_impact": "Risk score increased (+25 barrier penalty) and SIF potential flagged YES due to active execution without safety barrier."
        }

    # 5. None
    return {
        "negation_type": "NONE",
        "preventive_phrase": None,
        "barrier_phrase": None,
        "interpretation": "Standard report: No critical negation or stop-work patterns detected.",
        "score_impact": "Scored using standard rule weights."
    }


# ─── 1. TEMPORAL & SENTENCE PARSING (CRITICAL) ────────────────────────────────

def split_into_temporal_clauses(text: str) -> List[Dict[str, Any]]:
    """
    Sentence & Clause Segmentation:
    Splits long or multi-phase text into sequential sentence and temporal clauses.
    Identifies chronological order and safety states per clause.
    """
    if not text or not text.strip():
        return []

    # Step 1: Split on standard sentence punctuation (. ; ! ? \n \r)
    raw_segments = [seg.strip() for seg in re.split(r"[\.\;\!\?\n\r]+", text) if seg.strip()]
    refined_clauses: List[str] = []

    for seg in raw_segments:
        # Step 2: Split inline temporal transitions (e.g. "gas test done but later entry without testing")
        parts = TEMPORAL_SPLIT_PATTERN.split(seg)
        if len(parts) > 1:
            curr = ""
            for p in parts:
                p_clean = p.strip()
                if not p_clean:
                    continue
                if p_clean.lower() in TEMPORAL_CONNECTIVES:
                    if curr.strip():
                        refined_clauses.append(curr.strip())
                    curr = p_clean + " "
                else:
                    curr += p_clean
            if curr.strip():
                refined_clauses.append(curr.strip())
        else:
            refined_clauses.append(seg)

    # Step 3: Analyze each clause sequentially
    parsed_clauses: List[Dict[str, Any]] = []
    for idx, clause in enumerate(refined_clauses):
        cl_lower = clause.lower()
        marker = next((m for m in TEMPORAL_CONNECTIVES if m in cl_lower), None)
        neg_info = analyze_negation_context(clause)

        # Detect barriers within this specific clause
        barriers_with_ev = detect_barriers_with_evidence(clause)
        barrier_names = [b["barrier"] for b in barriers_with_ev]

        # Check positive confirmation within this clause
        has_positive_completion = False
        for pos_patterns in POSITIVE_COMPLETION_PATTERNS.values():
            if any(p.search(cl_lower) for p in pos_patterns):
                has_positive_completion = True
                break

        is_safe = (
            neg_info["negation_type"] == "SAFE_PREVENTIVE" or
            (has_positive_completion and not barrier_names)
        )
        is_unsafe = (
            neg_info["negation_type"] == "UNSAFE_VIOLATION" or
            (len(barrier_names) > 0 and neg_info["negation_type"] != "SAFE_PREVENTIVE")
        )

        parsed_clauses.append({
            "index": idx,
            "clause_text": clause,
            "temporal_marker": marker,
            "negation_type": neg_info["negation_type"],
            "negation_details": neg_info,
            "barriers": barrier_names,
            "barrier_evidence": barriers_with_ev,
            "is_safe": is_safe,
            "is_unsafe": is_unsafe,
        })

    return parsed_clauses


def analyze_temporal_sequence(clauses: List[Dict[str, Any]], raw_text: str) -> Dict[str, Any]:
    """
    Advanced Multi-Stage Temporal & Contradiction Resolver:
    - Maintains a chronological timeline array: e.g. ["SAFE", "UNSAFE", "SAFE", "UNSAFE"]
    - Applies Final Rule: LAST unsafe state dominates UNLESS final state is SAFE with explicit confirmation.
    """
    clause_texts = [c["clause_text"] for c in clauses]
    logger.info(f"[TEMPORAL_SPLIT] input='{raw_text[:60]}...' clause_count={len(clauses)} clauses={clause_texts}")

    if not clauses:
        return {
            "temporal_sequence": "EMPTY",
            "temporal_timeline": [],
            "effective_negation_type": "NONE",
            "effective_barriers": [],
            "effective_barrier_evidence": [],
            "final_state": "NONE",
            "active_clauses": [],
        }

    # Step 1: Assign state per clause and build timeline
    timeline: List[str] = []
    all_unsafe_barriers: List[str] = []
    all_unsafe_evidence: List[Dict[str, Any]] = []

    for c in clauses:
        if c["is_unsafe"]:
            c["state"] = "UNSAFE"
            timeline.append("UNSAFE")
            for b in c["barriers"]:
                if b not in all_unsafe_barriers:
                    all_unsafe_barriers.append(b)
            for ev in c["barrier_evidence"]:
                if ev["barrier"] not in [x["barrier"] for x in all_unsafe_evidence]:
                    all_unsafe_evidence.append(ev)
        elif c["is_safe"]:
            c["state"] = "SAFE"
            timeline.append("SAFE")
        else:
            c["state"] = "NEUTRAL"

    # Filtered active timeline (ignoring neutral statements)
    active_timeline = [s for s in timeline if s in ("SAFE", "UNSAFE")]
    if not active_timeline:
        active_timeline = ["NEUTRAL"]

    # Step 2: Multi-Stage Evaluation
    # Final rule: LAST unsafe state dominates UNLESS final state is SAFE with explicit confirmation
    last_unsafe_idx = max((i for i, c in enumerate(clauses) if c.get("state") == "UNSAFE"), default=-1)
    last_safe_idx = max((i for i, c in enumerate(clauses) if c.get("state") == "SAFE"), default=-1)

    has_unsafe = last_unsafe_idx != -1
    has_safe = last_safe_idx != -1

    if has_unsafe and has_safe:
        if last_unsafe_idx > last_safe_idx:
            # e.g. SAFE -> UNSAFE or SAFE -> UNSAFE -> SAFE -> UNSAFE
            temporal_seq = "SAFE_TO_UNSAFE" if len(active_timeline) == 2 else "MULTI_STAGE_UNSAFE"
            final_state = "UNSAFE_VIOLATION"
            effective_neg = "UNSAFE_VIOLATION"
            effective_barriers = all_unsafe_barriers
            effective_evidence = all_unsafe_evidence
        else:
            # Final state is SAFE with explicit confirmation (e.g. UNSAFE -> SAFE)
            temporal_seq = "UNSAFE_TO_SAFE" if len(active_timeline) == 2 else "MULTI_STAGE_SAFE_RESOLVED"
            final_state = "SAFE_PREVENTIVE"
            effective_neg = "SAFE_PREVENTIVE"
            effective_barriers = all_unsafe_barriers
            effective_evidence = all_unsafe_evidence
    elif has_unsafe:
        temporal_seq = "PURE_UNSAFE"
        final_state = "UNSAFE_VIOLATION"
        effective_neg = "UNSAFE_VIOLATION"
        effective_barriers = all_unsafe_barriers
        effective_evidence = all_unsafe_evidence
    elif has_safe:
        temporal_seq = "PURE_SAFE"
        final_state = "SAFE_PREVENTIVE"
        effective_neg = "SAFE_PREVENTIVE"
        effective_barriers = []
        effective_evidence = []
    else:
        temporal_seq = "NEUTRAL"
        final_state = "NONE"
        effective_neg = "NONE"
        effective_barriers = []
        effective_evidence = []

    logger.info(f"[TEMPORAL_TIMELINE] timeline={active_timeline} sequence={temporal_seq} final_state={final_state}")
    logger.info(f"[TEMPORAL_CLASSIFICATION] sequence={temporal_seq} final_state={final_state} effective_barriers={effective_barriers}")

    return {
        "temporal_sequence": temporal_seq,
        "temporal_timeline": active_timeline,
        "effective_negation_type": effective_neg,
        "effective_barriers": effective_barriers,
        "effective_barrier_evidence": effective_evidence,
        "final_state": final_state,
        "active_clauses": clauses,
    }


# ─── 2. NOISE REDUCTION & RISK CALCULATION ────────────────────────────────────

def calculate_confidence(
    text: str,
    lsr: str,
    barrier_failures: List[str],
    neg_type: str,
    evidence: List[str],
) -> Dict[str, Any]:
    """
    Computes text-level confidence score between 0.20 and 0.98.
    """
    lower = text.lower().strip()
    words = lower.split()
    word_count = len(words)

    score = 0.50
    reasons = []

    # 1. LSR Alignment
    lsr_hits = 0
    if lsr != "General Safety" and lsr in LSR_RULES:
        lsr_hits = sum(1 for k in LSR_RULES[lsr] if re.search(r"\b" + re.escape(k) + r"\b", lower))

    if lsr_hits >= 2:
        score += 0.15
        reasons.append(f"Strong Life-Saving Rule alignment ({lsr_hits} keywords for '{lsr}')")
    elif lsr_hits == 1:
        score += 0.08
        reasons.append(f"Explicit Life-Saving Rule detected ('{lsr}')")
    else:
        score -= 0.05
        reasons.append("General safety context without specific Life-Saving Rule match")

    # 2. Barrier Match Density
    n_barriers = len([b for b in barrier_failures if b != "Unknown Barrier Failure"])
    if n_barriers >= 2:
        score += 0.15
        reasons.append(f"{n_barriers} explicit barrier failures detected")
    elif n_barriers == 1:
        score += 0.10
        reasons.append(f"1 explicit barrier failure detected ('{barrier_failures[0]}')")
    else:
        score -= 0.05
        reasons.append("No standard barrier patterns matched")

    # 3. Evidence phrase support
    if len(evidence) >= 2:
        score += 0.05

    # 4. Sentence Structure Clarity
    has_role = bool(re.search(r"\b(worker|workers|technician|technicians|operator|operators|crew|team|electrician|welder|supervisor|contractor|personnel)\b", lower))
    has_action = bool(re.search(r"\b(entered|proceeded|working|climbed|welding|operating|started|stopped|halted|avoided|refused|conducted|performed|inspected)\b", lower))

    if has_role and has_action:
        score += 0.10
        reasons.append("Clear actor and operational action structure")
    elif has_action or has_role:
        score += 0.05
        reasons.append("Identified operational context")

    # 5. Ambiguity & Conflicting Signals
    if neg_type == "AMBIGUOUS" or AMBIGUOUS_INDICATORS.search(lower):
        score -= 0.35
        reasons.append("Ambiguous or conflicting signals present")
    elif neg_type in ("SAFE_PREVENTIVE", "UNSAFE_VIOLATION"):
        score += 0.05
        reasons.append(f"Unambiguous negation intent ({neg_type})")

    if word_count < 4:
        score -= 0.20
        reasons.append("Fragmented / brief sentence structure")

    confidence = round(min(0.98, max(0.20, score)), 2)
    level = "HIGH" if confidence >= 0.80 else ("MEDIUM" if confidence >= 0.50 else "LOW")

    return {
        "confidence": confidence,
        "confidence_level": level,
        "reasons": reasons,
    }


def calculate_risk_score(report: Dict) -> Dict:
    text = report.get("report_text", "")
    lower = text.lower()
    lsr = report.get("life_saving_rule") or detect_lsr(text)
    
    # Use provided barrier failures or fallback to detector
    barrier_failures = report.get("barrier_failures") or detect_barriers(text)
    # Deduplicate barrier failures to eliminate over-counting in long reports
    barrier_failures = list(dict.fromkeys(b for b in barrier_failures if b and b != "Unknown Barrier Failure"))
    primary_barrier = barrier_failures[0] if barrier_failures else "Unknown Barrier Failure"

    severity = (report.get("severity") or "").lower()
    report_type = (report.get("report_type") or "").lower()

    neg_type = report.get("negation_type") or analyze_negation_context(text)["negation_type"]
    neg_details = report.get("negation_details") or analyze_negation_context(text)

    n_barriers = len(barrier_failures)

    if neg_type == "SAFE_PREVENTIVE":
        # Safe preventive decision: Work was halted/avoided before exposure
        hazard_severity = 10 if lsr != "General Safety" else 5
        barrier_score = 0   # 0 barrier penalty: proactive stop prevented breach
        exposure_score = 2  # exposure prevented
        activity_score = 2
        recurrence_score = 4
        total = hazard_severity + barrier_score + exposure_score + activity_score + recurrence_score
        level = "LOW"
    elif neg_type == "AMBIGUOUS":
        hazard_severity = 18 if lsr != "General Safety" else 10
        barrier_score = min(20, 12 + max(0, n_barriers - 1) * 4) if n_barriers > 0 else 12
        exposure_score = 10
        activity_score = 5
        recurrence_score = 5
        total = hazard_severity + barrier_score + exposure_score + activity_score + recurrence_score
        level = "MEDIUM"
    else:  # UNSAFE_VIOLATION or NONE
        hazard_severity = 28 if (lsr != "General Safety" or "critical" in severity) else (
            22 if "high" in severity else (14 if "medium" in severity else 6)
        )
        # Multi-barrier penalty: 25 for first barrier, +5 for each additional barrier, capped at 35
        if n_barriers == 0:
            barrier_score = 25 if neg_type == "UNSAFE_VIOLATION" else 5
        elif n_barriers == 1:
            barrier_score = 25
        else:
            barrier_score = min(35, 25 + (n_barriers - 1) * 5)

        exposure_score = 20 if any(w in lower for w in ["two worker", "crew", "multiple"]) else (
            16 if any(w in lower for w in ["worker", "technician", "operator"]) else 8
        )
        activity_score = 10 if any(a in lsr for a in ["Confined Space", "Energy Isolation", "Hot Work", "Working at Height"]) else 5
        recurrence_score = 15 if "incident" in report_type else (
            12 if "near miss" in report_type else (10 if "unsafe act" in report_type else 8)
        )
        total = min(100, hazard_severity + barrier_score + exposure_score + activity_score + recurrence_score)
        level = "CRITICAL" if total > 80 else ("HIGH" if total > 60 else ("MEDIUM" if total > 30 else "LOW"))

    return {
        "risk_score": total,
        "raw_score": total,
        "risk_level": level,
        "barrier_failures": barrier_failures,
        "primary_barrier": primary_barrier,
        "negation_type": neg_type,
        "negation_details": neg_details,
        "factors": [
            {"name": "Hazard Severity", "score": hazard_severity, "max_score": 30},
            {"name": "Barrier Failure", "score": barrier_score, "max_score": 35 if n_barriers > 1 else 25},
            {"name": "Exposure", "score": exposure_score, "max_score": 20},
            {"name": "Activity Criticality", "score": activity_score, "max_score": 10},
            {"name": "Recurrence Weight", "score": recurrence_score, "max_score": 15},
        ],
    }


# ─── 3. MAIN REPORT ANALYSIS PIPELINE ─────────────────────────────────────────

def analyze_report(report: Dict) -> Dict:
    """
    Main analysis pipeline:
    1. Adversarial Guard & Quality Check
    2. Temporal & Clause Segmentation (Multi-stage timeline)
    3. Rule Classification & Barrier Detection
    4. Multi-Phase Sequence Resolution (Last unsafe state dominates unless final safe)
    5. Calibrated System Confidence Calculation & Reason Formulation
    6. Safe Dataset-Aware Risk Normalization (std_dev < 5 guard)
    7. Strict Validation & Explicit Fallback Contract
    """
    text = report.get("report_text", "")
    if not text and report.get("description"):
        text = report.get("description")

    try:
        # Step 1: Adversarial & Input Quality Guard
        adversarial_info = detect_adversarial_patterns(text)
        adv_flags = adversarial_info["adversarial_flags"]
        analysis_quality = adversarial_info["analysis_quality"]
        text_clarity = adversarial_info["text_clarity"]
        adv_penalty = adversarial_info["confidence_penalty"]

        # Step 2: Temporal & Sentence Clause Segmentation
        clauses = split_into_temporal_clauses(text)
        temporal_analysis = analyze_temporal_sequence(clauses, text)
        temporal_sequence = temporal_analysis["temporal_sequence"]
        temporal_timeline = temporal_analysis["temporal_timeline"]
        neg_type = temporal_analysis["effective_negation_type"]

        # Step 3: Life-Saving Rule Classification
        rule_classification = classify_life_saving_rule(text)
        lsr = report.get("life_saving_rule") or rule_classification["primary_rule"]
        primary_rule = lsr
        secondary_rule = rule_classification.get("secondary_rule")
        rule_scores = rule_classification.get("scores", {})
        rule_confidence = float(rule_scores.get(primary_rule, 0.70))

        # Step 4: Barrier Evidence & Resolution
        resolved_barriers = temporal_analysis["effective_barriers"]
        resolved_evidence = temporal_analysis["effective_barrier_evidence"]

        if not resolved_barriers:
            if neg_type != "SAFE_PREVENTIVE":
                raw_ev = detect_barriers_with_evidence(text)
                resolved_barriers = [b["barrier"] for b in raw_ev]
                resolved_evidence = raw_ev

        # Deduplicate barrier failures across long inputs
        barrier_failures = list(dict.fromkeys(resolved_barriers))
        barrier_evidence = resolved_evidence
        evidence = extract_evidence(text)

        # Step 5: Risk Score Calculation
        neg_details = analyze_negation_context(text)
        risk_data = calculate_risk_score({
            **report,
            "report_text": text,
            "life_saving_rule": lsr,
            "barrier_failures": barrier_failures,
            "negation_type": neg_type,
            "negation_details": neg_details,
        })

        score = risk_data["risk_score"]
        raw_score = score
        level = risk_data["risk_level"]

        # Step 6: Confidence Calculations & Stabilization
        # 6a. Text-level confidence
        conf_data = calculate_confidence(text, lsr, barrier_failures, neg_type, evidence)
        confidence = conf_data["confidence"]
        confidence_level = conf_data["confidence_level"]
        conf_reasons = conf_data["reasons"]

        # 6b. Calibrated System Confidence with Component Capping
        barrier_top_conf = max([b["confidence_score"] for b in barrier_evidence], default=0.50) if barrier_evidence else 0.50
        has_conflicts = (temporal_sequence in ("SAFE_TO_UNSAFE", "MULTI_STAGE_UNSAFE") and "maybe" in text.lower())
        has_weak = len(barrier_evidence) == 0 and len(evidence) == 0

        sys_conf_data = calculate_system_confidence(
            barrier_confidence=barrier_top_conf,
            rule_confidence=rule_confidence,
            text_clarity=text_clarity,
            confidence_penalty=adv_penalty,
            has_conflicting_signals=has_conflicts,
            has_weak_evidence=has_weak,
        )
        system_confidence = sys_conf_data["system_confidence"]
        system_confidence_score = sys_conf_data["system_confidence_score"]
        confidence_reason = sys_conf_data["confidence_reason"]

        # Step 7: Safe Risk Normalization (Z-Score with std_dev < 5 guard)
        norm_result = normalize_risk_score(raw_score)
        normalized_score = norm_result["normalized_score"]
        normalization_applied = norm_result["normalization_applied"]

        # Step 8: SIF Potential & Explanations
        if neg_type == "SAFE_PREVENTIVE":
            sif_potential = "NO"
            prevented_barriers = [f"Prevented: {b}" for b in barrier_failures] if barrier_failures else ["Safely Controlled"]
            explanation = (
                f"SAFE PREVENTIVE DECISION: Proactive intervention stopped/avoided hazard exposure before breach. "
                f"Risk score reduced to {score}/100 ({level}) and SIF potential is NO. "
                f"Timeline: {' -> '.join(temporal_timeline)}. Quality: {analysis_quality}. "
                f"Confidence: {system_confidence} ({system_confidence_score})."
            )
            display_barriers = prevented_barriers
            recommended_actions = [
                "Log positive safety intervention / proactive stop report.",
                "Complete required barrier control before authorizing work.",
                "Verify pre-entry and isolation checklists are formally signed off.",
                "Brief the crew on safe work procedures prior to resumption."
            ]
        elif neg_type == "AMBIGUOUS" or analysis_quality == "LOW":
            sif_potential = "UNKNOWN"
            explanation = (
                f"AMBIGUOUS SCENARIO / LOW CLARITY: Detected potential barrier deficiency ({', '.join(barrier_failures) if barrier_failures else 'Uncertain'}). "
                f"Risk score evaluated at {score}/100 ({level}). "
                f"Analysis Quality: {analysis_quality} ({'; '.join(adv_flags) if adv_flags else 'Ambiguous wording'}). "
                f"System Confidence: {system_confidence} ({system_confidence_score}). Supervisor verification required."
            )
            display_barriers = barrier_failures if barrier_failures else ["Unknown Barrier Failure"]
            recommended_actions = [
                "Conduct immediate site walkthrough to verify operational status.",
                "Clarify if personnel were exposed before work was stopped.",
                "Ensure permit and safety controls are strictly validated before proceeding."
            ]
        else:
            sif_keywords = ["confined space", "without gas testing", "lockout", "without isolation",
                            "energized", "without harness", "suspended load", "line of fire",
                            "chemical exposure", "oxygen deficient", "pressurized", "no permit", "not wearing", "no standby"]
            has_sif = any(k in text.lower() for k in sif_keywords)
            sif_potential = "YES" if (has_sif or score >= 70) else ("NO" if score <= 30 else "UNKNOWN")

            barrier_summary = f"{len(barrier_failures)} barrier failure(s) detected: {', '.join(barrier_failures)}" if barrier_failures else "Unknown Barrier Failure"
            explanation = (
                f"UNSAFE CONDITION / VIOLATION: Flagged under {lsr} Life-Saving Rule ({temporal_sequence}). {barrier_summary}. "
                f"Timeline: {' -> '.join(temporal_timeline)}. "
                f"Risk score {score}/100 ({level}) increased due to missing safety controls during active work. SIF Potential: {sif_potential}. "
                f"System Confidence: {system_confidence} ({system_confidence_score}). Quality: {analysis_quality}."
            )
            display_barriers = barrier_failures if barrier_failures else ["Unknown Barrier Failure"]
            recommended_actions = [
                "Stop work immediately.",
                "Apply all required barrier controls and obtain necessary permits.",
                "Perform supervisor verification before resuming.",
                "Brief all workers on Life-Saving Rules compliance."
            ]

        raw_output = {
            "source": "engine",
            "fallback_indicator": None,
            "input_feedback": generate_input_feedback(analysis_quality),
            "risk_score": score,
            "raw_score": raw_score,
            "normalized_score": normalized_score,
            "normalization_applied": normalization_applied,
            "risk_level": level,
            "barrier_failures": display_barriers,
            "barrier_failure": display_barriers[0] if display_barriers else "Unknown Barrier Failure",  # backward compat
            "barrier_evidence": barrier_evidence,
            "confidence": confidence,
            "confidence_level": confidence_level,
            "confidence_factors": conf_reasons,
            "system_confidence": system_confidence,
            "system_confidence_score": system_confidence_score,
            "confidence_reason": confidence_reason,
            "confidence_reason_user": sys_conf_data.get("confidence_reason_user", "High confidence in safety control detection."),
            "analysis_quality": analysis_quality,
            "adversarial_flags": adv_flags,
            "temporal_sequence": temporal_sequence,
            "temporal_timeline": temporal_timeline,
            "negation_type": neg_type,
            "negation_details": neg_details,
            "sif_potential": sif_potential,
            "life_saving_rule": lsr,
            "primary_rule": primary_rule,
            "secondary_rule": secondary_rule,
            "rule_scores": rule_scores,
            "activity_detected": report.get("activity") or "General Activity",
            "hazard_detected": "See evidence",
            "evidence_phrases": evidence,
            "explanation": explanation,
            "risk_factors": risk_data["factors"],
            "recommended_actions": recommended_actions,
            "mode": "rule-based",
        }

        # Step 9: Strict Validation & Fallback Guard
        validated_output = validate_analysis_output(raw_output, raw_text=text)
        logger.info(f"[FINAL_MERGED_RESULT] source={validated_output.get('source')} risk_score={validated_output['risk_score']} level={validated_output['risk_level']} barriers={validated_output['barrier_failures']}")
        return validated_output

    except Exception as exc:
        logger.exception(f"Exception during analyze_report for text: '{text[:60]}...'")
        return safe_fallback_analysis(text, reason=str(exc))



# ─── AGGREGATIONS (FOR BACKWARD COMPATIBILITY) ────────────────────────────────

def compute_patterns(reports: List[Dict]) -> List[Dict]:
    pattern_map: Dict[str, List] = {}
    for r in reports:
        text = r.get("report_text", "")
        lsr = r.get("life_saving_rule") or detect_lsr(text)
        barriers = r.get("barrier_failures") or detect_barriers(text)
        barrier = barriers[0] if barriers else detect_barrier(text)
        if lsr != "General Safety" and barrier != "Unknown Barrier Failure":
            key = f"{lsr} + {barrier}"
            pattern_map.setdefault(key, []).append(r)

    result = []
    for i, (name, items) in enumerate(sorted(pattern_map.items(), key=lambda x: -len(x[1]))):
        if len(items) < 2:
            continue
        sites = list(set(r.get("site", "") for r in items if r.get("site")))
        sif_count = sum(1 for r in items if r.get("sif_potential") == "YES")
        pct = sif_count / len(items)
        risk = "CRITICAL" if pct > 0.7 else ("HIGH" if pct > 0.4 else ("MEDIUM" if pct > 0.1 else "LOW"))
        result.append({
            "id": f"PAT-{i+1}", "name": name, "frequency": len(items),
            "risk_level": risk, "sites": sites, "trend": "stable",
            "description": f"Recurring pattern in {len(items)} reports across {len(sites)} site(s).",
        })
    return result


def compute_site_risk(reports: List[Dict]) -> List[Dict]:
    site_map: Dict[str, List] = {}
    for r in reports:
        site = r.get("site") or "Unknown"
        site_map.setdefault(site, []).append(r)

    result = []
    for site, items in site_map.items():
        sif = sum(1 for r in items if r.get("sif_potential") == "YES")
        crit = sum(1 for r in items if r.get("severity") == "Critical" or r.get("risk_level") == "CRITICAL")
        score = round((sif / len(items)) * 70 + (crit / len(items)) * 30)
        level = "CRITICAL" if score > 50 else ("HIGH" if score > 35 else ("MEDIUM" if score > 15 else "LOW"))
        result.append({
            "site": site, "total_reports": len(items),
            "sif_count": sif, "critical_count": crit,
            "risk_level": level, "risk_score": score,
        })
    return sorted(result, key=lambda x: -x["risk_score"])
