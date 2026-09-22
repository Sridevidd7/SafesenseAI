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
from services.analytics_service import refresh_analytics_cache

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

# Optional columns the pipeline will use if present in the CSV.
_OPTIONAL_REPORT_ID   = {"report_id", "id", "incident_id", "report_number", "rpt_id"}
_OPTIONAL_SEVERITY    = {"severity", "risk_severity", "severity_level", "risk_level"}
_OPTIONAL_REPORT_TYPE = {"report_type", "type", "category_input", "incident_type", "category", "life_saving_rule"}
_OPTIONAL_DATE        = {"date", "incident_date", "timestamp", "datetime", "created_date", "time"}
_OPTIONAL_LOCATION    = {"location", "site", "area", "workplace", "facility", "plant"}

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
    sif_count:          int
    description_column: str


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
    df = _parse_bytes(file_bytes, filename)

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
    activity_col    = _detect_optional_column(list(df.columns), {"activity", "task", "work", "operation", "job"})

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

    now = datetime.now(timezone.utc)

    for idx, row in df.iterrows():
        description = normalize_text(str(row[desc_col]))

        # Skip rows where description is missing or too short
        if len(description) < 5:
            skipped += 1
            if len(skipped_reasons) < 20:
                skipped_reasons.append(
                    f"Row {idx + 2}: description is empty or too short "
                    f"(got {len(description)!r} chars)."
                )
            continue

        # Extract optional fields
        severity    = normalize_text(str(row[severity_col]))    if severity_col    else ""
        report_type = normalize_text(str(row[report_type_col])) if report_type_col else ""
        date_raw    = normalize_text(str(row[date_col]))        if date_col        else ""
        date_val    = normalize_date(date_raw)
        
        # Site & Activity extraction with auto-fix fallback defaults
        site_raw     = normalize_text(str(row[site_col]))     if site_col     else ""
        activity_raw = normalize_text(str(row[activity_col])) if activity_col else ""
        site_val     = site_raw if site_raw else "Site Alpha"
        activity_val = activity_raw if activity_raw else "General Operation"

        # Compute content hash
        c_hash = compute_content_hash(description, date_val, site_val)

        # Run rule engine
        analysis = analyze_text(description)
        cat_val  = report_type if report_type else analysis["category"]

        # Determine report_id (user-supplied or deterministic hash)
        if report_id_col and str(row[report_id_col]).strip():
            row_id = str(row[report_id_col]).strip()
        else:
            row_id = c_hash

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

        # Determine risk level
        effective_level = analysis["risk_level"]
        if severity.lower() in ("critical", "high", "medium", "low"):
            effective_level = severity.upper()

        # Build ORM object
        db_obj = Report(
            report_id     = row_id,
            content_hash  = c_hash,
            description   = description,
            category      = cat_val,
            risk_score    = analysis["risk_score"],
            sif_potential = analysis["sif_potential"],
            risk_level    = effective_level,
            site          = site_val,
            activity      = activity_val,
            date          = date_val,
            created_at    = now,
        )
        db_objects.append(db_obj)

        # Accumulate stats
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
                "sif_potential": analysis["sif_potential"],
                "site":          site_val,
                "activity":      activity_val,
                "date":          date_val,
            })

    if not db_objects and duplicates_skipped == 0:
        raise ValueError(
            f"No valid rows found in '{filename}'. "
            f"All {skipped} row(s) were skipped ({skipped_reasons[0] if skipped_reasons else 'empty descriptions'})."
        )

    # ── 5. Bulk insert & automatic analytics cache refresh ────────────────────
    if db_objects:
        db.add_all(db_objects)
        db.commit()
        # Automatically refresh analytics cache after inserting new records
        refresh_analytics_cache(db)

    # Track uploaded file hash for idempotent file-level tracking
    file_hash = hashlib.md5(file_bytes).hexdigest()
    try:
        existing_file = db.query(UploadedFile).filter(UploadedFile.file_hash == file_hash).first()
        if not existing_file:
            uploaded_file_record = UploadedFile(
                file_hash   = file_hash,
                filename    = filename,
                uploaded_at = now,
            )
            db.add(uploaded_file_record)
            db.commit()
    except Exception:
        db.rollback()

    msg = (
        f"Successfully ingested {len(db_objects)} new reports."
        if duplicates_skipped == 0
        else f"Ingested {len(db_objects)} new reports ({duplicates_skipped} duplicate rows skipped)."
    )

    logger.info(
        f"[{datetime.now(timezone.utc).isoformat()}] EVENT=bulk_upload_completed "
        f"FILENAME={filename} INSERTED={len(db_objects)} DUPLICATES={duplicates_skipped} TOTAL_ROWS={len(df)}"
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
        description_column = desc_col,
    )
