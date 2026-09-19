"""
services/report_service.py — Business logic for safety report processing.

All database operations and rule-engine calls live here.
Route handlers are kept thin — they only call these functions.
"""
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from models import Report
from schemas import ReportCreate


# ─── Rule engine constants ────────────────────────────────────────────────────
# Each entry: (category_name, keyword_list)
# detectLSR: count keyword hits per category, highest wins.

_LSR_KEYWORDS: list[tuple[str, list[str]]] = [
    ("Confined Space", [
        "confined space", "vessel entry", "tank entry", "permit",
        "gas test", "atmospheric", "oxygen", "h2s", "drain",
        "pit", "sump", "chamber", "enclosed",
    ]),
    ("Energy Isolation", [
        "lockout", "tagout", "loto", "isolation", "energized",
        "de-energize", "live circuit", "electrical", "voltage",
        "power source", "isolation certificate", "pressure", "stored energy",
    ]),
    ("Hot Work", [
        "welding", "cutting", "grinding", "hot work", "sparks",
        "flame", "arc", "torch", "fire watch", "flammable",
        "ignition", "permit to work",
    ]),
    ("Working at Height", [
        "height", "scaffold", "ladder", "roof", "platform",
        "harness", "fall arrest", "elevated", "guardrail",
        "edge protection", "toe board", "fall protection",
    ]),
    ("Line of Fire", [
        "line of fire", "suspended load", "crane", "lift",
        "rigging", "exclusion zone", "struck by", "falling object",
        "overhead", "below load",
    ]),
    ("Vehicle Movement", [
        "vehicle", "forklift", "hgv", "truck", "reversing",
        "pedestrian", "banksman", "traffic", "collision",
        "seat belt", "speeding", "excavator", "mobile plant",
    ]),
    ("Chemical Handling", [
        "chemical", "acid", "caustic", "toxic", "corrosive",
        "spill", "ppe", "sds", "msds", "inhalation",
        "exposure", "gas leak", "chlorine", "sulfuric", "ammonia",
    ]),
    ("Fire Prevention", [
        "fire", "smoke", "detector", "suppression", "extinguisher",
        "flammable", "combustible", "ignition", "evacuation", "alarm",
    ]),
]

_BARRIER_PHRASES: list[tuple[str, list[str]]] = [
    ("Gas Testing Not Completed",   ["without gas test", "no gas test", "without atmospheric", "not tested"]),
    ("Permit Not Obtained",         ["without permit", "no permit", "permit not obtained", "no authorization"]),
    ("Isolation Not Applied",       ["without isolat", "no isolation", "not isolated", "without lockout"]),
    ("Fall Protection Not Used",    ["without harness", "no harness", "no fall arrest", "no edge protection"]),
    ("Exclusion Zone Not Set",      ["exclusion zone", "no exclusion", "zone not established", "below load"]),
    ("Fire Watch Not Posted",       ["no fire watch", "fire watch not", "without fire watch"]),
    ("PPE Not Available",           ["without ppe", "no ppe", "ppe not available", "without protection"]),
    ("Exposed Live Parts",          ["live terminal", "live conductor", "exposed conductor", "live wire"]),
    ("Seat Belt Not Worn",          ["without seat belt", "no seat belt", "not wearing seat belt"]),
]

_SIF_KEYWORDS = [
    "confined space", "without gas testing", "lockout", "without isolation",
    "energized", "live circuit", "without harness", "suspended load",
    "line of fire", "exclusion zone", "chemical exposure", "toxic gas",
    "oxygen deficient", "pressurized", "fire suppression disabled",
    "hot work", "without permit",
]


from services.risk_engine import (
    detect_lsr as engine_detect_lsr,
    detect_barrier as engine_detect_barrier,
    detect_barriers as engine_detect_barriers,
    calculate_risk_score as engine_calculate_risk_score,
    analyze_report as engine_analyze_report,
)

# ─── Functions delegating to unified risk engine ──────────────────────────────

def detect_lsr(text: str) -> str:
    """Return the Life-Saving Rule category with the most keyword hits."""
    return engine_detect_lsr(text)


def detect_barrier(text: str) -> str:
    """Return the primary barrier failure pattern that matches."""
    return engine_detect_barrier(text)


def detect_barriers(text: str) -> list[str]:
    """Return all barrier failure patterns that match."""
    return engine_detect_barriers(text)


def calculate_risk_score(
    text:        str,
    lsr:         str = "",
    barrier:     str = "",
    severity:    str = "",
    report_type: str = "",
) -> int:
    """
    Five-factor context-aware risk score, capped at 100.
    """
    result = engine_calculate_risk_score({
        "report_text": text,
        "life_saving_rule": lsr or None,
        "barrier_failure": barrier or None,
        "severity": severity or None,
        "report_type": report_type or None,
    })
    return result["risk_score"]


def is_sif(text: str, score: int) -> bool:
    """Return True when the report shows SIF potential."""
    analysis = engine_analyze_report({"report_text": text})
    return analysis["sif_potential"] == "YES"


def analyze_text(description: str) -> dict:
    """
    Run the full context-aware rule engine on raw description text.
    Returns a dict with category, barrier_failures, risk_score, confidence, sif_potential, risk_level, negation_type, explanation.
    """
    analysis = engine_analyze_report({"report_text": description})
    return {
        "category":         analysis["life_saving_rule"],
        "barrier":          analysis["barrier_failure"],
        "barrier_failures": analysis["barrier_failures"],
        "confidence":       analysis["confidence"],
        "confidence_level": analysis["confidence_level"],
        "risk_score":       analysis["risk_score"],
        "risk_level":       analysis["risk_level"],
        "sif_potential":    analysis["sif_potential"],
        "negation_type":    analysis["negation_type"],
        "explanation":      analysis["explanation"],
    }


import hashlib

def compute_report_hash(description: str, date: str = "", location: str = "") -> str:
    """Deterministic MD5 fingerprint from normalized text fields."""
    norm_desc = " ".join((description or "").strip().lower().split())
    norm_date = (date or "").strip().lower()
    norm_loc  = (location or "").strip().lower()
    raw = f"{norm_desc}|{norm_date}|{norm_loc}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ─── Database operations ──────────────────────────────────────────────────────

def create_report(db: Session, payload: ReportCreate) -> Report:
    """
    Analyze the description, persist the report (or return existing if duplicate), and return the ORM object.
    """
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    analysis = analyze_text(payload.description)
    norm_desc = " ".join(payload.description.strip().lower().split())
    raw = f"{norm_desc}|{date_str}|{analysis['category'].lower()}"
    r_id = hashlib.md5(raw.encode("utf-8")).hexdigest()

    existing = db.query(Report).filter(Report.report_id == r_id).first()
    if existing:
        return existing

    db_report = Report(
        report_id     = r_id,
        description   = payload.description,
        category      = analysis["category"],
        risk_score    = analysis["risk_score"],
        sif_potential = analysis["sif_potential"],
        risk_level    = analysis["risk_level"],
        date          = date_str,
        created_at    = datetime.now(timezone.utc),
    )
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report


def get_all_reports(
    db: Session,
    search: str | None = None,
    risk_level: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> tuple[list[Report], int]:
    """Return filtered reports and total count ordered newest first."""
    query = db.query(Report)
    if search:
        query = query.filter(Report.description.ilike(f"%{search.strip()}%"))
    if risk_level and risk_level.upper() in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        query = query.filter(Report.risk_level == risk_level.strip().upper())

    total = query.count()
    query = query.order_by(Report.created_at.desc())
    if offset is not None:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)

    return query.all(), total


def get_report_by_id(db: Session, report_id: str | int) -> Report | None:
    """Return a single report by primary key, or None."""
    rep_str = str(report_id)
    return db.query(Report).filter(Report.report_id == rep_str).first()
