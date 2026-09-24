"""
services/report_service.py — Business logic for safety report ingestion and processing.

Standardized Single Ingestion Pipeline:
- Single insert_report() function handles all entry points (CSV upload, manual entry, API).
- Text normalization, date normalization, and site/activity normalization.
- Ingestion-level MD5 content hashing (description + date + site).
- Database-level deduplication via content_hash and report_id.
- Automatic analytics cache refresh on write.
- Structured logging.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple, Union
import pandas as pd
from sqlalchemy.orm import Session

from models import Report
from schemas import ReportCreate
from services.risk_engine import (
    detect_lsr as engine_detect_lsr,
    detect_barrier as engine_detect_barrier,
    detect_barriers as engine_detect_barriers,
    calculate_risk_score as engine_calculate_risk_score,
    analyze_report as engine_analyze_report,
)
from services.analytics_service import refresh_analytics_cache

logger = logging.getLogger("safesense.ingestion")
logging.basicConfig(level=logging.INFO)


# ─── Normalization and Hashing Helpers ────────────────────────────────────────

def normalize_text(text: str) -> str:
    """Normalize text by stripping and collapsing whitespace."""
    if not text:
        return ""
    return " ".join(str(text).strip().split())


def normalize_date(date_val: Any) -> str:
    """Normalize date to YYYY-MM-DD or default to today."""
    if not date_val or not str(date_val).strip():
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    s = str(date_val).strip()
    try:
        dt = pd.to_datetime(s, errors="coerce")
        if pd.notnull(dt):
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def compute_content_hash(description: str, date: str = "", site: str = "") -> str:
    """
    Generate deterministic MD5 content fingerprint from (description + date + site).
    Prevents duplicate dataset uploads and duplicate observations even if report_id differs.
    """
    norm_desc = normalize_text(description).lower()
    norm_date = normalize_text(date).lower()
    norm_site = normalize_text(site or "site alpha").lower()
    raw = f"{norm_desc}|{norm_date}|{norm_site}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ─── Risk Engine Wrappers ─────────────────────────────────────────────────────

def detect_lsr(text: str) -> str:
    return engine_detect_lsr(text)


def detect_barrier(text: str) -> str:
    return engine_detect_barrier(text)


def detect_barriers(text: str) -> list[str]:
    return engine_detect_barriers(text)


def calculate_risk_score(
    text:        str,
    lsr:         str = "",
    barrier:     str = "",
    severity:    str = "",
    report_type: str = "",
) -> int:
    result = engine_calculate_risk_score({
        "report_text": text,
        "life_saving_rule": lsr or None,
        "barrier_failure": barrier or None,
        "severity": severity or None,
        "report_type": report_type or None,
    })
    return result["risk_score"]


def is_sif(text: str, score: int = 0) -> bool:
    analysis = engine_analyze_report({"report_text": text})
    return analysis["sif_potential"] == "YES"


def analyze_text(description: str) -> dict[str, Any]:
    """
    Run the full context-aware rule engine on raw description text.
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
        "risk_reason":      analysis.get("risk_reason"),
        "sif_potential":    analysis["sif_potential"],
        "negation_type":    analysis["negation_type"],
        "explanation":      analysis["explanation"],
    }


# ─── Standard Ingestion Pipeline ──────────────────────────────────────────────

def insert_report(
    db: Session,
    data: Union[dict[str, Any], ReportCreate],
    auto_commit: bool = True,
    refresh_cache: bool = True,
) -> Tuple[Report, bool]:
    """
    Standardized single ingestion function for all entry points (CSV, manual entry, API).

    Responsibilities:
    1. Normalizes fields (description, date, site, activity).
    2. Computes content_hash for database-level deduplication.
    3. Checks for existing record by content_hash or report_id.
    4. Runs rule engine analysis for new records.
    5. Inserts new Report ORM object.
    6. Automatically triggers analytics refresh on insert.

    Returns:
        tuple (Report, inserted_boolean)
    """
    raw_dict: dict[str, Any] = data.dict() if hasattr(data, "dict") else dict(data)
    
    raw_desc = normalize_text(raw_dict.get("description") or raw_dict.get("report_text") or "")
    if len(raw_desc) < 5:
        raise ValueError("Report description must be at least 5 characters.")

    # ── PII Preprocessing BEFORE NLP / Risk Engine ──
    from services.pii_service import redact_pii
    pii_res = redact_pii(raw_desc)
    description = pii_res.redacted_text

    raw_date = raw_dict.get("date") or raw_dict.get("incident_date") or ""
    date_val = normalize_date(raw_date)

    raw_site = raw_dict.get("site") or raw_dict.get("location") or ""
    site_val = normalize_text(raw_site) if raw_site else "Site Alpha"

    raw_unit = raw_dict.get("unit") or ""
    unit_val = normalize_text(raw_unit) if raw_unit else "Not Specified"

    raw_area = raw_dict.get("area") or ""
    area_val = normalize_text(raw_area) if raw_area else "Not Specified"

    raw_activity = raw_dict.get("activity") or raw_dict.get("task") or ""
    activity_val = normalize_text(raw_activity) if raw_activity else "General Operation"

    # Compute deterministic content hash for ingestion deduplication
    c_hash = compute_content_hash(description, date_val, site_val)

    # Determine report_id (user supplied or hash)
    supplied_id = str(raw_dict.get("report_id") or raw_dict.get("id") or "").strip()
    r_id = supplied_id if supplied_id else c_hash

    # Check for existing duplicate by content_hash or report_id
    existing = db.query(Report).filter(
        (Report.content_hash == c_hash) | (Report.report_id == r_id)
    ).first()

    if existing:
        logger.info(
            f"[{datetime.now(timezone.utc).isoformat()}] EVENT=ingestion_duplicate_skipped "
            f"REPORT_ID={existing.report_id} HASH={c_hash[:8]}... SITE={existing.site}"
        )
        return existing, False

    # Run analysis on SANITIZED description
    analysis = analyze_text(description)
    user_cat = raw_dict.get("category") or raw_dict.get("report_type")
    effective_category = str(user_cat).strip() if user_cat else analysis["category"]

    user_sev = str(raw_dict.get("severity") or raw_dict.get("risk_level") or "").strip().upper()
    effective_level = user_sev if user_sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW") else analysis["risk_level"]

    raw_barrier = raw_dict.get("barrier_failure") or raw_dict.get("barrier") or ""
    barrier_val = normalize_text(raw_barrier) if raw_barrier else (analysis.get("barrier") or "Unspecified")

    now = datetime.now(timezone.utc)
    new_report = Report(
        report_id       = r_id,
        content_hash    = c_hash,
        description     = description,
        category        = effective_category,
        risk_score      = analysis["risk_score"],
        sif_potential   = analysis["sif_potential"],
        risk_level      = effective_level,
        site            = site_val,
        unit            = unit_val,
        area            = area_val,
        activity        = activity_val,
        barrier_failure = barrier_val,
        pii_detected    = 1 if pii_res.pii_detected else 0,
        pii_count       = pii_res.pii_count,
        pii_types       = ", ".join(pii_res.pii_types),
        date            = date_val,
        created_at      = now,
    )

    db.add(new_report)

    if auto_commit:
        db.commit()
        db.refresh(new_report)
        if refresh_cache:
            refresh_analytics_cache(db)

    logger.info(
        f"[{datetime.now(timezone.utc).isoformat()}] EVENT=ingestion_report_created "
        f"REPORT_ID={new_report.report_id} HASH={c_hash[:8]}... LEVEL={effective_level} SIF={analysis['sif_potential']}"
    )

    # Phase 6 Batch 2: optional embedding-persistence hook (default OFF via
    # SAFESENSE_EMBEDDINGS). Purely advisory infrastructure; it never alters
    # the report row, analysis, risk, or SIF outputs, and degrades to a no-op
    # when disabled. See services/vector_store.py for the safety boundary.
    try:
        from services.vector_store import queue_embedding_on_ingest
        queue_embedding_on_ingest(new_report.report_id, description)
    except Exception:
        # Vector infrastructure must never affect deterministic ingestion.
        pass

    return new_report, True


def create_report(db: Session, payload: ReportCreate) -> Report:
    """
    API entry point for POST /api/reports.
    Standardized to call insert_report().
    """
    report, _ = insert_report(db, payload, auto_commit=True, refresh_cache=True)
    return report


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

    results = query.all()
    logger.info(f"[{datetime.now(timezone.utc).isoformat()}] EVENT=query_list_reports TOTAL={total} RETURNED={len(results)}")
    return results, total


def get_report_by_id(db: Session, report_id: str | int) -> Report | None:
    """Return a single report by primary key, or None."""
    rep_str = str(report_id)
    return db.query(Report).filter(Report.report_id == rep_str).first()
