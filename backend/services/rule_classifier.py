"""
SafeSense AI — Context-Aware Life-Saving Rule Classifier
=========================================================
Features:
1. Feature-weighted scoring (Strong=5, Medium=3, Weak=1)
2. Action verb contextual boost (+3)
3. Non-industrial false positive context guard
4. Primary + Secondary Life-Saving Rule ranking with tie-breaking
"""
from typing import Dict, List, Set, Any, Optional, Tuple
import re
import logging
from services.barrier_dictionary import normalize_text, NON_INDUSTRIAL_CONTEXT, INDUSTRIAL_INDICATORS

logger = logging.getLogger("safesense.rule_classifier")

# ─── 1. STRUCTURED RULE DEFINITIONS ───────────────────────────────────────────

RULE_DEFINITIONS: Dict[str, Dict[str, List[str]]] = {
    "Confined Space": {
        "strong_signals": [
            "entered vessel", "entered tank", "tank entry", "vessel entry",
            "inside chamber", "inside tank", "inside vessel", "confined space",
            "manhole entry", "column entry", "reactor entry", "inside sump",
            "entered pit", "entered chamber", "entry into tank", "entry into vessel"
        ],
        "medium_signals": [
            "gas testing", "gas test", "atmospheric test", "atmosphere",
            "oxygen", "h2s", "toxic gas", "ventilation", "hole watch",
            "standby person", "vessel", "tank", "chamber", "sump", "pit", "manhole"
        ],
        "weak_signals": [
            "permit", "entry clearance", "drain", "sampling", "confined"
        ]
    },
    "Working at Height": {
        "strong_signals": [
            "at height", "above ground", "elevated platform", "on scaffold",
            "on roof", "climbed ladder", "climbing ladder", "climbed tower",
            "manlift", "cherry picker", "edge protection", "fall arrest",
            "climbed 10", "climbed", "falling from height", "working at height"
        ],
        "medium_signals": [
            "harness", "lanyard", "safety line", "lifeline", "guardrail",
            "scaffold", "scaffolding", "ladder", "roof", "platform",
            "tie off", "tied off"
        ],
        "weak_signals": [
            "ladder", "step", "climb", "tower", "level", "meters", "feet"
        ]
    },
    "Energy Isolation": {
        "strong_signals": [
            "lockout tagout", "lockout", "tagout", "loto", "energized system",
            "live circuit", "de energize", "de energization",
            "energy isolation", "electrical switchgear", "breaker panel",
            "stored energy", "high voltage", "live wire", "live conductor"
        ],
        "medium_signals": [
            "energized valve", "electrical panel", "breaker", "voltage", "switchgear",
            "circuit", "transformer", "substation", "isolation", "isolated",
            "energized", "depressurized"
        ],
        "weak_signals": [
            "power", "wire", "cable", "motor", "pump", "electrical", "cord", "valve"
        ]
    },
    "Hot Work": {
        "strong_signals": [
            "hot work", "welding", "torch cutting", "open flame",
            "grinding sparks", "brazing", "plasma cutting"
        ],
        "medium_signals": [
            "fire watch", "welder", "torch", "arc", "sparks", "flame",
            "flammable", "cutting", "grinding"
        ],
        "weak_signals": [
            "heat", "burn", "spark"
        ]
    },
    "Line of Fire": {
        "strong_signals": [
            "line of fire", "suspended load", "under load", "crane lift",
            "rigging failure", "falling object", "struck by load", "drop zone",
            "below load", "under suspended load"
        ],
        "medium_signals": [
            "crane", "hoist", "rigging", "exclusion zone", "sling",
            "lifting", "overhead load"
        ],
        "weak_signals": [
            "dropped", "struck", "swing", "load"
        ]
    },
    "Vehicle Movement": {
        "strong_signals": [
            "forklift operation", "reversing vehicle", "hgv movement",
            "pedestrian walkway", "vehicle collision", "traffic management",
            "heavy vehicle", "forklift struck"
        ],
        "medium_signals": [
            "forklift", "truck", "vehicle", "excavator", "banksman",
            "reversing", "speeding", "seat belt"
        ],
        "weak_signals": [
            "driver", "traffic", "car", "pedestrian"
        ]
    },
    "Chemical Handling": {
        "strong_signals": [
            "chemical spill", "acid splash", "toxic leak", "caustic exposure",
            "chemical inhalation", "chlorine leak", "ammonia leak",
            "hazardous chemical", "toxic atmosphere"
        ],
        "medium_signals": [
            "acid", "caustic", "toxic", "corrosive", "chemical", "spill",
            "solvent", "inhalation", "ppe"
        ],
        "weak_signals": [
            "fumes", "leak", "drum"
        ]
    },
    "Fire Prevention": {
        "strong_signals": [
            "fire breakout", "combustible fire", "sprinkler discharge",
            "fire suppression", "extinguisher deployed"
        ],
        "medium_signals": [
            "smoke", "fire", "detector", "suppression", "extinguisher",
            "combustible", "flammable"
        ],
        "weak_signals": [
            "alarm", "heat"
        ]
    }
}

RULE_ACTION_WORDS: Dict[str, List[str]] = {
    "Confined Space": ["entered", "entering", "entry", "stepped into", "went into", "inside"],
    "Working at Height": ["climbed", "climbing", "working at", "elevated", "mounted"],
    "Energy Isolation": ["locking", "tagging", "switching", "operating", "opening", "servicing"],
    "Hot Work": ["welding", "cutting", "grinding", "burning", "brazing"],
    "Line of Fire": ["lifting", "rigging", "standing", "walking under"],
    "Vehicle Movement": ["driving", "reversing", "operating", "speeding"],
    "Chemical Handling": ["handling", "pouring", "mixing", "flushing"],
    "Fire Prevention": ["extinguishing", "igniting"],
}


# ─── 2. CORE CLASSIFICATION PIPELINE ──────────────────────────────────────────

def classify_life_saving_rule(text: str) -> Dict[str, Any]:
    """
    Context-aware weighted scoring model for Life-Saving Rules.
    Returns:
    {
      "primary_rule": "Confined Space",
      "secondary_rule": "Energy Isolation" | None,
      "scores": {
        "Confined Space": 14,
        "Energy Isolation": 6, ...
      }
    }
    """
    if not text:
        return {
            "primary_rule": "General Safety",
            "secondary_rule": None,
            "scores": {}
        }

    norm_text = normalize_text(text)
    tokens = set(norm_text.split())

    has_non_industrial = any(re.search(r"\b" + re.escape(ctx) + r"\b", norm_text) for ctx in NON_INDUSTRIAL_CONTEXT)
    has_industrial_marker = any(re.search(r"\b" + re.escape(ind) + r"\b", norm_text) for ind in INDUSTRIAL_INDICATORS)
    is_pure_non_industrial = has_non_industrial and not has_industrial_marker

    scores: Dict[str, int] = {}

    for rule, defs in RULE_DEFINITIONS.items():
        strong_hits = 0
        medium_hits = 0
        weak_hits = 0

        matched_strong: List[str] = []
        # Match strong signals (multi-word phrase search)
        for sig in defs["strong_signals"]:
            if sig in norm_text or re.search(r"\b" + re.escape(sig) + r"\b", norm_text):
                strong_hits += 1
                matched_strong.append(sig)

        # Match medium signals (avoiding duplicate subset matching if already matched in strong)
        for sig in defs["medium_signals"]:
            if (sig in norm_text or re.search(r"\b" + re.escape(sig) + r"\b", norm_text)):
                medium_hits += 1

        # Match weak signals
        for sig in defs["weak_signals"]:
            if sig in tokens or re.search(r"\b" + re.escape(sig) + r"\b", norm_text):
                weak_hits += 1

        score = (strong_hits * 5) + (medium_hits * 3) + (weak_hits * 1)

        # Context Action Boost: If action word specific to this rule exists AND rule has a signal match
        rule_actions = RULE_ACTION_WORDS.get(rule, [])
        has_rule_action = any(re.search(r"\b" + re.escape(act) + r"\b", norm_text) for act in rule_actions)
        if strong_hits > 0 and has_rule_action:
            score += 3

        # Non-Industrial Context Guard:
        # If in office/corridor/desk and there is NO strong industrial signal, zero out the rule
        if is_pure_non_industrial and strong_hits == 0:
            score = 0

        if score > 0:
            scores[rule] = score

    # Ranking & Primary/Secondary resolution
    if not scores:
        return {
            "primary_rule": "General Safety",
            "secondary_rule": None,
            "scores": {}
        }

    sorted_rules = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    primary_rule, primary_score = sorted_rules[0]
    secondary_rule: Optional[str] = None

    if len(sorted_rules) > 1:
        sec_rule, sec_score = sorted_rules[1]
        # Keep secondary rule if score difference <= 3 or secondary has substantial weight (>= 5)
        if abs(primary_score - sec_score) <= 3 or (sec_score >= 5 and sec_score >= primary_score * 0.4):
            secondary_rule = sec_rule

    logger.info(f"[RULE_SELECTED] primary_rule='{primary_rule}' secondary_rule='{secondary_rule}' score={primary_score}")

    return {
        "primary_rule": primary_rule,
        "secondary_rule": secondary_rule,
        "scores": scores
    }


def detect_lsr(text: str) -> str:
    """Return primary Life-Saving Rule (backward compatibility wrapper)."""
    classification = classify_life_saving_rule(text)
    return classification["primary_rule"]

