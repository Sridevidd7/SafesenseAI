"""
SafeSense AI — Safety Concept Extraction Layer
================================================
Deterministic, semantic concept extractor mapping diverse linguistic variants
into canonical safety concepts:
1. Hazard Domains & Spatial Entities (e.g. confined_space, working_at_height, energy_isolation, line_of_fire, hot_work, chemical_handling, vehicle_movement)
2. Exposure & Action Events (e.g. entry_exposure, height_exposure, live_energy_exposure, under_load_exposure)
3. Safety Barrier Verifications & Omissions (e.g. gas_testing_missing, permit_missing, lockout_tagout_missing, fall_protection_missing, standby_missing, isolation_missing)
4. Contextual Negation & Temporal State (active_violation, preventive_before_exposure, post_exposure_intervention)
5. Pattern Composition (Preposition + Action + Prerequisite, Verb-Object Inversions, Passive/Nominalized constructions)
"""
from typing import Dict, List, Set, Any, Optional, Tuple
import re
import logging

logger = logging.getLogger("safesense.concept_extractor")

# ─── 1. REUSABLE CONCEPT DICTIONARIES ─────────────────────────────────────────

CONFINED_SPACE_ENTITIES: Set[str] = {
    "vessel", "tank", "chamber", "pit", "sump", "manhole", "column", "reactor",
    "pipe", "pipeline", "duct", "silo", "vault", "sewer", "compartment",
    "enclosed space", "confined space", "drum", "boiler", "tanker", "tunnel"
}

HEIGHT_ENTITIES: Set[str] = {
    "scaffold", "scaffolding", "ladder", "tower", "roof", "platform",
    "elevated platform", "manlift", "cherry picker", "mast", "beam",
    "edge", "walkway at height", "structure", "overhead", "staging"
}

ENERGY_ENTITIES: Set[str] = {
    "electrical panel", "breaker", "breaker panel", "circuit", "switchgear",
    "busbar", "transformer", "motor", "pump", "live wire", "live circuit",
    "high voltage", "energized line", "stored energy", "distribution board",
    "mcc", "substation", "generator", "energized system", "live conductor"
}

LINE_OF_FIRE_ENTITIES: Set[str] = {
    "suspended load", "crane", "hoist", "rigging", "sling", "drop zone",
    "overhead load", "falling object", "lift", "crane lift", "winch"
}

HOT_WORK_ENTITIES: Set[str] = {
    "welding", "torch cutting", "open flame", "grinding sparks", "brazing",
    "plasma cutting", "hot work", "torch", "arc", "grinder"
}

CHEMICAL_ENTITIES: Set[str] = {
    "acid", "caustic", "toxic", "corrosive", "chemical", "chlorine",
    "ammonia", "solvent", "h2s", "hazardous chemical", "toxic gas",
    "chemical splash", "fumes"
}

VEHICLE_ENTITIES: Set[str] = {
    "forklift", "hgv", "truck", "vehicle", "excavator", "loader",
    "traffic", "trailer", "reach truck", "telehandler"
}

# Exposure patterns
ENTRY_EXPOSURE_PATTERNS = [
    re.compile(r"\b(?:entered|was\s+entering|had\s+entered|proceeded\s+to\s+enter|stepping\s+into|stepped\s+into|went\s+into|gone\s+into|crawled\s+into|climbed\s+into)(?:\s+(?:the\s+)?(?:confined\s+space|vessel|tank|reactor|column|sump|pit|chamber|pipe|drum))?\b", re.IGNORECASE),
    re.compile(r"\b(?:went\s+inside|stepped\s+inside|stepping\s+inside|gone\s+inside|accessed\s+the\s+inside|inside\s+the)(?:\s+(?:the\s+)?(?:confined\s+space|vessel|tank|reactor|column|sump|pit|chamber|pipe|drum))?\b", re.IGNORECASE),
    re.compile(r"\b(?:accessing|accessed|penetrated|entered\s+the|entry\s+into)(?:\s+(?:the\s+)?(?:confined\s+space|vessel|tank|reactor|column|sump|pit|chamber|pipe|drum))?\b", re.IGNORECASE),
    re.compile(r"\b(?:opened|opening|accessing|accessed|working\s+on)\s+(?:the\s+)?(?:confined\s+space|vessel|tank|reactor|column|sump|pit|chamber|pipe|drum)\b", re.IGNORECASE),
    re.compile(r"\b(?:entry\s+occurred|entry\s+was\s+made|unauthorized\s+entry|confined[\s-]space\s+entry|vessel\s+entry|tank\s+entry|manhole\s+entry|chamber\s+entry)\b", re.IGNORECASE),
    re.compile(r"\b(?:worker|technician|operator|crew|personnel|contractor)\s+(?:inside|in\s+the)\b", re.IGNORECASE),
]

HEIGHT_EXPOSURE_PATTERNS = [
    re.compile(r"\b(?:climbed|climbing|mounted|mounting|ascended|ascending)\b", re.IGNORECASE),
    re.compile(r"\b(?:working\s+at\s+height|working\s+on\s+(?:scaffold|scaffolding|ladder|roof|platform|tower))\b", re.IGNORECASE),
    re.compile(r"\b(?:at\s+height|above\s+ground|elevated\s+work)\b", re.IGNORECASE),
]

ENERGY_EXPOSURE_PATTERNS = [
    re.compile(r"\b(?:working\s+on|worked\s+on|servicing|serviced|repaired|repairing|troubleshooting|operating\s+on|operated\s+on|opened|opening)\s+(?:a\s+|the\s+)?(?:live\s+|energized\s+|electrical\s+)?(?:circuit|panel|breaker|switchgear|motor|pump|board|transformer|switch|equipment)\b", re.IGNORECASE),
    re.compile(r"\b(?:operated|working\s+with|worked\s+with)\s+(?:live\s+circuit|energized\s+system|energized\s+equipment)\b", re.IGNORECASE),
    re.compile(r"\b(?:touched|touching|handling)\s+(?:busbar|live\s+conductor|live\s+wire)\b", re.IGNORECASE),
    re.compile(r"\b(?:maintenance|servicing|work|repair)\s+(?:began|started|conducted|performed)?\s*while\s+.*?\s+(?:live|energized)\b", re.IGNORECASE),
]

LINE_OF_FIRE_EXPOSURE_PATTERNS = [
    re.compile(r"\b(?:walked|walking|standing|stood|positioned|stationed|moved)\s+(?:under|below|beneath)\s+(?:a\s+)?(?:suspended\s+load|load|crane|crane\s+load|lift|overhead\s+load|pipe)\b", re.IGNORECASE),
    re.compile(r"\b(?:under|below|beneath)\s+(?:a\s+)?(?:suspended\s+load|overhead\s+load)\b", re.IGNORECASE),
    re.compile(r"\b(?:entered|inside|crossed\s+into)\s+(?:the\s+)?(?:drop\s+zone|line\s+of\s+fire|lift\s+radius)\b", re.IGNORECASE),
    re.compile(r"\b(?:in\s+the\s+path\s+of|path\s+of)\s+(?:moving\s+)?(?:equipment|machinery|vehicle)\b", re.IGNORECASE),
]

# Modifiers
OMISSION_PREPOSITIONS = [
    "without", "with no", "no", "not", "missing", "lack of", "lacked",
    "absence of", "skipped", "omitted", "neglected", "failed to",
    "forgot to", "unperformed", "untested", "unverified", "unauthorized",
    "without any", "did not conduct", "did not perform", "did not do",
    "did not obtain", "did not apply", "did not isolate", "did not check",
    "did not wear", "did not tie", "did not assign", "without being"
]

PRE_CONTROL_CONNECTIVES = [
    "before", "prior to", "ahead of", "in advance of", "previous to"
]

BARRIER_REQUIREMENTS: Dict[str, Dict[str, Any]] = {
    "Gas Testing Not Completed": {
        "concept": "gas_testing_missing",
        "verbs": [
            "test", "testing", "tested", "check", "checking", "checked",
            "monitor", "monitoring", "monitored", "sample", "sampling", "sampled",
            "measure", "measuring", "measured", "verify", "verifying", "verified",
            "detect", "detecting", "detection", "analyze", "analyzing", "analyzed"
        ],
        "targets": [
            "gas", "gases", "atmosphere", "atmospheric", "air", "air quality",
            "oxygen", "oxygen levels", "oxygen level", "gas levels", "gas level",
            "h2s", "toxic gas", "flammable gas", "combustible gas", "air sample",
            "air sampling", "gas check", "gas testing", "atmospheric test",
            "atmospheric testing", "atmospheric monitoring", "gas monitoring"
        ],
        "compounds": [
            "gas test", "gas testing", "atmospheric test", "atmospheric testing",
            "atmospheric monitoring", "gas monitoring", "air monitoring",
            "oxygen test", "oxygen testing", "gas check", "gas checking",
            "air test", "air testing", "gas detection", "gas measurement",
            "atmospheric check", "oxygen sampling", "air quality check"
        ],
        "default_lsr": "Confined Space",
        "detection_reason": "Matched safety concept signal '{phrase}' indicating missing atmospheric testing or unverified gas levels."
    },
    "Permit Not Obtained": {
        "concept": "permit_missing",
        "verbs": [
            "obtain", "obtaining", "obtained", "issue", "issuing", "issued",
            "sign", "signing", "signed", "authorize", "authorizing", "authorized",
            "approve", "approving", "approved", "grant", "granting", "granted",
            "get", "getting", "got", "acquire", "acquiring", "acquired"
        ],
        "targets": [
            "permit", "work permit", "safe work permit", "ptw", "entry permit",
            "clearance", "entry clearance", "authorization", "approval",
            "work clearance", "formal permit", "work authorization",
            "clearance or permit", "permit to work"
        ],
        "compounds": [
            "work permit", "permit to work", "safe work permit", "entry clearance",
            "entry permit", "ptw issuance", "permit authorization", "clearance sign off",
            "permit issuance", "permit issue", "issuance of permit", "permit approval"
        ],
        "default_lsr": "Confined Space",
        "detection_reason": "Matched safety concept signal '{phrase}' indicating missing work authorization, clearance, or valid PTW."
    },
    "Fall Protection Not Used": {
        "concept": "fall_protection_missing",
        "verbs": [
            "wear", "wearing", "worn", "use", "using", "used", "put on",
            "tie off", "tying off", "tied off", "hook up", "hooking up", "hooked up",
            "attach", "attaching", "attached", "secure", "securing", "secured",
            "clip", "clipping", "clipped", "anchor", "anchoring", "anchored"
        ],
        "targets": [
            "harness", "safety harness", "lanyard", "lifeline", "safety line",
            "fall protection", "fall arrest", "fall restraint", "guardrail",
            "edge protection", "anchor point", "anchorage", "safety belt",
            "tied off", "tie off", "being tied off"
        ],
        "compounds": [
            "safety harness", "fall protection", "fall arrest", "fall restraint",
            "edge protection", "anchor point", "safety line", "guardrail",
            "tied off", "tie off", "being tied off"
        ],
        "default_lsr": "Working at Height",
        "detection_reason": "Matched safety concept signal '{phrase}' indicating missing safety harness, tie-off, or edge protection at height."
    },
    "Lockout/Tagout Not Completed": {
        "concept": "lockout_tagout_missing",
        "verbs": [
            "apply", "applying", "applied", "complete", "completing", "completed",
            "install", "installing", "installed", "lock", "locking", "locked",
            "lock out", "locking out", "locked out", "tag", "tagging", "tagged",
            "tag out", "tagging out", "tagged out", "affix", "affixing", "affixed"
        ],
        "targets": [
            "lockout", "tagout", "loto", "padlock", "breaker lock", "hasp",
            "lockout tagout", "loto padlock", "isolation lock", "safety tag",
            "breaker", "the breaker", "breaker panel", "power switch", "switch",
            "panel", "motor", "pump", "circuit"
        ],
        "compounds": [
            "lockout tagout", "loto application", "breaker lockout", "padlock application",
            "circuit isolation tag", "hasp locking"
        ],
        "default_lsr": "Energy Isolation",
        "detection_reason": "Matched safety concept signal '{phrase}' indicating lack of applied lockout/tagout padlocks or isolation tags."
    },
    "Isolation Not Applied": {
        "concept": "isolation_missing",
        "verbs": [
            "isolate", "isolating", "isolated", "de energize", "de energizing", "de energized",
            "de-energize", "de-energizing", "de-energized", "deenergize", "deenergizing", "deenergized",
            "disconnect", "disconnecting", "disconnected", "switch off", "switching off", "switched off",
            "shut down", "shutting down", "shut off"
        ],
        "targets": [
            "isolation", "energy isolation", "power", "electrical supply",
            "circuit", "power source", "electrical isolation", "line isolation",
            "feed", "breaker", "switchgear", "motor", "pump", "system",
            "circuit remained live", "remained live", "energized equipment", "live circuit"
        ],
        "compounds": [
            "energy isolation", "de energization", "power cutoff", "electrical disconnection",
            "system isolation", "circuit de energize", "breaker isolation", "electrical isolation",
            "circuit remained live", "remained live", "energized equipment", "live circuit"
        ],
        "default_lsr": "Energy Isolation",
        "detection_reason": "Matched safety concept signal '{phrase}' indicating electrical or energy source was not de-energized/isolated."
    },
    "Standby Person Not Assigned": {
        "concept": "standby_missing",
        "verbs": [
            "assign", "assigning", "assigned", "post", "posting", "posted",
            "station", "stationing", "stationed", "provide", "providing", "provided",
            "deploy", "deploying", "deployed", "position", "positioning", "positioned"
        ],
        "targets": [
            "standby", "standby person", "hole watch", "safety watcher",
            "attendant", "safety attendant", "entry watcher", "sentry",
            "observer", "standby monitor"
        ],
        "compounds": [
            "standby person", "hole watch", "safety attendant", "safety watcher",
            "entry watcher", "standby observer"
        ],
        "default_lsr": "Confined Space",
        "detection_reason": "Matched safety concept signal '{phrase}' indicating absence of required safety standby watcher/attendant."
    },
    "Exclusion Zone Not Established": {
        "concept": "exclusion_zone_missing",
        "verbs": [
            "establish", "establishing", "established", "set up", "setting up",
            "erect", "erecting", "erected", "cordon", "cordoning", "cordoned",
            "barricade", "barricading", "barricaded", "demarcate", "demarcating", "demarcated"
        ],
        "targets": [
            "exclusion zone", "barricade", "perimeter", "drop zone",
            "safety perimeter", "warning tape", "cordon", "red zone", "area",
            "beneath suspended load", "under suspended load", "positioned beneath suspended load",
            "entered the drop zone", "path of moving equipment"
        ],
        "compounds": [
            "exclusion zone", "perimeter barricade", "drop zone clearance",
            "red zone demarcation", "lift exclusion", "safety perimeter",
            "area was barricaded", "barricaded", "barricade",
            "beneath suspended load", "under suspended load", "positioned beneath suspended load",
            "entered the drop zone", "path of moving equipment"
        ],
        "default_lsr": "Line of Fire",
        "detection_reason": "Matched safety concept signal '{phrase}' indicating missing barricade/perimeter or personnel below suspended load."
    },
    "Fire Watch Not Posted": {
        "concept": "fire_watch_missing",
        "verbs": [
            "post", "posting", "posted", "assign", "assigning", "assigned",
            "station", "stationing", "stationed", "deploy", "deploying", "deployed"
        ],
        "targets": [
            "fire watch", "fire guard", "spark watch", "extinguisher standby",
            "hot work watch"
        ],
        "compounds": [
            "fire watch", "fire guard", "spark watch", "hot work watch"
        ],
        "default_lsr": "Hot Work",
        "detection_reason": "Matched safety concept signal '{phrase}' indicating hot work performed without assigned fire guard/watch."
    },
    "PPE Not Available": {
        "concept": "ppe_missing",
        "verbs": [
            "wear", "wearing", "worn", "use", "using", "used", "put on",
            "provide", "providing", "provided", "don", "donning", "donned"
        ],
        "targets": [
            "ppe", "personal protective equipment", "safety glasses", "eye protection",
            "face shield", "gloves", "safety gloves", "helmet", "hard hat",
            "respirator", "mask", "hearing protection", "earplugs", "safety shoes"
        ],
        "compounds": [
            "personal protective equipment", "safety glasses", "eye protection",
            "face shield", "hard hat", "respirator unit"
        ],
        "default_lsr": "General Safety",
        "detection_reason": "Matched safety concept signal '{phrase}' indicating missing or unworn mandatory personal protective equipment."
    },
    "Pressure Not Released": {
        "concept": "pressure_not_released",
        "verbs": [
            "release", "releasing", "released", "depressurize", "depressurizing", "depressurized",
            "bleed", "bleeding", "bled", "vent", "venting", "vented", "drain", "draining", "drained"
        ],
        "targets": [
            "pressure", "residual pressure", "line pressure", "system pressure",
            "hydraulic pressure", "pneumatic pressure", "steam pressure"
        ],
        "compounds": [
            "pressure release", "line venting", "bleed off", "residual pressure",
            "line depressurization"
        ],
        "default_lsr": "Energy Isolation",
        "detection_reason": "Matched safety concept signal '{phrase}' indicating line/vessel was not depressurized or bled before opening."
    }
}

POSITIVE_CONTROL_PATTERNS: Dict[str, Dict[str, Any]] = {
    "gas_testing_verified": {
        "concept": "gas_testing_verified",
        "rule": "Confined Space",
        "patterns": [
            re.compile(r"\b(?:gas\s+testing|gas\s+test|atmospheric\s+testing|atmospheric\s+monitoring|atmosphere)\s+(?:was|were|is)?\s*(?:completed|verified|performed|done|confirmed|tested|verified\s+safe)\b", re.I),
            re.compile(r"\b(?:completed|verified)\s+(?:gas\s+testing|atmospheric\s+monitoring|air\s+testing)\s+before\s+entry\b", re.I),
            re.compile(r"\batmosphere\s+(?:was\s+)?verified\s+safe\b", re.I),
            re.compile(r"\bgas\s+testing\s+was\s+not\s+skipped\b", re.I),
            re.compile(r"\bnot\s+skipped\s+(?:any\s+)?(?:gas\s+testing|atmospheric\s+testing)\b", re.I),
        ]
    },
    "fall_protection_verified": {
        "concept": "fall_protection_verified",
        "rule": "Working at Height",
        "patterns": [
            re.compile(r"\b(?:connected|secured|tied\s+off|attached)\s+(?:safety\s+)?(?:fall\s+protection|harness|lanyard)\b", re.I),
            re.compile(r"\b(?:fall\s+protection|harness|lanyard)\s+(?:was\s+|were\s+)?(?:already\s+secured|secured|connected|tied\s+off|inspected)\b", re.I),
            re.compile(r"\bworker\s+connected\s+fall\s+protection\s+before\s+climbing\b", re.I),
            re.compile(r"\bconnected\s+(?:the\s+)?(?:fall\s+protection|harness)\s+before\s+(?:climbing|work)\b", re.I),
        ]
    },
    "energy_isolation_verified": {
        "concept": "energy_isolation_verified",
        "rule": "Energy Isolation",
        "patterns": [
            re.compile(r"\b(?:breaker|panel|circuit|equipment)\s+(?:was\s+)?(?:locked\s+out|isolated|de-energized)\b", re.I),
            re.compile(r"\b(?:locked\s+out\s+and\s+verified\s+de-energized|verified\s+de-energized)\b", re.I),
            re.compile(r"\blockout\s+was\s+completed\s+before\s+work\b", re.I),
            re.compile(r"\blockout\s+tagout\s+(?:was\s+)?(?:verified|completed)\b", re.I),
        ]
    },
    "exclusion_zone_verified": {
        "concept": "exclusion_zone_verified",
        "rule": "Line of Fire",
        "patterns": [
            re.compile(r"\barea\s+was\s+barricaded\b", re.I),
            re.compile(r"\b(?:remained|stayed)\s+outside\s+(?:the\s+)?(?:drop\s+zone|lift\s+radius|perimeter|exclusion\s+zone)\b", re.I),
            re.compile(r"\bexclusion\s+zone\s+(?:was\s+)?(?:established|barricaded)\b", re.I),
        ]
    }
}


# ─── 2. PRE-COMPILED COMPOSITIONAL MATCHER TABLES ─────────────────────────────

def _build_precompiled_patterns():
    compiled_tables = {}
    mod_prefix = r"\b(?:" + "|".join(re.escape(m) for m in sorted(OMISSION_PREPOSITIONS, key=len, reverse=True)) + r")\s+(?:any\s+|the\s+|proper\s+|required\s+|valid\s+)?"
    vo_mod_prefix = r"\b(?:" + "|".join(re.escape(m) for m in ["without", "with no", "no", "not", "forgot to", "omitted to", "failed to", "neglected to", "did not", "didnt", "missing"]) + r")\s+(?:to\s+)?"
    conn_prefix = r"\b(?:" + "|".join(re.escape(c) for c in PRE_CONTROL_CONNECTIVES) + r")\s+(?:the\s+|an\s+|any\s+|area\s+|circuit\s+|equipment\s+|line\s+|work\s+)?(?:was\s+|were\s+|is\s+|are\s+)?"

    for barrier_name, req in BARRIER_REQUIREMENTS.items():
        compounds_sorted = sorted(list(dict.fromkeys(req["compounds"] + req["targets"])), key=len, reverse=True)
        verbs_sorted = sorted(req["verbs"], key=len, reverse=True)
        targets_sorted = sorted(req["targets"], key=len, reverse=True)

        compounds_group = "(?:" + "|".join(re.escape(c) for c in compounds_sorted) + ")"
        verbs_group = "(?:" + "|".join(re.escape(v) for v in verbs_sorted) + ")"
        targets_group = "(?:" + "|".join(re.escape(t) for t in targets_sorted) + ")"

        # 1. Compound Omission: e.g. "without gas testing", "missing permit"
        p_compound = re.compile(mod_prefix + compounds_group + r"\b", re.IGNORECASE)

        # 2. Verb-Object Inversion: e.g. "without checking the atmosphere", "failed to obtain permit"
        p_vo = re.compile(vo_mod_prefix + verbs_group + r"\s+(?:the\s+|any\s+|all\s+|required\s+|proper\s+)?" + targets_group + r"\b", re.IGNORECASE)

        # 3. Connective Compounds: e.g. "before atmospheric testing", "prior to permit issuance", "before electrical isolation"
        p_conn_comp = re.compile(conn_prefix + r"(?:any\s+|the\s+|conducting\s+|performing\s+|doing\s+|completing\s+|verifying\s+)?" + compounds_group + r"\b", re.IGNORECASE)

        # 4. Connective Verb-Object: e.g. "before securing lanyard", "prior to isolating power"
        p_conn_vo = re.compile(conn_prefix + verbs_group + r"\s+(?:the\s+|any\s+|required\s+)?" + targets_group + r"\b", re.IGNORECASE)

        # 5. Passive Negation: e.g. "atmosphere was not checked", "loto was not completed"
        p_passive = re.compile(targets_group + r"\s+(?:was|were|is|are)?\s*(?:not|never|omitted|skipped|forgotten|neglected)\s*(?:done|completed|conducted|performed|" + verbs_group + r")\b", re.IGNORECASE)

        compiled_tables[barrier_name] = {
            "compound": p_compound,
            "vo": p_vo,
            "conn_comp": p_conn_comp,
            "conn_vo": p_conn_vo,
            "passive": p_passive,
            "req": req
        }
    return compiled_tables

PRECOMPILED_BARRIER_MATCHERS = _build_precompiled_patterns()


# ─── 3. TEXT NORMALIZATION ───────────────────────────────────────────────────

def normalize_safety_text(text: str) -> str:
    """
    Expands hyphenated safety compounds and normalizes spacing.
    """
    if not text:
        return ""
    lowered = text.lower().strip()

    replacements = {
        r"\bconfined[\s-]space\b": "confined space",
        r"\block[\s-]out[\s-]tag[\s-]out\b": "lockout tagout",
        r"\block[\s-]out\b": "lockout",
        r"\btag[\s-]out\b": "tagout",
        r"\bstop[\s-]work\b": "stop work",
        r"\bde[\s-]energiz": "de energiz",
        r"\btie[\s-]off\b": "tie off",
        r"\btied[\s-]off\b": "tied off",
        r"\bdrop[\s-]zone\b": "drop zone",
        r"\bair[\s-]monitoring\b": "air monitoring",
        r"\bgas[\s-]testing\b": "gas testing",
        r"\bgas[\s-]test\b": "gas test",
        r"\bfire[\s-]watch\b": "fire watch",
        r"\bhole[\s-]watch\b": "hole watch",
    }
    for pat, rep in replacements.items():
        lowered = re.sub(pat, rep, lowered)

    # Collapse whitespace
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


# ─── 4. CORE CONCEPT EXTRACTION ──────────────────────────────────────────────

def extract_safety_concepts(text: str) -> Dict[str, Any]:
    """
    Extracts structured, explainable safety concepts from natural language text.
    Fast execution via precompiled compositional matchers.
    """
    if not text or not text.strip():
        return {
            "concepts": [],
            "hazard_domains": [],
            "primary_domain": "General Safety",
            "exposure_detected": False,
            "exposure_type": None,
            "exposure_evidence": [],
            "barrier_omissions": [],
            "evidence_phrases": [],
        }

    norm_text = normalize_safety_text(text)
    concepts: Set[str] = set()
    hazard_domains: Set[str] = set()
    evidence_phrases: List[str] = []
    barrier_omissions: List[Dict[str, Any]] = []

    # 1. HAZARD DOMAIN ENTITY DETECTION
    has_cs_entity = any(re.search(r"\b" + re.escape(e) + r"\b", norm_text) for e in CONFINED_SPACE_ENTITIES)
    has_height_entity = any(re.search(r"\b" + re.escape(e) + r"\b", norm_text) for e in HEIGHT_ENTITIES)
    has_energy_entity = any(re.search(r"\b" + re.escape(e) + r"\b", norm_text) for e in ENERGY_ENTITIES)
    has_lof_entity = any(re.search(r"\b" + re.escape(e) + r"\b", norm_text) for e in LINE_OF_FIRE_ENTITIES)
    has_hotwork_entity = any(re.search(r"\b" + re.escape(e) + r"\b", norm_text) for e in HOT_WORK_ENTITIES)
    has_chem_entity = any(re.search(r"\b" + re.escape(e) + r"\b", norm_text) for e in CHEMICAL_ENTITIES)
    has_veh_entity = any(re.search(r"\b" + re.escape(e) + r"\b", norm_text) for e in VEHICLE_ENTITIES)

    # 2. EXPOSURE / ACTION EVENT DETECTION
    entry_exposure_matches = []
    for pat in ENTRY_EXPOSURE_PATTERNS:
        m = pat.search(norm_text)
        if m:
            entry_exposure_matches.append(m.group(0))

    height_exposure_matches = []
    for pat in HEIGHT_EXPOSURE_PATTERNS:
        m = pat.search(norm_text)
        if m:
            height_exposure_matches.append(m.group(0))

    energy_exposure_matches = []
    for pat in ENERGY_EXPOSURE_PATTERNS:
        m = pat.search(norm_text)
        if m:
            energy_exposure_matches.append(m.group(0))

    lof_exposure_matches = []
    for pat in LINE_OF_FIRE_EXPOSURE_PATTERNS:
        m = pat.search(norm_text)
        if m:
            lof_exposure_matches.append(m.group(0))

    exposure_detected = False
    exposure_type = None
    exposure_evidence: List[str] = []

    if entry_exposure_matches:
        exposure_detected = True
        exposure_type = "ENTRY_EXPOSURE"
        exposure_evidence.extend(entry_exposure_matches)
        concepts.add("entry_exposure")
        # If entry occurred and gas testing is mentioned or space is confined
        if has_cs_entity or "inside" in norm_text or "gas" in norm_text or "atmosphere" in norm_text or "air" in norm_text:
            concepts.add("confined_space")
            hazard_domains.add("Confined Space")

    if height_exposure_matches or (has_height_entity and any(w in norm_text for w in ["climbed", "working", "on", "above"])):
        exposure_detected = True
        exposure_type = exposure_type or "HEIGHT_EXPOSURE"
        exposure_evidence.extend(height_exposure_matches)
        concepts.add("height_exposure")
        concepts.add("working_at_height")
        hazard_domains.add("Working at Height")

    if energy_exposure_matches or (has_energy_entity and any(w in norm_text for w in ["servicing", "repair", "operating", "working", "live"])):
        exposure_detected = True
        exposure_type = exposure_type or "ENERGY_EXPOSURE"
        exposure_evidence.extend(energy_exposure_matches)
        concepts.add("energy_exposure")
        concepts.add("energy_isolation")
        hazard_domains.add("Energy Isolation")

    if lof_exposure_matches:
        exposure_detected = True
        exposure_type = exposure_type or "LINE_OF_FIRE_EXPOSURE"
        exposure_evidence.extend(lof_exposure_matches)
        concepts.add("line_of_fire_exposure")
        concepts.add("line_of_fire")
        hazard_domains.add("Line of Fire")

    if has_cs_entity:
        concepts.add("confined_space")
        hazard_domains.add("Confined Space")
    if has_hotwork_entity:
        concepts.add("hot_work")
        hazard_domains.add("Hot Work")
    if has_chem_entity:
        concepts.add("chemical_handling")
        hazard_domains.add("Chemical Handling")
    if has_veh_entity:
        concepts.add("vehicle_movement")
        hazard_domains.add("Vehicle Movement")

    # 3. PRECOMPILED BARRIER OMISSION MATCHING
    for barrier_name, item in PRECOMPILED_BARRIER_MATCHERS.items():
        req = item["req"]
        omission_evidence: List[str] = []
        conf_score = 0.92

        # 1. Direct compound omission (e.g. 'without gas testing')
        m_comp = item["compound"].search(norm_text)
        if m_comp:
            omission_evidence.append(m_comp.group(0))
            conf_score = max(conf_score, 0.98)

        # 2. Verb-object inversion omission (e.g. 'without checking the atmosphere')
        if not omission_evidence:
            m_vo = item["vo"].search(norm_text)
            if m_vo:
                omission_evidence.append(m_vo.group(0))
                conf_score = max(conf_score, 0.96)

        # 3. Exposure / activity before prerequisite control (e.g. 'went inside before atmospheric testing', 'opened vessel prior to permit issuance')
        has_activity = exposure_detected or bool(re.search(r"\b(?:opened|opening|started|starting|began|beginning|commenced|commencing|proceeded|proceeding|worked|working|serviced|servicing|repaired|repairing|maintenance|operation|climb|climbed|access|accessed)\b", norm_text))
        if not omission_evidence and has_activity:
            m_conn_comp = item["conn_comp"].search(norm_text)
            if m_conn_comp:
                omission_evidence.append(m_conn_comp.group(0))
                conf_score = max(conf_score, 0.95)

            if not omission_evidence:
                m_conn_vo = item["conn_vo"].search(norm_text)
                if m_conn_vo:
                    omission_evidence.append(m_conn_vo.group(0))
                    conf_score = max(conf_score, 0.94)

        # 4. Passive target omission (e.g. 'atmosphere was not checked')
        if not omission_evidence:
            m_pass = item["passive"].search(norm_text)
            if m_pass:
                omission_evidence.append(m_pass.group(0))
                conf_score = max(conf_score, 0.95)

        if omission_evidence:
            concepts.add(req["concept"])
            default_lsr = req.get("default_lsr")
            if default_lsr:
                hazard_domains.add(default_lsr)
            clean_ev = list(dict.fromkeys(omission_evidence))
            evidence_phrases.extend(clean_ev)
            barrier_omissions.append({
                "barrier": barrier_name,
                "concept": req["concept"],
                "method": "concept",
                "confidence_score": round(conf_score, 2),
                "confidence": round(conf_score, 2),
                "confidence_level": "HIGH",
                "evidence": clean_ev,
                "detection_reason": req["detection_reason"].format(phrase=clean_ev[0])
            })

    # 4. POSITIVE CONTROL DETECTION
    positive_controls = []
    for ctrl_key, ctrl_info in POSITIVE_CONTROL_PATTERNS.items():
        for pat in ctrl_info["patterns"]:
            m = pat.search(norm_text)
            if m:
                matched_phrase = m.group(0)
                concepts.add(ctrl_info["concept"])
                hazard_domains.add(ctrl_info["rule"])
                evidence_phrases.append(matched_phrase)
                positive_controls.append({
                    "concept": ctrl_info["concept"],
                    "source_phrase": matched_phrase,
                    "evidence_type": "POSITIVE_CONTROL",
                    "state": "POSITIVE_CONTROL",
                    "related_barrier": None,
                    "related_rule": ctrl_info["rule"]
                })
                break

    evidence_phrases = list(dict.fromkeys(evidence_phrases + exposure_evidence))

    primary_domain = "General Safety"
    if "Confined Space" in hazard_domains:
        primary_domain = "Confined Space"
    elif "Working at Height" in hazard_domains:
        primary_domain = "Working at Height"
    elif "Energy Isolation" in hazard_domains:
        primary_domain = "Energy Isolation"
    elif "Hot Work" in hazard_domains:
        primary_domain = "Hot Work"
    elif "Line of Fire" in hazard_domains:
        primary_domain = "Line of Fire"
    elif "Chemical Handling" in hazard_domains:
        primary_domain = "Chemical Handling"
    elif "Vehicle Movement" in hazard_domains:
        primary_domain = "Vehicle Movement"
    elif hazard_domains:
        primary_domain = sorted(list(hazard_domains))[0]

    return {
        "concepts": sorted(list(concepts)),
        "hazard_domains": sorted(list(hazard_domains)),
        "primary_domain": primary_domain,
        "exposure_detected": exposure_detected,
        "exposure_type": exposure_type,
        "exposure_evidence": exposure_evidence,
        "barrier_omissions": barrier_omissions,
        "positive_controls": positive_controls,
        "evidence_phrases": evidence_phrases,
    }


def get_compositional_barrier_evidence(text: str) -> List[Dict[str, Any]]:
    """
    Returns detected barrier evidence items from the concept extraction layer
    ready for consumption by the barrier detection pipeline.
    """
    concepts_data = extract_safety_concepts(text)
    return concepts_data["barrier_omissions"]


def build_structured_evidence(
    text: str,
    negation_type: str = "NONE",
    detected_barriers: Optional[List[str]] = None,
    lsr: str = "General Safety"
) -> List[Dict[str, Any]]:
    """
    Constructs an explicit, deterministic evidence model:
    Each item tracks:
      - concept (canonical concept string)
      - source_phrase (exact phrase from report)
      - evidence_type (ENTRY_EXPOSURE, HEIGHT_EXPOSURE, ENERGY_EXPOSURE,
                      LINE_OF_FIRE_EXPOSURE, BARRIER_OMISSION, POSITIVE_CONTROL, SPATIAL_ENTITY)
      - state (ACTIVE_VIOLATION, PREVENTED, POSITIVE_CONTROL, CONTEXT_ONLY)
      - related_barrier (e.g. 'Gas Testing Not Completed' or None)
      - related_rule (canonical Life-Saving Rule)
    """
    if not text or not text.strip():
        return []

    concepts_data = extract_safety_concepts(text)
    items: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str, str]] = set()

    is_preventive = negation_type in ("SAFE_PREVENTIVE", "PREVENTIVE_BEFORE_EXPOSURE") or (
        detected_barriers and any(b.startswith("Prevented:") for b in detected_barriers)
    )

    rule_context = lsr if lsr != "General Safety" else concepts_data.get("primary_domain", "General Safety")

    # 1. Exposure Evidence
    if concepts_data["exposure_detected"] and concepts_data["exposure_evidence"]:
        exp_phrase = concepts_data["exposure_evidence"][0]
        exp_type = concepts_data.get("exposure_type") or "ENTRY_EXPOSURE"
        state = "PREVENTED" if is_preventive else "ACTIVE_VIOLATION"

        c_name = "entry_exposure"
        if exp_type == "HEIGHT_EXPOSURE":
            c_name = "height_exposure"
        elif exp_type == "ENERGY_EXPOSURE":
            c_name = "energy_exposure"
        elif exp_type == "LINE_OF_FIRE_EXPOSURE":
            c_name = "line_of_fire_exposure"

        key = (c_name, exp_phrase, state)
        if key not in seen:
            seen.add(key)
            items.append({
                "concept": c_name,
                "source_phrase": exp_phrase,
                "evidence_type": exp_type,
                "state": state,
                "related_barrier": None,
                "related_rule": rule_context
            })

    # 2. Barrier Omission Evidence
    for b_item in concepts_data["barrier_omissions"]:
        b_name = b_item["barrier"]
        b_concept = b_item["concept"]
        b_phrase = b_item["evidence"][0] if b_item.get("evidence") else b_name
        b_rule = b_item.get("default_lsr") or rule_context
        state = "PREVENTED" if is_preventive else "ACTIVE_VIOLATION"

        key = (b_concept, b_phrase, state)
        if key not in seen:
            seen.add(key)
            items.append({
                "concept": b_concept,
                "source_phrase": b_phrase,
                "evidence_type": "BARRIER_OMISSION",
                "state": state,
                "related_barrier": b_name,
                "related_rule": b_rule
            })

    # 3. Positive Control Evidence
    for pos_item in concepts_data.get("positive_controls", []):
        key = (pos_item["concept"], pos_item["source_phrase"], "POSITIVE_CONTROL")
        if key not in seen:
            seen.add(key)
            items.append({
                "concept": pos_item["concept"],
                "source_phrase": pos_item["source_phrase"],
                "evidence_type": "POSITIVE_CONTROL",
                "state": "POSITIVE_CONTROL",
                "related_barrier": None,
                "related_rule": pos_item["related_rule"]
            })

    # 4. Context / Spatial Entities (if no active exposure and no barrier omission)
    if not concepts_data["exposure_detected"] and not concepts_data["barrier_omissions"] and not concepts_data.get("positive_controls"):
        norm = normalize_safety_text(text)
        for ent in sorted(CONFINED_SPACE_ENTITIES, key=len, reverse=True):
            if re.search(r"\b" + re.escape(ent) + r"\b", norm):
                key = ("confined_space", ent, "CONTEXT_ONLY")
                if key not in seen:
                    seen.add(key)
                    items.append({
                        "concept": "confined_space",
                        "source_phrase": ent,
                        "evidence_type": "SPATIAL_ENTITY",
                        "state": "CONTEXT_ONLY",
                        "related_barrier": None,
                        "related_rule": "Confined Space"
                    })
                break
        for ent in sorted(HEIGHT_ENTITIES, key=len, reverse=True):
            if re.search(r"\b" + re.escape(ent) + r"\b", norm):
                key = ("working_at_height", ent, "CONTEXT_ONLY")
                if key not in seen:
                    seen.add(key)
                    items.append({
                        "concept": "working_at_height",
                        "source_phrase": ent,
                        "evidence_type": "SPATIAL_ENTITY",
                        "state": "CONTEXT_ONLY",
                        "related_barrier": None,
                        "related_rule": "Working at Height"
                    })
                break
        for ent in sorted(ENERGY_ENTITIES, key=len, reverse=True):
            if re.search(r"\b" + re.escape(ent) + r"\b", norm):
                key = ("energy_isolation", ent, "CONTEXT_ONLY")
                if key not in seen:
                    seen.add(key)
                    items.append({
                        "concept": "energy_isolation",
                        "source_phrase": ent,
                        "evidence_type": "SPATIAL_ENTITY",
                        "state": "CONTEXT_ONLY",
                        "related_barrier": None,
                        "related_rule": "Energy Isolation"
                    })
                break

    return items
