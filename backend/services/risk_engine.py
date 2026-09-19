"""
SafeSense AI — Backend Risk Engine
Rule-based NLP analysis with:
- Multi-barrier failure detection and incremental penalty scoring
- Confidence scoring based on keyword density, structural clarity, and ambiguity
- Context-aware negation handling (unsafe violations vs. safe preventive stop-work decisions)
- Scaffolding for ML model integration
"""
from typing import Dict, Any, List, Optional
import re

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

BARRIER_PATTERNS = {
    "Gas Testing Not Completed": ["without gas test", "no gas test", "without atmospheric", "not tested", "gas testing was not done", "gas test was not done", "gas test not done", "gas testing not completed", "gas testing was not completed", "no atmospheric testing"],
    "Permit Not Obtained": ["without permit", "no permit", "permit not obtained", "without authorization", "missing permit", "permit was not issued", "no authorization", "permit not issued", "permit was not obtained", "no valid permit"],
    "Standby Person Not Assigned": ["no standby", "no attendant", "standby not", "without standby", "standby was missing", "no standby person", "attendant not assigned", "standby person not"],
    "Isolation Not Applied": ["without isolat", "no isolation", "not isolated", "isolation not applied", "without lockout", "without loto", "isolation certificate was not", "missing isolation", "isolation was not applied"],
    "Lockout/Tagout Not Completed": ["lockout not applied", "tag not applied", "loto not completed", "lockout not done", "tagout not completed", "no lockout"],
    "Fall Protection Not Used": ["without harness", "no harness", "no fall arrest", "no edge protection", "harness was not available", "harness was missing", "not wearing harness", "without fall protection", "no guardrail"],
    "Exclusion Zone Not Established": ["exclusion zone", "no exclusion", "zone not established", "standing under", "below load", "no exclusion zone"],
    "Fire Watch Not Posted": ["no fire watch", "without fire watch", "fire watch not posted", "missing fire watch", "fire watch was not available"],
    "PPE Not Available": ["without ppe", "no ppe", "without protection", "without gloves", "not wearing ppe", "ppe was missing", "ppe was not available", "not wearing safety glasses", "not wearing helmet", "not wearing mask"],
    "Pressure Not Released": ["not depressurized", "pressure not released", "still under pressure", "line under pressure"],
}

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
    r"(?:gas\s+test(?:ing)?|atmospheric\s+test(?:ing)?|permit(?: to work)?|ptw|authorization|isolation|lockout|tagout|loto|harness|fall\s+protection|fall\s+arrest|ppe|safety\s+glasses|gloves|helmet|mask|respirator|fire\s+watch|standby(?:\s+person)?|attendant|ventilation|guardrail|earthing|grounding|chock|banksman)|"
    r"(?:gas\s+test(?:ing)?|permit|ptw|authorization|isolation|lockout|tagout|loto|harness|fall\s+protection|ppe|fire\s+watch|standby|attendant|ventilation|guardrail)\s+(?:was\s+|were\s+)?(?:not\s+(?:done|obtained|conducted|applied|completed|issued|available|present|worn|used|carried\s+out|tested|performed))|"
    r"not\s+wearing\s+(?:ppe|harness|helmet|gloves|safety\s+glasses|mask|respirator|protection|seat\s*belt)|"
    r"not\s+(?:tested|isolated|depressurized|grounded|authorized|inspected)"
    r")\b",
    re.IGNORECASE
)

AMBIGUOUS_INDICATORS = re.compile(
    r"\b("
    r"unclear\s+(?:if|whether)|"
    r"not\s+confirmed\s+(?:if|whether)|"
    r"possibly|"
    r"may\s+have|"
    r"while\s+inspecting|"
    r"inspection\s+only|"
    r"started\s+(?:then|and\s+then)\s+stopped|"
    r"entered\s+(?:then|and\s+then)\s+stopped"
    r")\b",
    re.IGNORECASE
)


def detect_lsr(text: str) -> str:
    """Return the Life-Saving Rule category with the highest keyword match count."""
    lower = text.lower()
    best, best_score = "General Safety", 0
    for rule, keywords in LSR_RULES.items():
        score = sum(1 for k in keywords if re.search(r"\b" + re.escape(k) + r"\b", lower))
        if score > best_score:
            best_score = score
            best = rule
    return best


def detect_barriers(text: str) -> List[str]:
    """Detect ALL matching barrier failures in the report text."""
    lower = text.lower()
    matched = []
    for barrier, patterns in BARRIER_PATTERNS.items():
        if any(p in lower for p in patterns):
            matched.append(barrier)
    return matched


def detect_barrier(text: str) -> str:
    """Return first detected barrier or fallback (backward compatibility)."""
    barriers = detect_barriers(text)
    return barriers[0] if barriers else "Unknown Barrier Failure"


def extract_evidence(text: str) -> List[str]:
    lower = text.lower()
    key_phrases = [
        "confined space", "without gas testing", "without permit", "no permit",
        "without isolation", "lockout", "live circuit", "without harness",
        "welding", "without fire watch", "exclusion zone", "without standby",
        "no standby", "not wearing ppe",
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


def calculate_confidence(
    text: str,
    lsr: str,
    barrier_failures: List[str],
    neg_type: str,
    evidence: List[str],
) -> Dict[str, Any]:
    """
    Computes a confidence score between 0.0 and 1.0 based on:
    - Keyword density & specificity
    - Structural clarity (subject + action verbs)
    - Presence or absence of conflicting/ambiguous signals
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
    n_barriers = len(barrier_failures)
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
    
    # Detect all barrier failures
    barrier_failures = report.get("barrier_failures") or detect_barriers(text)
    primary_barrier = barrier_failures[0] if barrier_failures else "Unknown Barrier Failure"

    severity = (report.get("severity") or "").lower()
    report_type = (report.get("report_type") or "").lower()

    negation_info = analyze_negation_context(text)
    neg_type = negation_info["negation_type"]

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
        "risk_level": level,
        "barrier_failures": barrier_failures,
        "primary_barrier": primary_barrier,
        "negation_type": neg_type,
        "negation_details": negation_info,
        "factors": [
            {"name": "Hazard Severity", "score": hazard_severity, "max_score": 30},
            {"name": "Barrier Failure", "score": barrier_score, "max_score": 35 if n_barriers > 1 else 25},
            {"name": "Exposure", "score": exposure_score, "max_score": 20},
            {"name": "Activity Criticality", "score": activity_score, "max_score": 10},
            {"name": "Recurrence Weight", "score": recurrence_score, "max_score": 15},
        ],
    }


def analyze_report(report: Dict) -> Dict:
    text = report.get("report_text", "")
    lsr = report.get("life_saving_rule") or detect_lsr(text)
    barrier_failures = report.get("barrier_failures") or detect_barriers(text)
    evidence = extract_evidence(text)

    risk_data = calculate_risk_score({
        **report,
        "life_saving_rule": lsr,
        "barrier_failures": barrier_failures,
    })

    score = risk_data["risk_score"]
    level = risk_data["risk_level"]
    neg_type = risk_data["negation_type"]
    neg_details = risk_data["negation_details"]

    # Confidence calculation
    conf_data = calculate_confidence(text, lsr, barrier_failures, neg_type, evidence)
    confidence = conf_data["confidence"]
    confidence_level = conf_data["confidence_level"]
    conf_reasons = conf_data["reasons"]

    # SIF potential determination
    if neg_type == "SAFE_PREVENTIVE":
        sif_potential = "NO"
        prevented_barriers = [f"Prevented: {b}" for b in barrier_failures] if barrier_failures else ["Safely Controlled"]
        explanation = (
            f"SAFE PREVENTIVE DECISION: Worker/team took proactive action ('{neg_details.get('preventive_phrase')}') "
            f"when '{neg_details.get('barrier_phrase')}' was detected. "
            f"Risk score reduced to {score}/100 ({level}) and SIF potential is NO because exposure was averted. "
            f"Barriers addressed: {', '.join(barrier_failures) if barrier_failures else 'Standard Controls'}. "
            f"Confidence: {confidence} ({confidence_level}) — {'; '.join(conf_reasons)}."
        )
        display_barriers = prevented_barriers
        recommended_actions = [
            "Log positive safety intervention / near-miss report.",
            "Complete required barrier control before authorizing work.",
            "Verify all pre-entry and isolation checklists are formally signed off.",
            "Brief the crew on safe work procedures prior to resumption."
        ]
    elif neg_type == "AMBIGUOUS":
        sif_potential = "UNKNOWN"
        explanation = (
            f"AMBIGUOUS SCENARIO: Detected potential barrier deficiency ({', '.join(barrier_failures) if barrier_failures else 'Uncertain'}) "
            f"with unclear operational exposure ('{neg_details.get('ambiguous_phrase')}'). "
            f"Risk score evaluated at {score}/100 ({level}). Supervisor verification required. "
            f"Confidence: {confidence} ({confidence_level}) — {'; '.join(conf_reasons)}."
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
            f"UNSAFE CONDITION / VIOLATION: Flagged under {lsr} Life-Saving Rule. {barrier_summary}. "
            f"Risk score {score}/100 ({level}) increased due to missing safety controls during active work. SIF Potential: {sif_potential}. "
            f"Confidence: {confidence} ({confidence_level}) — {'; '.join(conf_reasons)}."
        )
        display_barriers = barrier_failures if barrier_failures else ["Unknown Barrier Failure"]
        recommended_actions = [
            "Stop work immediately.",
            "Apply all required barrier controls and obtain necessary permits.",
            "Perform supervisor verification before resuming.",
            "Brief all workers on Life-Saving Rules compliance."
        ]

    return {
        "risk_score": score,
        "risk_level": level,
        "barrier_failures": display_barriers,
        "barrier_failure": display_barriers[0] if display_barriers else "Unknown Barrier Failure",  # backward compat
        "confidence": confidence,
        "confidence_level": confidence_level,
        "confidence_factors": conf_reasons,
        "negation_type": neg_type,
        "negation_details": neg_details,
        "sif_potential": sif_potential,
        "life_saving_rule": lsr,
        "activity_detected": report.get("activity") or "General Activity",
        "hazard_detected": "See evidence",
        "evidence_phrases": evidence,
        "explanation": explanation,
        "risk_factors": risk_data["factors"],
        "recommended_actions": recommended_actions,
        "mode": "rule-based",
    }


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


