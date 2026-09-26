"""
services/upload_service.py — CSV / Excel bulk upload processing pipeline.

Responsibilities
----------------
1. Parse the uploaded file bytes with pandas (CSV or Excel).
2. Validate structure: file must not be empty, must contain a 'description' column.
3. For every valid row, compute deterministic content_hash (description + date + site).
4. Run rule engine analysis (category, risk_score, sif_potential, risk_level).
5. Bulk-insert all unique Report ORM objects in a single DB transaction.
6. Automatically trigger refresh_analytics_cache(db).
7. Return a typed UploadResult dataclass consumed by the route layer.
"""
from __future__ import annotations

import hashlib
import io
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from models import Report, UploadedFile
from services.report_service import (
    analyze_text,
    compute_content_hash,
    normalize_text,
    normalize_date,
)
from services.analytics_service import invalidate_analytics_cache, get_total_reports
from services.pii_service import redact_pii

logger = logging.getLogger("safesense.upload")
logging.basicConfig(level=logging.INFO)

# The mandatory description column aliases.
_DESCRIPTION_ALIASES = {
    "description",
    "report_text",
    "observation",
    "text",
    "details",
    "incident_description",
    "safety_observation",
}

# Optional columns the pipeline will use if present in the CSV (ordered by priority).
_OPTIONAL_REPORT_ID   = ("report_id", "id", "incident_id", "report_number", "rpt_id")
_OPTIONAL_SEVERITY    = ("severity", "risk_severity", "severity_level", "risk_level")
_OPTIONAL_REPORT_TYPE = ("report_type", "type", "category_input", "incident_type", "category", "life_saving_rule")
_OPTIONAL_DATE        = ("date", "incident_date", "timestamp", "datetime", "created_date", "time")
_OPTIONAL_LOCATION    = ("site", "plant", "facility", "installation", "location", "workplace")
_OPTIONAL_UNIT        = ("unit", "operating_unit", "plant_unit", "process_unit", "refinery_unit", "facility_unit")
_OPTIONAL_AREA        = ("area", "work_area", "zone", "section", "location_area", "bay", "sector")
_OPTIONAL_BARRIER     = ("barrier_failure", "barrier", "failed_barrier", "control_failure", "barrier_type")
_OPTIONAL_ACTIVITY    = ("activity", "task", "work", "operation", "job")

SAMPLE_SIZE = 5   # number of processed rows returned in the response


# ─── Result dataclasses ───────────────────────────────────────────────────────

@dataclass
class ProcessedRow:
    """One successfully processed report row."""
    row_index:     int
    saved_id:      str   # primary key in DB
    report_id:     str
    description:   str
    category:      str
    risk_score:    int
    risk_level:    str
    sif_potential: str
    date:          str


@dataclass
class UploadResult:
    """Aggregated result returned to the route handler."""
    filename:           str
    inserted:           int          # newly inserted rows
    duplicates:         int          # duplicate rows skipped
    total:              int          # total data rows in CSV
    total_rows:         int          # alias for total
    processed:          int          # rows evaluated
    duplicates_skipped: int          # alias for duplicates
    file_duplicate:     bool         # true if the entire file was a duplicate
    message:            str          # status or info message
    skipped:            int          # rows skipped (empty description)
    skipped_reasons:    list[str]    # human-readable skip reasons
    sample:             list[dict]   # first SAMPLE_SIZE saved rows
    risk_summary:       dict[str, int]
    sif_count:          int          = 0
    description_column: str          = ""
    pii_detected_count: int          = 0
    pii_total_redacted: int          = 0
    success:            bool         = True
    database_total:     int          = 0


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _detect_description_column(columns: list[str]) -> Optional[str]:
    """
    Find the description column by checking known aliases (case-insensitive).
    """
    normalised = {c.strip().lower(): c for c in columns}
    for alias in _DESCRIPTION_ALIASES:
        if alias in normalised:
            return normalised[alias]
    return None


def _detect_optional_column(columns: list[str], aliases: set[str]) -> Optional[str]:
    """Find an optional column by alias set. Returns original name or None."""
    normalised = {c.strip().lower(): c for c in columns}
    for alias in aliases:
        if alias in normalised:
            return normalised[alias]
    return None


def _parse_bytes(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """
    Parse raw bytes into a DataFrame.
    Supports .csv, .xlsx, .xls.
    """
    name_lower = filename.lower()
    try:
        if name_lower.endswith(".csv"):
            try:
                df = pd.read_csv(io.BytesIO(file_bytes), dtype=str, keep_default_na=False)
            except UnicodeDecodeError:
                df = pd.read_csv(
                    io.BytesIO(file_bytes),
                    dtype=str,
                    keep_default_na=False,
                    encoding="latin-1",
                )
        elif name_lower.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(file_bytes), dtype=str)
            df = df.fillna("")
        else:
            raise ValueError(
                f"Unsupported file type '{filename}'. "
                "Upload a .csv, .xlsx, or .xls file."
            )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Failed to parse '{filename}': {exc}") from exc

    return df


# ─── Public API ───────────────────────────────────────────────────────────────

def process_csv_upload(
    db:         Session,
    file_bytes: bytes,
    filename:   str,
) -> UploadResult:
    """
    Full pipeline: parse → validate → deduplicate → analyse → persist → auto-refresh.
    """
    # ── 1. Parse file ─────────────────────────────────────────────────────────
    t_start = time.time()
    logger.info(
        f"[{datetime.now(timezone.utc).isoformat()}] EVENT=UPLOAD_START "
        f"FILENAME={filename} BYTES={len(file_bytes)}"
    )

    df = _parse_bytes(file_bytes, filename)

    logger.info(
        f"[{datetime.now(timezone.utc).isoformat()}] EVENT=UPLOAD_PARSED "
        f"FILENAME={filename} ROWS={len(df)} ELAPSED_MS={round((time.time() - t_start) * 1000, 1)}"
    )

    if df.empty:
        raise ValueError(
            f"'{filename}' is empty (no data rows after the header)."
        )

    # ── 2. Detect required & optional columns ─────────────────────────────────
    desc_col = _detect_description_column(list(df.columns))
    if desc_col is None:
        available = ", ".join(f'"{c}"' for c in df.columns)
        raise ValueError(
            f"No description column found in '{filename}'. "
            f"Column must be named one of: {', '.join(sorted(_DESCRIPTION_ALIASES))}. "
            f"Columns found: {available}."
        )

    report_id_col   = _detect_optional_column(list(df.columns), _OPTIONAL_REPORT_ID)
    severity_col    = _detect_optional_column(list(df.columns), _OPTIONAL_SEVERITY)
    report_type_col = _detect_optional_column(list(df.columns), _OPTIONAL_REPORT_TYPE)
    date_col        = _detect_optional_column(list(df.columns), _OPTIONAL_DATE)
    site_col        = _detect_optional_column(list(df.columns), _OPTIONAL_LOCATION)
    unit_col        = _detect_optional_column(list(df.columns), _OPTIONAL_UNIT)
    area_col        = _detect_optional_column(list(df.columns), _OPTIONAL_AREA)
    barrier_col     = _detect_optional_column(list(df.columns), _OPTIONAL_BARRIER)
    activity_col    = _detect_optional_column(list(df.columns), _OPTIONAL_ACTIVITY)

    # ── 3. Preload existing IDs and hashes for row-level deduplication ────────
    existing_db_ids: set[str] = {
        row[0]
        for row in db.query(Report.report_id).all()
        if row[0]
    }
    existing_db_hashes: set[str] = {
        row[0]
        for row in db.query(Report.content_hash).all()
        if row[0]
    }
    seen_in_batch_ids: set[str] = set()
    seen_in_batch_hashes: set[str] = set()

    # ── 4. Process rows ───────────────────────────────────────────────────────
    db_objects:         list[Report]       = []
    sample_rows:        list[dict]         = []
    skipped:            int                = 0
    duplicates_skipped: int                = 0
    skipped_reasons:    list[str]          = []
    risk_summary:       dict[str, int]     = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    sif_count:          int                = 0
    pii_rows_count:     int                = 0
    pii_total_count:    int                = 0

    now = datetime.now(timezone.utc)

    for idx, row in df.iterrows():
        raw_description = normalize_text(str(row[desc_col]))

        # Skip rows where description is missing or too short
        if len(raw_description) < 5:
            skipped += 1
            if len(skipped_reasons) < 20:
                skipped_reasons.append(
                    f"Row {idx + 2}: description is empty or too short "
                    f"(got {len(raw_description)!r} chars)."
                )
            continue

        # ── PII Preprocessing BEFORE NLP / Risk Engine ──
        pii_res = redact_pii(raw_description)
        description = pii_res.redacted_text
        if pii_res.pii_detected:
            pii_rows_count += 1
            pii_total_count += pii_res.pii_count

        # Extract optional fields
        severity    = normalize_text(str(row[severity_col]))    if severity_col    else ""
        report_type = normalize_text(str(row[report_type_col])) if report_type_col else ""
        date_raw    = normalize_text(str(row[date_col]))        if date_col        else ""
        date_val    = normalize_date(date_raw)
        
        # Site, Unit, Area & Activity extraction with fallback defaults
        site_raw     = normalize_text(str(row[site_col]))     if site_col     else ""
        unit_raw     = normalize_text(str(row[unit_col]))     if unit_col     else ""
        area_raw     = normalize_text(str(row[area_col]))     if area_col     else ""
        activity_raw = normalize_text(str(row[activity_col])) if activity_col else ""
        barrier_raw  = normalize_text(str(row[barrier_col]))  if barrier_col  else ""

        site_val     = site_raw     if site_raw     else "Site Alpha"
        unit_val     = unit_raw     if unit_raw     else "Not Specified"
        area_val     = area_raw     if area_raw     else "Not Specified"
        activity_val = activity_raw if activity_raw else "General Operation"

        # Compute content hash from sanitized description
        c_hash = compute_content_hash(description, date_val, site_val)

        # Run rule engine on SANITIZED description
        analysis = analyze_text(description)
        cat_val  = report_type if report_type else analysis["category"]

        # Determine barrier failure (CSV specified or engine detected)
        detected_b = analysis.get("barrier") or analysis.get("barrier_failure")
        barrier_val = barrier_raw if barrier_raw else (detected_b if detected_b else "Unspecified")

        # Determine report_id (user-supplied or deterministic hash)
        if report_id_col and str(row[report_id_col]).strip():
            row_id = str(row[report_id_col]).strip()
        else:
            row_id = c_hash

        # Determine risk level
        effective_level = analysis["risk_level"]
        if severity.lower() in ("critical", "high", "medium", "low"):
            effective_level = severity.upper()

        # Accumulate stats for processed batch
        risk_summary[effective_level] = risk_summary.get(effective_level, 0) + 1
        if analysis["sif_potential"] == "YES":
            sif_count += 1

        if len(sample_rows) < SAMPLE_SIZE:
            sample_rows.append({
                "row_index":     int(idx) + 2,
                "saved_id":      row_id,
                "report_id":     row_id,
                "description":   description,
                "category":      cat_val,
                "risk_score":    analysis["risk_score"],
                "risk_level":    effective_level,
                "risk_reason":   analysis.get("risk_reason"),
                "sif_potential": analysis["sif_potential"],
                "site":          site_val,
                "activity":      activity_val,
                "date":          date_val,
            })

        # Check for duplicate by ID or by content hash
        if (
            row_id in existing_db_ids
            or row_id in seen_in_batch_ids
            or c_hash in existing_db_hashes
            or c_hash in seen_in_batch_hashes
        ):
            duplicates_skipped += 1
            continue

        seen_in_batch_ids.add(row_id)
        seen_in_batch_hashes.add(c_hash)

        # Build ORM object with sanitized description and metadata
        db_obj = Report(
            report_id       = row_id,
            content_hash    = c_hash,
            description     = description,
            category        = cat_val,
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
        db_objects.append(db_obj)

    logger.info(
        f"[{datetime.now(timezone.utc).isoformat()}] EVENT=UPLOAD_ANALYSIS_COMPLETE "
        f"FILENAME={filename} VALID_REPORTS={len(db_objects)} DUPLICATES={duplicates_skipped} "
        f"SKIPPED={skipped} ELAPSED_MS={round((time.time() - t_start) * 1000, 1)}"
    )

    if not db_objects and duplicates_skipped == 0:
        raise ValueError(
            f"No valid rows found in '{filename}'. "
            f"All {skipped} row(s) were skipped ({skipped_reasons[0] if skipped_reasons else 'empty descriptions'})."
        )

    # ── 5. Bulk insert & atomic persistence ──────────────────────────────────
    file_hash = hashlib.md5(file_bytes).hexdigest()
    existing_file = db.query(UploadedFile).filter(UploadedFile.file_hash == file_hash).first()

    if db_objects or not existing_file:
        try:
            if db_objects:
                db.add_all(db_objects)
            if not existing_file:
                uploaded_file_record = UploadedFile(
                    file_hash   = file_hash,
                    filename    = filename,
                    uploaded_at = now,
                )
                db.add(uploaded_file_record)
            db.commit()
            logger.info(
                f"[{datetime.now(timezone.utc).isoformat()}] EVENT=UPLOAD_DB_COMMIT "
                f"FILENAME={filename} INSERTED={len(db_objects)} ELAPSED_MS={round((time.time() - t_start) * 1000, 1)}"
            )
        except Exception as exc:
            db.rollback()
            logger.error(
                f"[{datetime.now(timezone.utc).isoformat()}] EVENT=UPLOAD_DB_ERROR "
                f"FILENAME={filename} ERROR={str(exc)} ELAPSED_MS={round((time.time() - t_start) * 1000, 1)}"
            )
            raise

    # ── 6. Fast non-blocking cache invalidation ──────────────────────────────
    try:
        invalidate_analytics_cache()
        logger.info(
            f"[{datetime.now(timezone.utc).isoformat()}] EVENT=UPLOAD_CACHE_INVALIDATED "
            f"FILENAME={filename} ELAPSED_MS={round((time.time() - t_start) * 1000, 1)}"
        )
    except Exception as exc:
        logger.warning(f"Non-fatal error invalidating analytics cache: {exc}")

    # Authoritative current database count for client confirmation
    database_total = 0
    try:
        database_total = get_total_reports(db)
    except Exception as exc:
        logger.warning(f"Could not read total reports count: {exc}")

    msg = (
        f"Successfully ingested {len(db_objects)} new reports."
        if duplicates_skipped == 0
        else f"Ingested {len(db_objects)} new reports ({duplicates_skipped} duplicate rows skipped)."
    )

    logger.info(
        f"[{datetime.now(timezone.utc).isoformat()}] EVENT=UPLOAD_COMPLETE "
        f"FILENAME={filename} INSERTED={len(db_objects)} DUPLICATES={duplicates_skipped} "
        f"TOTAL_ROWS={len(df)} DATABASE_TOTAL={database_total} TOTAL_ELAPSED_MS={round((time.time() - t_start) * 1000, 1)}"
    )

    return UploadResult(
        filename           = filename,
        inserted           = len(db_objects),
        duplicates         = duplicates_skipped,
        total              = len(df),
        total_rows         = len(df),
        processed          = len(db_objects) + duplicates_skipped,
        duplicates_skipped = duplicates_skipped,
        file_duplicate     = (len(db_objects) == 0 and duplicates_skipped > 0),
        message            = msg,
        skipped            = skipped,
        skipped_reasons    = skipped_reasons,
        sample             = sample_rows,
        risk_summary       = risk_summary,
        sif_count          = sif_count,
        pii_detected_count = pii_rows_count,
        pii_total_redacted = pii_total_count,
        description_column = desc_col,
        success            = True,
        database_total     = database_total,
    )
