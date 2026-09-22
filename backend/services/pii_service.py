"""
services/pii_service.py — Production-quality PII detection and redaction pipeline.

Preprocessing layer executed BEFORE NLP/risk analysis:
Raw Safety Report → PII Detection & Redaction → NLP / Risk Analysis → Database / Analytics

Detects and redacts:
- Worker/person names (using high-confidence contextual patterns)
- Employee IDs / badge numbers
- Phone numbers
- Email addresses
- Personal physical addresses

Replaces with standard placeholders:
[WORKER_NAME], [EMPLOYEE_ID], [PHONE], [EMAIL], [ADDRESS]

Preserves all safety operational terminology (worker roles, equipment, units, areas,
hazards, LSRs, barriers, PPE, etc.).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

# ─── Operational Safety Whitelist (MUST NEVER BE REDACTED) ────────────────────
SAFETY_WHITELIST: Set[str] = {
    # Roles
    "worker", "workers", "technician", "technicians", "operator", "operators",
    "contractor", "contractors", "supervisor", "supervisors", "engineer", "engineers",
    "electrician", "electricians", "welder", "welders", "rigger", "riggers",
    "driver", "drivers", "auditor", "auditors", "officer", "officers", "crew", "team",
    "hse", "safety manager", "site manager", "banksman", "attendant", "standby",
    # Life Saving Rules & Hazard Categories
    "confined space", "energy isolation", "hot work", "working at height",
    "line of fire", "vehicle movement", "chemical handling", "fire prevention",
    "general safety", "near miss", "unsafe act", "unsafe condition", "incident",
    # Equipment & Facilities
    "pump", "motor", "reactor", "vessel", "tank", "compressor", "pipe", "pipeline",
    "valve", "boiler", "substation", "generator", "crane", "forklift", "scaffold",
    "scaffolding", "ladder", "harness", "breaker", "switchgear", "panel",
    "electrical panel", "manifold", "flange", "turbine", "chiller", "conveyor",
    # Units, Areas & Locations
    "refinery", "unit", "area", "workshop", "fabrication", "terminal", "storage",
    "tank farm", "control room", "switchgear room", "transfer station", "bay",
    "site alpha", "site beta", "site gamma", "site delta", "manifold section",
    # Controls, PPE & Protocols
    "lockout", "tagout", "loto", "permit", "ptw", "ppe", "gas test", "atmospheric",
    "atmospheric testing", "oxygen", "h2s", "safety glasses", "gloves", "helmet",
    "respirator", "mask", "face shield", "ear protection", "fall arrest", "barrier",
    "isolation", "fire watch", "pre-entry", "inspection", "maintenance", "overhaul",
    "ventilation", "grounding", "earthing", "chock",
}

# ─── Regex Patterns ──────────────────────────────────────────────────────────

# Email: standard pattern
EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    re.IGNORECASE
)

# Phone Numbers: 10-digit mobile, international, 555-xxx demo numbers, dashed/spaced
PHONE_REGEX = re.compile(
    r"(?:"
    r"(?:\+?91[-.\s]?)?[6-9]\d{9}\b|"                      # Indian 10-digit
    r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b|"  # US/Standard 10-digit
    r"\b555[-.\s]?\d{3,4}[-.\s]?\d{4}\b|"                 # Standard fictional 555-xxxx
    r"\b555[-.\s]?\d{4}\b|"                               # Short fictional 555-0199
    r"\b\d{3}[-.]\d{3}[-.]\d{4}\b"                        # Generic 000-000-0000
    r")"
)

# Employee IDs: "Employee ID 48392", "Emp ID: DEMO-123", "Badge #9021", etc.
EMPLOYEE_ID_REGEX = re.compile(
    r"\b(?:"
    r"(?:Employee|Emp|Worker|Staff|Badge)\s*(?:ID|Number|No|#)\s*[:#\-]?\s*([A-Za-z0-9\-]{2,15})|"
    r"(?:ID\s*[:#\-]\s*([A-Za-z0-9\-]{2,15}))|"
    r"\b(?:DEMO|EMP|WRK|STF)[-_][0-9]{3,8}\b"
    r")\b",
    re.IGNORECASE
)

# Residential / Personal Addresses: e.g. "123 Baker Street", "Apt 4B, MG Road"
ADDRESS_REGEX = re.compile(
    r"\b\d{1,5}\s+[A-Za-z0-9\s.,]{3,30}\b(?:"
    r"Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|"
    r"Apartment|Apt|Suite|Ste|Floor|Fl|Cross|Layout|Nagar|Colony)\b",
    re.IGNORECASE
)

# Contextual Worker Name Patterns (High Confidence)
# 1. Preceded by role: "Worker Rahul Kumar", "Technician Alex Morgan", "Employee Jane Doe"
ROLE_PRECEDED_NAME_REGEX = re.compile(
    r"\b(Worker|Technician|Operator|Contractor|Engineer|Employee|Supervisor|Auditor|Officer|Staff|Driver|Welder|Mechanic|Electrician|Rigger|Specialist)\s+"
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b"
)

# 2. Preceded by honorific: "Mr. Rahul Kumar", "Dr. John Smith"
HONORIFIC_NAME_REGEX = re.compile(
    r"\b(Mr\.|Mrs\.|Ms\.|Dr\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b"
)

# 3. Followed by communicative/reporting action: "Rahul Kumar reported", "Jane Doe called"
ACTION_FOLLOWED_NAME_REGEX = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s+"
    r"(?:reported|called|phoned|contacted|notified|stated|witnessed|observed|informed|escalated|intervened|halted|stopped)\b"
)

# 4. Followed by parenthetical or comma-separated Employee ID: "Rahul Kumar (Employee ID 48392)"
ID_FOLLOWED_NAME_REGEX = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*"
    r"(?:\(\s*(?:Employee|Emp|Staff|Badge|Worker\s*ID|ID)|,\s*(?:Employee|Emp|Staff|Badge|Worker\s*ID|ID))\b",
    re.IGNORECASE
)

# 5. Labeled name: "Name: Rahul Kumar", "Reporter: Jane Doe"
LABELED_NAME_REGEX = re.compile(
    r"\b(?:Name|Reporter|Observer|Injured Person)\s*[:=]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b",
    re.IGNORECASE
)


@dataclass
class RedactionResult:
    """Detailed result of PII detection and redaction."""
    original_text: str
    redacted_text: str
    pii_detected: bool
    pii_count: int
    pii_types: List[str] = field(default_factory=list)
    redactions: List[Dict[str, Any]] = field(default_factory=list)


def _is_whitelisted(candidate: str) -> bool:
    """Check if candidate text or any part of it is a protected safety operational term."""
    norm = candidate.strip().lower()
    if norm in SAFETY_WHITELIST:
        return True
    tokens = norm.split()
    if all(t in SAFETY_WHITELIST for t in tokens):
        return True
    return False


def redact_pii(text: str) -> RedactionResult:
    """
    Scans text for sensitive identifiers and replaces them with standard placeholders:
    [WORKER_NAME], [EMPLOYEE_ID], [PHONE], [EMAIL], [ADDRESS].

    Guarantees:
    - Zero external network calls (purely local & deterministic)
    - High-confidence contextual worker name recognition
    - Strict safety terminology preservation
    - Returns sanitized text suitable for risk engine and database persistence
    """
    if not text or not isinstance(text, str):
        return RedactionResult(
            original_text=str(text or ""),
            redacted_text=str(text or ""),
            pii_detected=False,
            pii_count=0,
            pii_types=[],
            redactions=[],
        )

    working_text = text
    detected_types: Set[str] = set()
    redaction_log: List[Dict[str, Any]] = []

    # ── 1. Redact Emails ──────────────────────────────────────────────────────
    def email_repl(match: re.Match) -> str:
        val = match.group(0)
        detected_types.add("EMAIL")
        redaction_log.append({"type": "EMAIL", "original": val, "placeholder": "[EMAIL]"})
        return "[EMAIL]"

    working_text = EMAIL_REGEX.sub(email_repl, working_text)

    # ── 2. Redact Employee IDs ────────────────────────────────────────────────
    def employee_id_repl(match: re.Match) -> str:
        val = match.group(0)
        detected_types.add("EMPLOYEE_ID")
        redaction_log.append({"type": "EMPLOYEE_ID", "original": val, "placeholder": "[EMPLOYEE_ID]"})
        return "[EMPLOYEE_ID]"

    working_text = EMPLOYEE_ID_REGEX.sub(employee_id_repl, working_text)

    # ── 3. Redact Phone Numbers ───────────────────────────────────────────────
    def phone_repl(match: re.Match) -> str:
        val = match.group(0)
        if len(re.sub(r"\D", "", val)) < 7:
            return val
        detected_types.add("PHONE")
        redaction_log.append({"type": "PHONE", "original": val, "placeholder": "[PHONE]"})
        return "[PHONE]"

    working_text = PHONE_REGEX.sub(phone_repl, working_text)

    # ── 4. Redact Personal Addresses ──────────────────────────────────────────
    def address_repl(match: re.Match) -> str:
        val = match.group(0)
        if _is_whitelisted(val):
            return val
        detected_types.add("ADDRESS")
        redaction_log.append({"type": "ADDRESS", "original": val, "placeholder": "[ADDRESS]"})
        return "[ADDRESS]"

    working_text = ADDRESS_REGEX.sub(address_repl, working_text)

    # ── 5. Contextual Worker Name Detection & Redaction ───────────────────────
    # A. Names followed by ID: "Rahul Kumar ([EMPLOYEE_ID])" or "Rahul Kumar (Employee ID...)"
    def id_followed_repl(match: re.Match) -> str:
        name = match.group(1)
        if _is_whitelisted(name):
            return match.group(0)
        detected_types.add("WORKER_NAME")
        redaction_log.append({"type": "WORKER_NAME", "original": name, "placeholder": "[WORKER_NAME]"})
        full_match = match.group(0)
        return full_match.replace(name, "[WORKER_NAME]", 1)

    working_text = ID_FOLLOWED_NAME_REGEX.sub(id_followed_repl, working_text)

    # Also match pattern where EMPLOYEE_ID was already redacted: "<Name> ([EMPLOYEE_ID])"
    already_redacted_id_pat = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*\(\s*\[EMPLOYEE_ID\]\)")
    def already_id_repl(match: re.Match) -> str:
        name = match.group(1)
        if _is_whitelisted(name):
            return match.group(0)
        detected_types.add("WORKER_NAME")
        redaction_log.append({"type": "WORKER_NAME", "original": name, "placeholder": "[WORKER_NAME]"})
        return "[WORKER_NAME] ([EMPLOYEE_ID])"

    working_text = already_redacted_id_pat.sub(already_id_repl, working_text)

    # B. Names preceded by role: "Worker Rahul Kumar" -> "Worker [WORKER_NAME]"
    def role_preceded_repl(match: re.Match) -> str:
        role = match.group(1)
        name = match.group(2)
        if _is_whitelisted(name):
            return match.group(0)
        detected_types.add("WORKER_NAME")
        redaction_log.append({"type": "WORKER_NAME", "original": name, "placeholder": "[WORKER_NAME]"})
        return f"{role} [WORKER_NAME]"

    working_text = ROLE_PRECEDED_NAME_REGEX.sub(role_preceded_repl, working_text)

    # C. Names preceded by honorific: "Mr. Rahul Kumar" -> "[WORKER_NAME]"
    def honorific_repl(match: re.Match) -> str:
        name = match.group(2)
        if _is_whitelisted(name):
            return match.group(0)
        detected_types.add("WORKER_NAME")
        redaction_log.append({"type": "WORKER_NAME", "original": match.group(0), "placeholder": "[WORKER_NAME]"})
        return "[WORKER_NAME]"

    working_text = HONORIFIC_NAME_REGEX.sub(honorific_repl, working_text)

    # D. Names followed by communicative action: "Rahul Kumar called [PHONE]" -> "[WORKER_NAME] called [PHONE]"
    def action_followed_repl(match: re.Match) -> str:
        name = match.group(1)
        if _is_whitelisted(name) or "[WORKER_NAME]" in name:
            return match.group(0)
        detected_types.add("WORKER_NAME")
        redaction_log.append({"type": "WORKER_NAME", "original": name, "placeholder": "[WORKER_NAME]"})
        full_match = match.group(0)
        return full_match.replace(name, "[WORKER_NAME]", 1)

    working_text = ACTION_FOLLOWED_NAME_REGEX.sub(action_followed_repl, working_text)

    # E. Labeled names: "Name: Jane Doe" -> "Name: [WORKER_NAME]"
    def labeled_name_repl(match: re.Match) -> str:
        name = match.group(1)
        if _is_whitelisted(name):
            return match.group(0)
        detected_types.add("WORKER_NAME")
        redaction_log.append({"type": "WORKER_NAME", "original": name, "placeholder": "[WORKER_NAME]"})
        full_match = match.group(0)
        return full_match.replace(name, "[WORKER_NAME]", 1)

    working_text = LABELED_NAME_REGEX.sub(labeled_name_repl, working_text)

    pii_count = len(redaction_log)
    pii_detected = pii_count > 0

    return RedactionResult(
        original_text=text,
        redacted_text=working_text,
        pii_detected=pii_detected,
        pii_count=pii_count,
        pii_types=sorted(list(detected_types)),
        redactions=redaction_log,
    )
