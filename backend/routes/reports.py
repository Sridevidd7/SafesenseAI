"""
routes/reports.py — All /reports endpoints.

Route handlers are intentionally thin:
  - validate input via Pydantic (automatic)
  - call the service layer
  - return a typed response schema
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from database import get_db
from datetime import datetime, timezone
from schemas import ReportCreate, ReportResponse, ReportListResponse, UploadResponse, MetaInfo
from services.auth import require_authenticated, require_write
import services.report_service as svc
import services.upload_service as upload_svc
import services.analytics_service as analytics_svc

router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
)


def _build_meta(total_reports: int) -> MetaInfo:
    return MetaInfo(
        total_reports=total_reports,
        last_updated=datetime.now(timezone.utc).isoformat(),
        source="db",
    )


@router.post(
    "",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new safety report",
    description=(
        "Accepts a free-text safety observation, runs the HSE rule engine "
        "(LSR classification + weighted risk score), persists the result, "
        "and returns the stored record."
    ),
)
def create_report(
    payload: ReportCreate,
    db: Session = Depends(get_db),
    user=Depends(require_write),
) -> ReportResponse:
    report = svc.create_report(db, payload)
    total = analytics_svc.get_total_reports(db)
    meta = _build_meta(total)
    
    rep_dict = {
        "report_id":     report.report_id,
        "id":            report.report_id,
        "description":   report.description,
        "category":      report.category,
        "risk_score":    report.risk_score,
        "sif_potential": report.sif_potential,
        "risk_level":    report.risk_level,
        "site":          report.site,
        "unit":          getattr(report, "unit", "Not Specified"),
        "area":          getattr(report, "area", "Not Specified"),
        "activity":      report.activity,
        "barrier_failure": getattr(report, "barrier_failure", "Unspecified"),
        "pii_detected":  bool(getattr(report, "pii_detected", 0)),
        "pii_count":     int(getattr(report, "pii_count", 0)),
        "pii_types":     str(getattr(report, "pii_types", "")),
        "date":          report.date,
        "created_at":    report.created_at,
    }
    return ReportResponse(
        **rep_dict,
        data=rep_dict,
        meta=meta,
    )


from typing import Optional

@router.get(
    "",
    response_model=ReportListResponse,
    summary="List all safety reports",
    description="Returns stored reports ordered newest first with optional search, filter, and pagination.",
)
def list_reports(
    search: Optional[str] = None,
    risk_level: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    db: Session = Depends(get_db),
    user=Depends(require_authenticated),
) -> ReportListResponse:
    reports, total = svc.get_all_reports(
        db,
        search=search,
        risk_level=risk_level,
        limit=limit,
        offset=offset,
    )
    meta = _build_meta(total)
    resp_reports = [ReportResponse.model_validate(r) for r in reports]
    return ReportListResponse(
        total=total,
        reports=resp_reports,
        data=resp_reports,
        meta=meta,
    )


@router.get(
    "/{report_id}",
    response_model=ReportResponse,
    summary="Get a single safety report by ID",
)
def get_report(
    report_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_authenticated),
) -> ReportResponse:
    report = svc.get_report_by_id(db, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with id={report_id} not found.",
        )
    total = analytics_svc.get_total_reports(db)
    meta = _build_meta(total)
    rep_dict = {
        "report_id":     report.report_id,
        "id":            report.report_id,
        "description":   report.description,
        "category":      report.category,
        "risk_score":    report.risk_score,
        "sif_potential": report.sif_potential,
        "risk_level":    report.risk_level,
        "site":          report.site,
        "unit":          getattr(report, "unit", "Not Specified"),
        "area":          getattr(report, "area", "Not Specified"),
        "activity":      report.activity,
        "barrier_failure": getattr(report, "barrier_failure", "Unspecified"),
        "pii_detected":  bool(getattr(report, "pii_detected", 0)),
        "pii_count":     int(getattr(report, "pii_count", 0)),
        "pii_types":     str(getattr(report, "pii_types", "")),
        "date":          report.date,
        "created_at":    report.created_at,
    }
    return ReportResponse(
        **rep_dict,
        data=rep_dict,
        meta=meta,
    )


from services.llm_service import generate_llm_explanation
from services.risk_engine import analyze_report



@router.get(
    "/{report_id}/explain",
    summary="Generate or retrieve grounded LLM explanation for a report",
)
async def explain_report(
    report_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_authenticated),
):
    report = svc.get_report_by_id(db, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with id={report_id} not found.",
        )
    
    # Run analysis for rich barrier/rule context
    analysis = analyze_report({"report_text": report.description})
    report_data = {
        "id": report.report_id,
        "report_id": report.report_id,
        "description": report.description,
        "life_saving_rule": report.category or analysis.get("life_saving_rule"),
        "primary_rule": analysis.get("primary_rule") or report.category or analysis.get("life_saving_rule"),
        "secondary_rule": analysis.get("secondary_rule"),
        "rule_scores": analysis.get("rule_scores", {}),
        "barrier_failures": analysis.get("barrier_failures") or [report.category],
        "barrier_evidence": analysis.get("barrier_evidence") or [],
        "risk_score": report.risk_score,
        "risk_level": report.risk_level,
        "sif_potential": report.sif_potential,
        "confidence": analysis.get("confidence", 0.95),
    }
    explanation = await generate_llm_explanation(report_data)
    return explanation


@router.post(
    "/explain",
    summary="Generate grounded LLM explanation for custom report data",
)
async def explain_custom_report(
    payload: dict,
    user=Depends(require_authenticated),
):
    explanation = await generate_llm_explanation(payload)
    return explanation


# ─── CSV / Excel bulk upload ──────────────────────────────────────────────────


_ALLOWED_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",   # browsers sometimes send this for .csv
}

_ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bulk upload safety reports from CSV or Excel",
    description=(
        "Upload a CSV or Excel file. The file must contain a column named "
        "'description' (or a recognised alias: report_text, observation, text, "
        "details, incident_description, safety_observation). "
        "Each row is analysed by the HSE rule engine and saved to the database. "
        "Returns processing statistics and a 5-row sample."
    ),
)
def upload_csv(
    file: UploadFile = File(
        ...,
        description="CSV or Excel file with a 'description' column",
    ),
    db: Session = Depends(get_db),
    user=Depends(require_write),
) -> UploadResponse:
    # ── Validate filename extension ───────────────────────────────────────────
    filename = file.filename or "upload"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"File extension '{ext}' is not supported. "
                f"Upload a .csv, .xlsx, or .xls file."
            ),
        )

    # ── Read bytes & enforce file size limit ──────────────────────────────────
    from config import settings
    raw_bytes = file.file.read()
    if len(raw_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty (0 bytes).",
        )
    if len(raw_bytes) > settings.max_upload_size_bytes:
        max_mb = settings.max_upload_size_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum allowed upload limit ({max_mb} MB).",
        )

    # ── Delegate to service layer ─────────────────────────────────────────────
    try:
        result = upload_svc.process_csv_upload(
            db         = db,
            file_bytes = raw_bytes,
            filename   = filename,
        )
    except ValueError as exc:
        # Structural errors from the service (missing column, empty file, etc.)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    # ── Map dataclass → Pydantic response schema ──────────────────────────────
    return UploadResponse(
        inserted           = result.inserted,
        duplicates         = result.duplicates,
        total              = result.total,
        filename           = result.filename,
        total_rows         = result.total_rows,
        processed          = result.processed,
        duplicates_skipped = result.duplicates_skipped,
        file_duplicate     = result.file_duplicate,
        message            = result.message,
        skipped            = result.skipped,
        skipped_reasons    = result.skipped_reasons,
        sample             = result.sample,
        risk_summary       = result.risk_summary,
        sif_count          = result.sif_count,
        pii_detected_count = result.pii_detected_count,
        pii_total_redacted = result.pii_total_redacted,
        description_column = result.description_column,
        success            = getattr(result, "success", True),
        database_total     = getattr(result, "database_total", 0),
    )
