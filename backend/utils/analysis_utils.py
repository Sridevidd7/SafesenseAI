"""
SafeSense AI — Analysis Utilities (Confidence, Validation, Adversarial Guard & Normalization)
=============================================================================================
Module Responsibilities:
1. Input Quality & Adversarial Input Guard (Double negations, speculation, weak signals)
2. Calibrated System Confidence with Component Capping & Penalty Reasoning
3. Safe Risk Normalization (Z-Score with std_dev < 5 instability guard)
4. Strict Validation & Explicit Fallback Contract
"""
from typing import Dict, List, Set, Any, Optional, Tuple
import re
import logging

logger = logging.getLogger("safesense.analysis_utils")

# ─── 1. ADVERSARIAL PATTERNS & SPECULATIVE PHRASES ────────────────────────────

DOUBLE_NEGATION_PATTERNS = [
    re.compile(r"\bnot\s+(?:without|unverified|unsafe|missing|lacking|omitted|absent)\b", re.IGNORECASE),
    re.compile(r"\bnever\s+(?:without|unverified|unsafe|missing|lacking)\b", re.IGNORECASE),
    re.compile(r"\bno\s+lack\s+of\b", re.IGNORECASE),
    re.compile(r"\bwithout\s+no\b", re.IGNORECASE),
]

SPECULATIVE_PATTERNS = [
    re.compile(r"\b(?:maybe|perhaps|possibly|allegedly|supposedly|unconfirmed)\b", re.IGNORECASE),
    re.compile(r"\bnot\s+sure(?:\s+if|\s+whether)?\b", re.IGNORECASE),
    re.compile(r"\bunclear(?:\s+if|\s+whether)?\b", re.IGNORECASE),
    re.compile(r"\buncertain(?:\s+if|\s+whether)?\b", re.IGNORECASE),
    re.compile(r"\bmight\s+have\b", re.IGNORECASE),
    re.compile(r"\bcould\s+be\b", re.IGNORECASE),
    re.compile(r"\bseem(?:s|ed)?\s+to\b", re.IGNORECASE),
    re.compile(r"\bnot\s+confirmed\b", re.IGNORECASE),
]

HIGH_RISK_KEYWORDS = [
    "vessel entry", "confined space entry", "inside reactor", "inside column",
    "live electrical", "energized busbar", "high voltage line", "suspended load",
    "overhead crane lift", "toxic gas leak", "h2s release", "unsecured at height"
]


def detect_adversarial_patterns(text: str) -> Dict[str, Any]:
    """
    Evaluates input text for adversarial or low-clarity signals:
    - Double negations (e.g. 'not without permit')
    - Speculative/uncertain phrasing (e.g. 'maybe unsafe', 'not sure if safe')
    - Weak signal / short fragments (< 4 words)
    """
    if not text or not text.strip():
        return {
            "is_adversarial": True,
            "adversarial_flags": ["Empty input text"],
            "analysis_quality": "LOW",
            "text_clarity": 0.10,
            "confidence_penalty": 0.40,
        }

    raw = text.strip()
    lower = raw.lower()
    words = lower.split()
    word_count = len(words)

    flags: List[str] = []
    penalty = 0.0

    # 1. Double Negations
    for pat in DOUBLE_NEGATION_PATTERNS:
        match = pat.search(lower)
        if match:
            flags.append(f"Double negation detected: '{match.group(0)}'")
            penalty += 0.25

    # 2. Speculative & Unclear Phrasing
    for pat in SPECULATIVE_PATTERNS:
        match = pat.search(lower)
        if match:
            flags.append(f"Speculative phrasing detected: '{match.group(0)}'")
            penalty += 0.20

    # 3. Fragment / Length Evaluation
    if word_count < 4:
        flags.append(f"Fragmented text: short word count ({word_count} words)")
        penalty += 0.25

    flags = list(dict.fromkeys(flags))
    clarity_score = max(0.10, min(1.0, 1.0 - (len(flags) * 0.25) - (0.15 if word_count < 6 else 0.0)))

    if penalty >= 0.35 or word_count < 3:
        quality = "LOW"
    elif penalty > 0.0 or word_count < 6:
        quality = "MEDIUM"
    else:
        quality = "HIGH"

    return {
        "is_adversarial": len(flags) > 0,
        "adversarial_flags": flags,
        "analysis_quality": quality,
        "text_clarity": round(clarity_score, 2),
        "confidence_penalty": round(min(0.50, penalty), 2),
    }


def generate_user_confidence_reason(level: str, analysis_quality: str = "HIGH", barrier_count: int = 1, is_safe_action: bool = False) -> str:
    """Generates plain-English, non-technical confidence explanation for users."""
    if is_safe_action:
        return "High confidence because a proactive safety intervention and verified control step were clearly identified."
    if level == "HIGH":
        if barrier_count >= 2:
            return "High confidence because multiple strong safety violations and clear action words were detected."
        return "High confidence because a specific Life-Saving Rule breach and operational controls were clearly identified."
    elif level == "MEDIUM":
        return "Moderate confidence because key safety concepts were detected, but some operational context or details were limited."
    else:
        return "Low confidence due to speculative wording, fragmented phrasing, or missing operational details. Human verification is recommended."


def generate_input_feedback(quality: str) -> str:
    """Generates user-facing input quality feedback."""
    if quality == "LOW":
        return "Input is unclear or incomplete. Results may be less reliable."
    elif quality == "MEDIUM":
        return "Some details are brief or ambiguous. Verify operational controls manually."
    else:
        return "Input observation is clear and well-structured."


# ─── 2. SYSTEM CONFIDENCE STABILIZATION ───────────────────────────────────────

def calculate_system_confidence(
    barrier_confidence: float,
    rule_confidence: float,
    text_clarity: float,
    confidence_penalty: float = 0.0,
    has_conflicting_signals: bool = False,
    has_weak_evidence: bool = False,
    barrier_count: int = 1,
    is_safe_action: bool = False,
) -> Dict[str, Any]:
    """
    Stabilized system confidence computation:
    - Cap contribution from any single component to at most 0.50
    - Penalize low clarity (< 0.60), conflicting signals, or weak evidence
    - Produce explainable technical confidence_reason AND non-technical confidence_reason_user
    """
    b_conf = max(0.0, min(1.0, float(barrier_confidence)))
    r_conf = max(0.0, min(1.0, float(rule_confidence)))
    t_clarity = max(0.0, min(1.0, float(text_clarity)))
    pen = max(0.0, float(confidence_penalty))

    # Cap individual component contributions to 0.50 max
    barrier_contrib = min(0.50, 0.45 * b_conf)
    rule_contrib = min(0.50, 0.35 * r_conf)
    clarity_contrib = min(0.50, 0.20 * t_clarity)

    additional_penalties: List[str] = []
    total_penalty = pen

    if t_clarity < 0.60:
        total_penalty += 0.15
        additional_penalties.append("low text clarity (-0.15)")

    if has_conflicting_signals:
        total_penalty += 0.20
        additional_penalties.append("conflicting signals (-0.20)")

    if has_weak_evidence or (b_conf <= 0.50 and r_conf <= 0.50):
        total_penalty += 0.15
        additional_penalties.append("weak empirical evidence (-0.15)")

    total_penalty = min(0.65, total_penalty)
    raw_score = barrier_contrib + rule_contrib + clarity_contrib - total_penalty
    score = round(max(0.15, min(0.99, raw_score)), 2)

    if score >= 0.80:
        level = "HIGH"
    elif score >= 0.50:
        level = "MEDIUM"
    else:
        level = "LOW"

    # Construct explainable reason string (technical)
    reason_parts = [
        f"Barrier contribution: {barrier_contrib:.2f} (raw {b_conf:.2f})",
        f"Rule contribution: {rule_contrib:.2f} (raw {r_conf:.2f})",
        f"Clarity: {clarity_contrib:.2f} (raw {t_clarity:.2f})",
    ]
    if additional_penalties:
        reason_parts.append(f"Penalties applied: {', '.join(additional_penalties)}")
    elif total_penalty > 0:
        reason_parts.append(f"Penalty applied: -{total_penalty:.2f}")
    else:
        reason_parts.append("No ambiguity penalties")

    confidence_reason = f"{level} confidence ({score}): " + "; ".join(reason_parts) + "."
    confidence_reason_user = generate_user_confidence_reason(
        level=level,
        analysis_quality="LOW" if total_penalty >= 0.35 else ("MEDIUM" if total_penalty > 0 else "HIGH"),
        barrier_count=barrier_count,
        is_safe_action=is_safe_action,
    )

    return {
        "system_confidence": level,
        "system_confidence_score": score,
        "confidence_reason": confidence_reason,
        "confidence_reason_user": confidence_reason_user,
        "confidence_components": {
            "barrier_contribution": round(barrier_contrib, 2),
            "rule_contribution": round(rule_contrib, 2),
            "clarity_contribution": round(clarity_contrib, 2),
            "total_penalty": round(total_penalty, 2),
        },
    }


# ─── 3. SAFE RISK NORMALIZATION (WITH STD_DEV < 5 GUARD) ──────────────────────

def normalize_risk_score(
    raw_score: float | int,
    mean_risk: float = 50.0,
    std_dev: float = 20.0,
) -> Dict[str, Any]:
    """
    Computes safe dataset-aware risk normalization:
    - IF std_dev < 5:
        disable normalization, return raw_score / 100.0, normalization_applied = False
    - ELSE:
        compute z-score = (raw_score - mean) / std_dev, normalization_applied = True
    """
    try:
        raw = float(raw_score)
        m = float(mean_risk)
        s = float(std_dev)

        if s < 5.0:
            norm_val = round(raw / 100.0, 2)
            applied = False
            decision_log = f"std_dev ({s:.2f}) < 5.0 -> normalization disabled, scaled raw_score/100 ({norm_val})"
        else:
            norm_val = round((raw - m) / s, 2)
            applied = True
            decision_log = f"std_dev ({s:.2f}) >= 5.0 -> z-score normalization applied ({norm_val})"

        logger.info(f"[NORMALIZATION_DECISION] raw_score={raw} normalized_score={norm_val} normalization_applied={applied} details='{decision_log}'")
        return {
            "normalized_score": norm_val,
            "normalization_applied": applied,
            "mean_risk": round(m, 2),
            "std_dev": round(s, 2),
        }
    except Exception as exc:
        logger.warning(f"[NORMALIZATION_DECISION] exception={exc} defaulting to raw_score/100")
        raw_val = float(raw_score) if isinstance(raw_score, (int, float)) else 50.0
        return {
            "normalized_score": round(raw_val / 100.0, 2),
            "normalization_applied": False,
            "mean_risk": 50.0,
            "std_dev": 20.0,
        }


# ─── 4. STRICT VALIDATION & EXPLICIT FALLBACK CONTRACT ────────────────────────

VALID_LSR_NAMES: Set[str] = {
    "Confined Space",
    "Energy Isolation",
    "Hot Work",
    "Working at Height",
    "Line of Fire",
    "Vehicle Movement",
    "Chemical Handling",
    "Fire Prevention",
    "General Safety",
}


def safe_fallback_analysis(report_text: str = "", reason: str = "Fallback triggered") -> Dict[str, Any]:
    """
    Explicit fallback contract:
    Returns deterministic, safe output flagged with source='fallback', reason, fallback_indicator, and confidence='LOW'.
    """
    logger.warning(f"[FALLBACK_TRIGGER] triggered=True reason='{reason}' text='{report_text[:60]}'")
    return {
        "source": "fallback",
        "reason": reason,
        "fallback_indicator": "Limited analysis due to unclear input",
        "input_feedback": "Input is unclear or incomplete. Results may be less reliable.",
        "risk_score": 50,
        "raw_score": 50,
        "normalized_score": 0.50,
        "normalization_applied": False,
        "risk_level": "MEDIUM",
        "risk_reason": "Medium risk evaluated under safe fallback mode due to unclear or limited input.",
        "barrier_failures": ["Unknown Barrier Failure"],
        "barrier_failure": "Unknown Barrier Failure",
        "barrier_evidence": [],
        "confidence": "LOW",
        "confidence_level": "LOW",
        "confidence_score": 0.30,
        "system_confidence": "LOW",
        "system_confidence_score": 0.30,
        "confidence_reason": f"Fallback mode active: {reason}. Supervisor review required.",
        "confidence_reason_user": "Low confidence due to speculative wording, fragmented phrasing, or missing operational details. Human verification is recommended.",
        "analysis_quality": "LOW",
        "adversarial_flags": [reason],
        "sif_potential": "UNKNOWN",
        "life_saving_rule": "General Safety",
        "primary_rule": "General Safety",
        "secondary_rule": None,
        "rule_scores": {"General Safety": 1.0},
        "activity_detected": "General Operation",
        "hazard_detected": "Unspecified hazard",
        "evidence_phrases": [],
        "explanation": f"Safe deterministic fallback: {reason}. Supervisor review advised.",
        "recommended_actions": [
            "Review observation text manually with site supervisor.",
            "Verify operational controls and permits."
        ],
        "mode": "rule-based-fallback",
    }


def validate_analysis_output(result: Dict[str, Any], raw_text: str = "") -> Dict[str, Any]:
    """
    Strict validation layer enforcing:
    - Clamping risk_score within [0, 100]
    - Fallback trigger if invalid rule or unhandled high-risk contradiction
    - Ensuring all contract fields are present (including risk_reason)
    """
    if not isinstance(result, dict):
        return safe_fallback_analysis(raw_text, "Output is not a valid dictionary")

    try:
        # Check explicit fallback trigger
        if result.get("source") == "fallback":
            return result

        # 1. Fallback trigger: Invalid Life-Saving Rule
        lsr = result.get("life_saving_rule")
        if not lsr or (lsr not in VALID_LSR_NAMES and lsr != "General Safety"):
            return safe_fallback_analysis(raw_text, f"Invalid rule classification: '{lsr}'")

        # 2. Fallback trigger: High risk keywords present with zero detected barriers and not safe
        lower_text = raw_text.lower()
        barriers = result.get("barrier_failures", [])
        clean_barriers = [b for b in barriers if b and b != "Unknown Barrier Failure" and not b.startswith("Prevented:")]
        is_safe_state = result.get("negation_type") == "SAFE_PREVENTIVE" or result.get("sif_potential") == "NO"

        has_high_risk_keyword = any(k in lower_text for k in HIGH_RISK_KEYWORDS)
        if has_high_risk_keyword and len(clean_barriers) == 0 and not is_safe_state:
            return safe_fallback_analysis(raw_text, "High risk industrial keywords detected without identifiable barrier controls")

        # 3. Risk Score Validation & Clamping
        raw_score = result.get("raw_score")
        if raw_score is None:
            raw_score = result.get("risk_score", 50)
        try:
            clamped_score = int(round(max(0, min(100, float(raw_score)))))
        except (ValueError, TypeError):
            clamped_score = 50

        result["risk_score"] = clamped_score
        result["raw_score"] = clamped_score

        # 4. Sync Risk Level
        if clamped_score >= 80:
            result["risk_level"] = "CRITICAL"
        elif clamped_score >= 60:
            result["risk_level"] = "HIGH"
        elif clamped_score >= 30:
            result["risk_level"] = "MEDIUM"
        else:
            result["risk_level"] = "LOW"

        # 5. Barrier Cleaning & Deduplication
        if isinstance(barriers, list):
            cleaned: List[str] = []
            for b in barriers:
                if isinstance(b, str) and b.strip() and b.strip() not in cleaned:
                    cleaned.append(b.strip())
            if not cleaned:
                if clamped_score > 30 and result.get("negation_type") in ("UNSAFE_VIOLATION", "PURE_UNSAFE"):
                    result["barrier_failures"] = ["Unknown Barrier Failure"]
                else:
                    result["barrier_failures"] = []
            else:
                result["barrier_failures"] = cleaned
        else:
            result["barrier_failures"] = ["Unknown Barrier Failure"] if clamped_score > 30 else []

        result["barrier_failure"] = result["barrier_failures"][0] if result["barrier_failures"] else None

        # 6. Risk Reason Justification
        if not result.get("risk_reason"):
            lvl = result["risk_level"]
            if result["barrier_failures"]:
                primary_b = result["barrier_failures"][0]
                result["risk_reason"] = f"{lvl.capitalize()} risk due to {primary_b} in {lsr} operations."
            else:
                result["risk_reason"] = f"{lvl.capitalize()} risk due to routine operations with no barrier failure in {lsr}."

        # 7. SIF Potential Validation
        sif = str(result.get("sif_potential", "NO")).upper()
        result["sif_potential"] = sif if sif in ("YES", "NO", "UNKNOWN") else "NO"

        # 8. Source marker
        result["source"] = result.get("source") or "engine"

        return result

    except Exception as exc:
        logger.exception("Validation caught exception, invoking safe fallback.")
        return safe_fallback_analysis(raw_text, f"Validation failure: {str(exc)}")
