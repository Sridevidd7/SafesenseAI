"""
SafeSense AI — Hardened Production-Ready Barrier Detection Engine
==================================================================
Features:
1. Strict Normalization (Contractions expansion, punctuation stripping, whitespace collapse)
2. 4-Layer Hybrid Detection (Flexible Regex Synonyms, Semantic Boost, Keyword Co-occurrence, Weak Signals)
3. Noise & Positive Confirmation Guards (False positive prevention)
4. Domain Conflict Resolution & Deduplication (Merge overlapping concept matches)
5. Multi-Barrier Interaction Severity Boost
6. Confidence Calibration (HIGH >= 0.85, MEDIUM >= 0.60, LOW < 0.60)
7. Explainable Detection Reasons for Judges & Human Reviewers
8. Ranking & Top-K Selection (TOP_K = 3)
"""
from typing import Dict, List, Set, Any, Optional
import re
import string
import logging
import difflib

logger = logging.getLogger("safesense.barrier_dictionary")

# ─── 1. NORMALIZATION & ROBUST INPUT HANDLING ───────────────────────────────

CONTRACTIONS: Dict[str, str] = {
    r"\bdidn't\b": "did not",
    r"\bwasn't\b": "was not",
    r"\bweren't\b": "were not",
    r"\bhaven't\b": "have not",
    r"\bhasn't\b": "has not",
    r"\bhadn't\b": "had not",
    r"\bdon't\b": "do not",
    r"\bdoesn't\b": "does not",
    r"\bwon't\b": "will not",
    r"\bwouldn't\b": "would not",
    r"\bcan't\b": "cannot",
    r"\bcouldn't\b": "could not",
    r"\bshouldn't\b": "should not",
    r"\bisn't\b": "is not",
    r"\baren't\b": "are not",
}

# Common Industrial & Safety Abbreviations
COMMON_ABBREVIATIONS: Dict[str, str] = {
    r"\bloto\b": "lockout tagout",
    r"\bptw\b": "permit to work",
    r"\bppe\b": "personal protective equipment",
    r"\bsds\b": "safety data sheet",
    r"\bswp\b": "safe work permit",
    r"\bjha\b": "job hazard analysis",
    r"\btra\b": "task risk assessment",
    r"\bhgv\b": "heavy vehicle",
    r"\bh2s\b": "hydrogen sulfide",
    r"\bscba\b": "self contained breathing apparatus",
    r"\bapr\b": "air purifying respirator",
}

# Deterministic Typo Normalization Dictionary
COMMON_TYPOS: Dict[str, str] = {
    "gass": "gas",
    "gases": "gas",
    "scafold": "scaffold",
    "scafolding": "scaffold",
    "scaffld": "scaffold",
    "scaffolding": "scaffold",
    "harnes": "harness",
    "harnees": "harness",
    "harnesss": "harness",
    "isloation": "isolation",
    "isolaton": "isolation",
    "isolatn": "isolation",
    "isolt": "isolation",
    "isolat": "isolation",
    "deenergiz": "de-energized",
    "deenergized": "de-energized",
    "de-energise": "de-energized",
    "deenergise": "de-energized",
    "energised": "energized",
    "baricade": "barricade",
    "barricad": "barricade",
    "barakade": "barricade",
    "exclution": "exclusion",
    "exclusn": "exclusion",
    "extingusher": "extinguisher",
    "extingush": "extinguisher",
    "extingwisher": "extinguisher",
    "respirater": "respirator",
    "resprator": "respirator",
    "confind": "confined",
    "confinded": "confined",
    "vessle": "vessel",
    "vesel": "vessel",
    "vessl": "vessel",
    "depresurize": "depressurize",
    "depressurise": "depressurize",
    "depresurised": "depressurized",
    "depresur": "depressurize",
    "unauthoriz": "unauthorized",
    "unauthoris": "unauthorized",
    "linyard": "lanyard",
    "laynard": "lanyard",
    "chemcal": "chemical",
    "chemicl": "chemical",
    "breker": "breaker",
    "braker": "breaker",
}

# Key Safety Vocabulary for Fuzzy Tolerance Match
FUZZY_SAFETY_VOCAB: List[str] = [
    "scaffold", "scaffolding", "harness", "isolation", "barrier", "confined", "respirator",
    "extinguisher", "depressurize", "depressurized", "lockout", "tagout", "testing",
    "permit", "clearance", "barricade", "exclusion", "chemical", "hazard", "equipment",
    "welding", "atmospheric", "oxygen", "voltage", "switchgear", "circuit", "protective",
    "guardrail", "lifeline", "lanyard", "authorized", "authorization", "overhaul"
]

PUNCTUATION_TRANSLATOR = str.maketrans(string.punctuation, " " * len(string.punctuation))


def normalize_text(text: str) -> str:
    """
    Robust Input Normalization:
    1. Contraction expansion (e.g. didn't -> did not)
    2. Common abbreviation expansion (loto -> lockout tagout, ptw -> permit to work, ppe -> personal protective equipment)
    3. Punctuation stripping & clean tokenization
    4. Spelling tolerance via deterministic typo lookup and fuzzy matching for key safety terms
    """
    if not text:
        return ""
    lowered = text.lower()
    
    # 1. Expand contractions
    for pattern, replacement in CONTRACTIONS.items():
        lowered = re.sub(pattern, replacement, lowered)

    # 2. Expand common abbreviations
    for pattern, replacement in COMMON_ABBREVIATIONS.items():
        lowered = re.sub(pattern, replacement, lowered)

    # 3. Strip punctuation
    cleaned = lowered.translate(PUNCTUATION_TRANSLATOR)
    raw_tokens = cleaned.split()

    # 4. Correct typos and apply fuzzy matching for key safety terms
    corrected_tokens: List[str] = []
    for tok in raw_tokens:
        if tok in COMMON_TYPOS:
            corrected_tokens.append(COMMON_TYPOS[tok])
        elif len(tok) >= 5 and tok not in ("without", "during", "before", "after", "worker", "contractor"):
            matches = difflib.get_close_matches(tok, FUZZY_SAFETY_VOCAB, n=1, cutoff=0.82)
            if matches:
                corrected_tokens.append(matches[0])
            else:
                corrected_tokens.append(tok)
        else:
            corrected_tokens.append(tok)

    normalized_str = " ".join(corrected_tokens)
    logger.info(f"[INPUT_NORMALIZED] input='{text[:60]}...' normalized='{normalized_str[:60]}...'")
    return normalized_str


# ─── 2. DOMAIN MERGE & CONFLICT RESOLUTION MAP ────────────────────────────────

MERGE_MAP: Dict[str, str] = {
    "oxygen": "Gas Testing Not Completed",
    "atmosphere": "Gas Testing Not Completed",
    "atmospheric": "Gas Testing Not Completed",
    "gas": "Gas Testing Not Completed",
    "ptw": "Permit Not Obtained",
    "clearance": "Permit Not Obtained",
    "authorization": "Permit Not Obtained",
    "permit": "Permit Not Obtained",
    "harness": "Fall Protection Not Used",
    "lanyard": "Fall Protection Not Used",
    "lifeline": "Fall Protection Not Used",
    "tie off": "Fall Protection Not Used",
    "lockout": "Lockout/Tagout Not Completed",
    "tagout": "Lockout/Tagout Not Completed",
    "loto": "Lockout/Tagout Not Completed",
    "isolation": "Isolation Not Applied",
    "de energized": "Isolation Not Applied",
    "standby": "Standby Person Not Assigned",
    "attendant": "Standby Person Not Assigned",
    "hole watch": "Standby Person Not Assigned",
    "exclusion zone": "Exclusion Zone Not Established",
    "barricade": "Exclusion Zone Not Established",
    "fire watch": "Fire Watch Not Posted",
    "ppe": "PPE Not Available",
    "depressurize": "Pressure Not Released",
}


# ─── 3. CONTEXT & POSITIVE CONFIRMATION GUARDS (NOISE FILTERS) ────────────────

NON_INDUSTRIAL_CONTEXT: List[str] = [
    "office", "corridor", "desk", "cabin", "walkway", "canteen", "cafeteria",
    "parking lot", "reception", "restroom", "lobby", "breakroom", "kitchen", "pantry"
]

INDUSTRIAL_INDICATORS: List[str] = [
    "vessel", "tank", "confined space", "substation", "transformer", "high voltage",
    "switchgear", "scaffold", "crane", "rigging", "pipeline", "furnace", "reactor",
    "column", "manifold", "breaker panel", "generator", "plant", "refinery", "tower"
]

INDUSTRIAL_ONLY_BARRIERS: Set[str] = {
    "Energy Isolation",
    "Lockout/Tagout Not Completed",
    "Gas Testing Not Completed",
    "Pressure Not Released",
    "Fall Protection Not Used",
    "Fire Watch Not Posted",
}

POSITIVE_COMPLETION_PATTERNS: Dict[str, List[re.Pattern]] = {
    "Gas Testing Not Completed": [
        re.compile(r"\b(?:gas\s+test(?:ing)?|atmospheric\s+test(?:ing)?|oxygen\s+test(?:ing)?|testing)\s+(?:was\s+|were\s+|is\s+)?(?:completed|conducted|performed|done|verified|confirmed|passed)\b"),
        re.compile(r"\b(?:completed|conducted|performed|done)\s+(?:the\s+)?(?:gas\s+test(?:ing)?|atmospheric\s+test(?:ing)?|testing)\b"),
        re.compile(r"\bgas\s+(?:was\s+)?tested\b"),
    ],
    "Permit Not Obtained": [
        re.compile(r"\b(?:permit|ptw|authorization|clearance)\s+(?:was\s+|were\s+)?(?:obtained|issued|signed|authorized|approved|in\s+place|completed)\b"),
        re.compile(r"\b(?:obtained|issued|approved)\s+(?:the\s+)?(?:permit|ptw|authorization|clearance)\b"),
    ],
    "Fall Protection Not Used": [
        re.compile(r"\b(?:harness|fall\s+protection)\s+(?:was\s+|were\s+)?(?:worn|used|attached|tied\s+off|secured)\b"),
        re.compile(r"\b(?:wearing|used|tied\s+off\s+with)\s+(?:safety\s+)?(?:harness|fall\s+protection)\b"),
    ],
    "Lockout/Tagout Not Completed": [
        re.compile(r"\b(?:lockout|tagout|loto)\s+(?:was\s+|were\s+)?(?:applied|completed|performed|done|installed)\b"),
    ],
    "Isolation Not Applied": [
        re.compile(r"\b(?:isolation|circuit|equipment|line)\s+(?:was\s+|were\s+)?(?:isolated|de\s*energized|switched\s+off)\b"),
    ],
}


# ─── 4. FLEXIBLE REGEX PATTERNS (STAGE A) ─────────────────────────────────────

BARRIER_REGEX_PATTERNS: Dict[str, List[re.Pattern]] = {
    "Gas Testing Not Completed": [
        re.compile(r"\b(?:without|no|not|missing|lacked|forgot|omitted|skipped|bypassed|neglected|failed\s+to(?:\s+conduct|\s+perform)?)\s+(?:to\s+)?(?:conduct\s+|perform\s+|do\s+)?(?:any\s+)?(?:gas|atmospheric|atmosphere|oxygen|air)\s+(?:test(?:ing)?|check(?:ing)?|sampling|monitoring|levels?|measurement)\b"),
        re.compile(r"\b(?:gas|atmospheric|atmosphere|oxygen|air)\s+(?:levels?|sampling|test(?:ing)?|check(?:ing)?|monitoring)\s+(?:were|was|is|are)?\s*(?:not|never|omitted|skipped|forgotten|neglected)\s*(?:done|completed|conducted|performed|tested|checked|monitored|taken|measured)\b"),
        re.compile(r"\b(?:not|never|forgot\s+to|omitted\s+to)\s+(?:tested|test|checked|check|monitored|sampled)\s+(?:for\s+gas|the\s+atmosphere|atmospheric|air\s+quality|oxygen|gas\s+levels)\b"),
        re.compile(r"\b(?:without|no|forgot|skipped|omitted)\s+(?:gas\s+test|gas\s+testing|atmospheric\s+test|atmospheric\s+testing|gas\s+check)\b"),
        re.compile(r"\b(?:skipped|omitted|neglected|forgot)\s+(?:gas\s+test|atmospheric\s+test|gas\s+monitoring)\b"),
        re.compile(r"\b(?:without|no)\s+(?:any\s+)?testing\b"),
        re.compile(r"\bentry\s+without\s+testing\b"),
    ],
    "Permit Not Obtained": [
        re.compile(r"\b(?:without|no|not|missing|lacked|skipped|omitted|forgot|bypassed|failed\s+to\s+obtain)\s+(?:to\s+obtain\s+)?(?:any\s+)?(?:valid\s+)?(?:work\s+)?(?:permit|clearance|ptw|authorization|approval|entry\s+clearance|entry\s+permit)\b"),
        re.compile(r"\b(?:permit|ptw|authorization|clearance|entry\s+clearance|work\s+permit)\s+(?:was|were|is|are)?\s*(?:not|never)\s*(?:issued|obtained|authorized|approved|signed|granted)\b"),
        re.compile(r"\bentered\s+(?:.*?\s+)?without\s+(?:any\s+)?(?:clearance|permit|authorization|approval|ptw)\b"),
        re.compile(r"\bunauthorized\s+(?:entry|work|activity)\b"),
        re.compile(r"\bno\s+permit\s+was\s+issued\b"),
    ],
    "Fall Protection Not Used": [
        re.compile(r"\b(?:without|no|not|missing|lacked|forgot|omitted|skipped|bypassed)\s+(?:any\s+)?(?:safety\s+)?(?:harness|fall\s+protection|fall\s+arrest|guardrail|edge\s+protection|lifeline|safety\s+line|lanyard)\b"),
        re.compile(r"\b(?:not|never|forgot\s+to\s+wear)\s+(?:wearing|tied\s+off|hooked\s+up|attached|secured)\s+(?:with\s+)?(?:a\s+)?(?:safety\s+)?(?:harness|at\s+height|to\s+lifeline|fall\s+protection)?\b"),
        re.compile(r"\b(?:worker|technician|personnel|contractor|operator)\s+(?:was\s+|were\s+)?not\s+tied\s+off\b"),
        re.compile(r"\bunsecured\s+at\s+height\b"),
        re.compile(r"\bnot\s+tied\s+off\s+at\s+height\b"),
    ],
    "Lockout/Tagout Not Completed": [
        re.compile(r"\b(?:without|no|not|missing|forgot|omitted|skipped|bypassed)\s+(?:lockout|tagout|loto|breaker\s+lock|padlock)\b"),
        re.compile(r"\b(?:lockout|tagout|loto)\s+(?:was|were)?\s*(?:not|never)\s*(?:applied|done|completed|performed|installed)\b"),
        re.compile(r"\bloto\s+not\s+(?:done|applied|completed)\b"),
    ],
    "Isolation Not Applied": [
        re.compile(r"\b(?:without|no|not|missing|forgot|omitted|skipped|bypassed)\s+(?:energy\s+)?(?:isolation|isolating)\b"),
        re.compile(r"\b(?:energy|circuit|power|system|equipment|line)\s+(?:was|were)?\s*(?:not|never)\s*(?:isolated|de\s*energized|switched\s+off)\b"),
        re.compile(r"\b(?:live\s+circuit|energized\s+system)\s+(?:was\s+)?not\s+isolated\b"),
        re.compile(r"\bnot\s+de\s*energized\b"),
    ],
    "Standby Person Not Assigned": [
        re.compile(r"\b(?:without|no|not|missing|forgot|omitted)\s+(?:any\s+)?(?:standby|standby\s+person|attendant|hole\s+watch|watcher|sentry)\b"),
        re.compile(r"\b(?:standby(?:\s+person)?|attendant|hole\s+watch)\s+(?:was|were)?\s*(?:not|never)\s*(?:assigned|present|posted|stationed|available)\b"),
    ],
    "Exclusion Zone Not Established": [
        re.compile(r"\b(?:without|no|not|missing|forgot|omitted)\s+(?:any\s+)?(?:exclusion\s+zone|barricade|perimeter|drop\s+zone|warning\s+tape)\b"),
        re.compile(r"\b(?:exclusion\s+zone|barricade)\s+(?:was|were)?\s*(?:not|never)\s*(?:established|set\s+up|created|posted|demarcated)\b"),
        re.compile(r"\bstanding\s+(?:under|below|beneath)\s+(?:a\s+)?(?:suspended\s+)?load\b"),
    ],
    "Fire Watch Not Posted": [
        re.compile(r"\b(?:without|no|not|missing|forgot|omitted)\s+(?:any\s+)?(?:fire\s+watch|fire\s+guard|spark\s+watch)\b"),
        re.compile(r"\b(?:fire\s+watch|fire\s+guard)\s+(?:was|were)?\s*(?:not|never)\s*(?:posted|assigned|present|available|stationed)\b"),
    ],
    "PPE Not Available": [
        re.compile(r"\b(?:without|no|not|missing|forgot|omitted)\s+(?:any\s+)?(?:ppe|protective\s+equipment|gloves|safety\s+glasses|eye\s+protection|helmet|hard\s+hat|mask|respirator)\b"),
        re.compile(r"\bnot\s+wearing\s+(?:any\s+)?(?:ppe|gloves|safety\s+glasses|eye\s+protection|helmet|hard\s+hat|mask|respirator|protection)\b"),
    ],
    "Pressure Not Released": [
        re.compile(r"\b(?:not|never|was\s+not|forgot\s+to|omitted\s+to)\s+(?:depressurized|vented|bled|drained)\b"),
        re.compile(r"\b(?:pressure|line|vessel|system)\s+(?:was\s+)?(?:not\s+released|still\s+under\s+pressure|not\s+depressurized|not\s+bled|not\s+vented)\b"),
        re.compile(r"\bresidual\s+pressure\s+(?:not\s+bled|remained)\b"),
    ],
}

BARRIER_SYNONYMS: Dict[str, List[str]] = {
    "Gas Testing Not Completed": [
        "no gas test", "no gas testing", "without gas test", "without gas testing",
        "gas testing not done", "gas test not done", "gas testing was not done",
        "gas test was not done", "gas testing not completed", "gas testing was not completed",
        "gas test not completed", "no atmospheric test", "no atmospheric testing",
        "without atmospheric test", "without atmospheric testing", "atmospheric test missing",
        "no atmospheric test done", "gas check not performed", "no gas check",
        "gas check missing", "gas monitoring not conducted", "not tested for gas",
        "gas not tested", "atmosphere not tested", "oxygen levels were not checked",
        "oxygen levels not checked",
    ],
    "Permit Not Obtained": [
        "no permit", "no work permit", "permit not obtained", "permit was not obtained",
        "permit not issued", "permit was not issued", "no permit was issued",
        "without permit", "without work permit", "without authorization",
        "no authorization", "missing permit", "work permit missing", "no valid permit",
        "entry not authorized", "unauthorized entry", "unauthorized work",
        "ptw not issued", "ptw not obtained", "without ptw", "no ptw",
        "without clearance or permit", "without any clearance or permit",
    ],
    "Fall Protection Not Used": [
        "no harness", "without harness", "no safety harness", "not wearing harness",
        "not wearing safety harness", "no fall protection", "without fall protection",
        "fall protection not used", "fall protection missing", "no fall arrest",
        "without fall arrest", "not tied off", "not tied off at height",
        "harness was missing", "harness was not available", "no guardrail",
        "no edge protection", "no safety line", "unsecured at height",
        "working at height without harness",
    ],
    "Lockout/Tagout Not Completed": [
        "lockout not applied", "tag not applied", "tagout not applied",
        "loto not completed", "loto not done", "loto not applied", "lockout not done",
        "lockout not completed", "tagout not completed", "no lockout", "without lockout",
        "without loto", "no loto", "loto missing",
    ],
    "Isolation Not Applied": [
        "without isolation", "without isolat", "no isolation", "not isolated",
        "isolation not applied", "isolation was not applied", "missing isolation",
        "isolation missing", "energy not isolated", "not de energized", "not deenergized",
        "live circuit not isolated", "power not isolated",
    ],
    "Standby Person Not Assigned": [
        "no standby", "no standby person", "standby person not assigned",
        "standby not assigned", "without standby", "standby was missing",
        "no attendant", "attendant not assigned", "no hole watch", "hole watch missing",
    ],
    "Exclusion Zone Not Established": [
        "no exclusion zone", "exclusion zone not established", "exclusion zone missing",
        "without exclusion zone", "no exclusion", "zone not established",
        "standing under suspended load", "standing under load", "below load",
        "standing below load", "no barricade", "drop zone not cleared",
    ],
    "Fire Watch Not Posted": [
        "no fire watch", "without fire watch", "fire watch not posted",
        "missing fire watch", "fire watch missing", "no fire guard",
    ],
    "PPE Not Available": [
        "without ppe", "no ppe", "missing ppe", "ppe was missing", "ppe was not available",
        "ppe not available", "ppe not worn", "not wearing ppe", "without protection",
        "without gloves", "not wearing gloves", "not wearing safety glasses",
        "not wearing eye protection", "not wearing helmet", "not wearing mask",
    ],
    "Pressure Not Released": [
        "pressure not released", "not depressurized", "was not depressurized",
        "still under pressure", "line under pressure", "system not depressurized",
        "pressure not bled",
    ],
}


# ─── 5. SEMANTIC EQUIVALENTS (STAGE B) ────────────────────────────────────────

SEMANTIC_EQUIVALENTS: Dict[str, List[str]] = {
    "Gas Testing Not Completed": [
        "atmospheric check", "oxygen test", "gas sampling", "atmospheric testing",
        "oxygen levels", "gas check", "air monitoring", "testing procedure",
        "gas measurement", "oxygen sampling", "air quality check"
    ],
    "Permit Not Obtained": [
        "authorization", "approval", "entry clearance", "ptw", "work clearance",
        "clearance", "entry permit", "formal permit", "work authorization"
    ],
    "Fall Protection Not Used": [
        "safety harness", "fall arrest", "tie off", "lanyard", "lifeline",
        "edge protection", "height safety", "anchor point", "fall restraint"
    ],
    "Lockout/Tagout Not Completed": [
        "lockout tagout", "loto application", "breaker lockout", "padlock application",
        "circuit isolation tag", "hasp locking"
    ],
    "Isolation Not Applied": [
        "energy isolation", "de energization", "power cutoff", "electrical disconnection",
        "system isolation", "circuit de energize"
    ],
    "Standby Person Not Assigned": [
        "safety watcher", "safety attendant", "hole watch", "standby monitor",
        "entry watcher", "standby observer"
    ],
    "Exclusion Zone Not Established": [
        "perimeter barricade", "drop zone clearance", "red zone demarcation",
        "lift exclusion", "safety perimeter"
    ],
    "Fire Watch Not Posted": [
        "spark watch", "fire guard", "extinguisher standby", "hot work watch"
    ],
    "PPE Not Available": [
        "personal protective equipment", "safety gear", "face shield",
        "respirator unit", "eye protection", "hard hat"
    ],
    "Pressure Not Released": [
        "pressure release", "line venting", "bleed off", "residual pressure",
        "hydraulic release", "line depressurization"
    ],
}


# ─── 6. KEYWORDS & WEAK SIGNALS (STAGE C & D) ─────────────────────────────────

BARRIER_KEYWORDS: Dict[str, Set[str]] = {
    "Gas Testing Not Completed": {
        "gas", "atmospheric", "atmosphere", "testing", "test", "tested", "check",
        "oxygen", "h2s", "sampling", "monitoring", "procedure"
    },
    "Permit Not Obtained": {
        "permit", "ptw", "authorization", "authorized", "clearance", "approval"
    },
    "Fall Protection Not Used": {
        "harness", "lanyard", "anchor", "anchorage", "tied", "tie", "lifeline",
        "guardrail", "fall", "arrest", "height"
    },
    "Lockout/Tagout Not Completed": {
        "lockout", "tagout", "loto", "padlock", "breaker", "hasp"
    },
    "Isolation Not Applied": {
        "isolation", "isolated", "isolate", "de-energized", "deenergized", "energized", "power"
    },
    "Standby Person Not Assigned": {
        "standby", "attendant", "watcher", "watchperson", "hole-watch", "sentry"
    },
    "Exclusion Zone Not Established": {
        "exclusion", "barricade", "perimeter", "demarcation", "cordon", "suspended", "load"
    },
    "Fire Watch Not Posted": {
        "firewatch", "fire", "watch", "extinguisher", "spark-watch"
    },
    "PPE Not Available": {
        "ppe", "glasses", "gloves", "helmet", "respirator", "mask", "goggles", "shield"
    },
    "Pressure Not Released": {
        "depressurized", "depressurize", "pressure", "bled", "bleed", "venting", "vented", "vent"
    },
}

NEGATION_INDICATORS: Set[str] = {
    "no", "not", "without", "missing", "lack", "lacked", "absence", "failed", "failure",
    "unauthorized", "unperformed", "untested", "unsecured", "unisolated", "skipped",
    "omitted", "neglected", "never", "did not", "was not", "were not", "cannot"
}

WEAK_CONTEXT_PATTERNS: Dict[str, List[re.Pattern]] = {
    "Gas Testing Not Completed": [
        re.compile(r"\b(?:gas\s+test|testing|atmosphere|atmospheric\s+check)\s+(?:was\s+|is\s+)?(?:unclear|uncertain|unconfirmed|inconclusive|doubtful)\b"),
        re.compile(r"\b(?:unclear|uncertain|unconfirmed)\s+(?:if|whether)\s+(?:gas\s+test|testing|atmosphere)\b"),
        re.compile(r"\btesting\s+unclear\b"),
    ],
    "Permit Not Obtained": [
        re.compile(r"\b(?:permit|clearance|ptw)\s+(?:was\s+|is\s+)?(?:unclear|uncertain|unconfirmed)\b"),
    ],
    "Fall Protection Not Used": [
        re.compile(r"\b(?:harness|fall\s+protection|tie\s+off)\s+(?:was\s+|is\s+)?(?:unclear|uncertain|unconfirmed)\b"),
    ],
    "Isolation Not Applied": [
        re.compile(r"\b(?:isolation|de\s*energization)\s+(?:was\s+|is\s+)?(?:unclear|uncertain|unconfirmed)\b"),
    ],
}


# ─── 7. EXPLAINABILITY REASON GENERATOR ────────────────────────────────────────

REASON_TEMPLATES: Dict[str, str] = {
    "Gas Testing Not Completed": "Matched {method} signal '{phrase}' indicating missing atmospheric verification or unverified gas levels.",
    "Permit Not Obtained": "Matched {method} signal '{phrase}' indicating missing work authorization, clearance, or valid PTW.",
    "Fall Protection Not Used": "Matched {method} signal '{phrase}' indicating missing safety harness, tie-off, or edge protection at height.",
    "Lockout/Tagout Not Completed": "Matched {method} signal '{phrase}' indicating lack of applied lockout/tagout padlocks or isolation tags.",
    "Isolation Not Applied": "Matched {method} signal '{phrase}' indicating electrical or energy source was not de-energized/isolated.",
    "Standby Person Not Assigned": "Matched {method} signal '{phrase}' indicating absence of required safety standby watcher/attendant.",
    "Exclusion Zone Not Established": "Matched {method} signal '{phrase}' indicating missing barricade/perimeter or personnel below suspended load.",
    "Fire Watch Not Posted": "Matched {method} signal '{phrase}' indicating hot work performed without assigned fire guard/watch.",
    "PPE Not Available": "Matched {method} signal '{phrase}' indicating missing or unworn mandatory personal protective equipment.",
    "Pressure Not Released": "Matched {method} signal '{phrase}' indicating line/vessel was not depressurized or bled before opening.",
}


def calibrate_confidence(conf: float) -> str:
    """Calibrates numerical confidence into human-interpretable severity bands."""
    if conf >= 0.85:
        return "HIGH"
    elif conf >= 0.60:
        return "MEDIUM"
    else:
        return "LOW"


def generate_detection_reason(barrier: str, method: str, evidence: List[str]) -> str:
    """Produces explainable detection reason for judges and safety audits."""
    phrase = evidence[0] if evidence else barrier
    template = REASON_TEMPLATES.get(
        barrier,
        "Matched {method} signal '{phrase}' indicating critical safety control failure."
    )
    return template.format(method=method, phrase=phrase)


# ─── 8. CORE HYBRID DETECTION PIPELINE ────────────────────────────────────────

def detect_barriers_with_evidence(text: str) -> List[Dict[str, Any]]:
    """
    Hardened 4-Layer Hybrid Detection Engine:
    1. Layer 1 Normalization (contractions, whitespace, punctuation).
    2. Layer 2 Hybrid Matchers (Flexible Regex, Semantic Boost, Keyword Co-occurrence, Weak Signals).
    3. Layer 3 Noise Filter & Context Guard (Non-industrial guard + positive completion verification).
    4. Layer 4 Conflict Resolution, Deduplication, Multi-Barrier Boost, Calibration & Top-K Ranking.
    """
    if not text:
        return []

    norm_text = normalize_text(text)
    tokens = set(norm_text.split())

    has_non_industrial = any(re.search(r"\b" + re.escape(ctx) + r"\b", norm_text) for ctx in NON_INDUSTRIAL_CONTEXT)
    has_industrial_marker = any(re.search(r"\b" + re.escape(ind) + r"\b", norm_text) for ind in INDUSTRIAL_INDICATORS)
    is_pure_non_industrial = has_non_industrial and not has_industrial_marker

    has_negation = bool(tokens & NEGATION_INDICATORS) or any(
        neg in norm_text for neg in ["no ", "without ", "not ", "missing ", "skipped ", "omitted ", "failed "]
    )

    detected: Dict[str, Dict[str, Any]] = {}

    # ── Stage A: Flexible Regex & Synonym Matching (High Confidence: 0.88 – 0.98)
    for barrier, patterns in BARRIER_REGEX_PATTERNS.items():
        matched_phrases = []
        for pat in patterns:
            match = pat.search(norm_text)
            if match:
                matched_phrases.append(match.group(0))

        if barrier in BARRIER_SYNONYMS:
            for syn in BARRIER_SYNONYMS[barrier]:
                norm_syn = normalize_text(syn)
                if norm_syn and norm_syn in norm_text:
                    if norm_syn not in matched_phrases:
                        matched_phrases.append(norm_syn)

        if matched_phrases:
            base_conf = 0.92
            conf = min(0.99, base_conf + (len(matched_phrases) - 1) * 0.03)
            detected[barrier] = {
                "barrier": barrier,
                "confidence_score": round(conf, 2),
                "confidence": round(conf, 2),
                "method": "synonym",
                "evidence": list(dict.fromkeys(matched_phrases))[:4]
            }

    # ── Stage B: Semantic Boost Mapping (Medium-High Confidence: 0.75 – 0.85)
    if has_negation:
        for barrier, semantic_phrases in SEMANTIC_EQUIVALENTS.items():
            if barrier in detected:
                # Merge additional semantic evidence if already found
                for sem in semantic_phrases:
                    norm_sem = normalize_text(sem)
                    if norm_sem and norm_sem in norm_text and norm_sem not in detected[barrier]["evidence"]:
                        detected[barrier]["evidence"].append(norm_sem)
                continue

            matched_semantic = []
            for sem in semantic_phrases:
                norm_sem = normalize_text(sem)
                if norm_sem and norm_sem in norm_text:
                    matched_semantic.append(norm_sem)

            if matched_semantic:
                base_conf = 0.80
                conf = min(0.88, base_conf + (len(matched_semantic) - 1) * 0.04)
                detected[barrier] = {
                    "barrier": barrier,
                    "confidence_score": round(conf, 2),
                    "confidence": round(conf, 2),
                    "method": "semantic",
                    "evidence": matched_semantic[:3]
                }

    # ── Stage C: Keyword Co-occurrence (Medium Confidence: 0.55 – 0.65)
    for barrier, keywords in BARRIER_KEYWORDS.items():
        if barrier in detected:
            continue

        matched_tokens = [kw for kw in keywords if kw in tokens or any(kw in tok for tok in tokens)]
        if len(matched_tokens) >= 2 and has_negation:
            evidence_str = " + ".join(matched_tokens[:3])
            detected[barrier] = {
                "barrier": barrier,
                "confidence_score": 0.60,
                "confidence": 0.60,
                "method": "keyword",
                "evidence": [f"Keywords: {evidence_str}"]
            }

    # ── Stage D: Weak / Ambiguous Context Signals (LOW Confidence: 0.45 – 0.55)
    for barrier, weak_patterns in WEAK_CONTEXT_PATTERNS.items():
        if barrier in detected:
            continue
        for pat in weak_patterns:
            m = pat.search(norm_text)
            if m:
                detected[barrier] = {
                    "barrier": barrier,
                    "confidence_score": 0.50,
                    "confidence": 0.50,
                    "method": "weak_signal",
                    "evidence": [m.group(0)]
                }
                break

    # ── Stage E: Positive Confirmation Guard (Case 3 Noise Handling)
    # E.g., "worker mentioned gas but testing was completed" -> suppress Gas Testing failure
    filtered_detected: Dict[str, Dict[str, Any]] = {}
    for barrier, item in detected.items():
        is_positive = False
        if barrier in POSITIVE_COMPLETION_PATTERNS:
            for pos_pat in POSITIVE_COMPLETION_PATTERNS[barrier]:
                if pos_pat.search(norm_text):
                    # Check if there is also an explicit negative phrase for this barrier
                    has_explicit_neg_phrase = False
                    if barrier in BARRIER_REGEX_PATTERNS:
                        for neg_pat in BARRIER_REGEX_PATTERNS[barrier]:
                            if neg_pat.search(norm_text):
                                has_explicit_neg_phrase = True
                                break
                    if not has_explicit_neg_phrase:
                        is_positive = True
                        break

        if not is_positive:
            filtered_detected[barrier] = item

    # ── Stage F: Context Filtering (Non-Industrial False Positive Guard)
    context_validated: List[Dict[str, Any]] = []
    for barrier, item in filtered_detected.items():
        conf = item["confidence_score"]
        if is_pure_non_industrial and barrier in INDUSTRIAL_ONLY_BARRIERS:
            continue
        if has_non_industrial and not has_industrial_marker:
            conf = max(0.0, conf - 0.40)

        if conf >= 0.45:
            item["confidence_score"] = round(min(1.0, conf), 2)
            item["confidence"] = item["confidence_score"]
            context_validated.append(item)

    # ── Stage G: Multi-Barrier Interaction Boost
    # If >= 2 HIGH confidence barriers are detected, boost confidence by +0.05
    high_conf_count = sum(1 for b in context_validated if b["confidence_score"] >= 0.85)
    if high_conf_count >= 2:
        for b in context_validated:
            b["confidence_score"] = min(1.0, round(b["confidence_score"] + 0.05, 2))
            b["confidence"] = b["confidence_score"]

    # ── Stage H: Confidence Calibration & Detection Reason Generation
    for b in context_validated:
        b["confidence_level"] = calibrate_confidence(b["confidence_score"])
        b["detection_reason"] = generate_detection_reason(b["barrier"], b["method"], b["evidence"])

    # ── Stage I: Ranking & Top-K Truncation
    context_validated.sort(key=lambda x: (-float(x["confidence_score"]), str(x["barrier"])))
    TOP_K = 3
    result = context_validated[:TOP_K]
    logger.info(f"[BARRIER_DETECTED] count={len(result)} barriers={[b['barrier'] for b in result]}")
    return result


def detect_barriers(text: str) -> List[str]:
    """Return list of detected barrier failure names ranked by confidence."""
    evidence = detect_barriers_with_evidence(text)
    return [item["barrier"] for item in evidence]


def detect_barrier(text: str) -> str:
    """Return primary detected barrier or fallback."""
    barriers = detect_barriers(text)
    return barriers[0] if barriers else "Unknown Barrier Failure"
