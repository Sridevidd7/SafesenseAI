"""
SafeSense AI — FastAPI Backend
================================
Production-hardened backend supporting SQLite (local/demo) and PostgreSQL (production-target).
"""
from __future__ import annotations

import io
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

# ─── Configuration & Logging Bootstrap (Phase 7) ──────────────────────────────
from config import settings
from utils.logging_config import configure_logging

configure_logging(is_production=settings.is_production)
logger = logging.getLogger("safesense.api")

# Enforce fail-fast configuration checks on production startup
try:
    settings.validate_production()
except ValueError as val_err:
    logger.critical(f"FATAL: Production configuration error: {val_err}")
    raise

# ─── Database bootstrap ───────────────────────────────────────────────────────
from database import Base, IS_SQLITE, engine, get_db, ping_database
import models  # registers ORM models with Base metadata

# In SQLite mode, tables are created automatically on startup.
# In PostgreSQL mode, schema is owned and applied exclusively by Alembic.
if IS_SQLITE:
    Base.metadata.create_all(bind=engine)

# ─── Service imports ──────────────────────────────────────────────────────────
from services.auth import create_access_token, verify_password, verify_token
from services.multilingual import LANG_DISPLAY, process_dataset, process_report
from services.report_generator import generate_summary_report
from services.risk_engine import (
    analyze_report,
    calculate_risk_score,
    compute_patterns,
    compute_site_risk,
)
from services.upload_service import process_csv_upload
from schemas import UploadResponse

# ─── Routers ──────────────────────────────────────────────────────────────────
from routes.actions import router as actions_router
from routes.admin import router as admin_router
from routes.copilot import router as copilot_router
from routes.dashboard import router as dashboard_router
from routes.reports import router as reports_router
from routes.reviews import router as reviews_router
from routes.semantic import router as semantic_router

# ─── Middleware ───────────────────────────────────────────────────────────────
from middleware import (
    RateLimiterMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SafeSense AI API",
    description=(
        "AI-powered industrial safety intelligence platform API "
        "with hybrid deterministic safety logic and PostgreSQL/pgvector advisory architecture."
    ),
    version="1.2.0",
    docs_url=None if settings.is_production and os.getenv("DISABLE_SWAGGER_IN_PROD", "false").lower() == "true" else "/api/docs",
    redoc_url=None if settings.is_production and os.getenv("DISABLE_SWAGGER_IN_PROD", "false").lower() == "true" else "/api/redoc",
)

# Add Middleware in processing order (LIFO execution)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimiterMiddleware)
app.add_middleware(RequestIDMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global safe error handler preventing stack trace and query leakage in production.
    """
    req_id = getattr(request.state, "request_id", "unknown")
    logger.error(
        f"[UNHANDLED_EXCEPTION] request_id={req_id} path={request.url.path} error={str(exc)}",
        exc_info=True,
    )
    if settings.is_production:
        return JSONResponse(
            status_code=500,
            content={
                "detail": "An internal server error occurred. Please contact system administrator with your request ID.",
                "request_id": req_id,
            },
        )
    # In development/test mode, surface error details for easier debugging
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"Internal error: {str(exc)}",
            "request_id": req_id,
            "error_type": type(exc).__name__,
        },
    )


security = HTTPBearer(auto_error=False)

# ─── Mount database-backed routers ───────────────────────────────────────────
app.include_router(reports_router,   prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(actions_router,   prefix="/api")
app.include_router(reviews_router,   prefix="/api")
app.include_router(admin_router,     prefix="/api")
app.include_router(copilot_router,   prefix="/api")
app.include_router(semantic_router,  prefix="/api")

# Mount direct endpoints (without /api prefix) for direct client requests
app.include_router(reports_router)
app.include_router(dashboard_router)
app.include_router(actions_router)
app.include_router(reviews_router)
app.include_router(admin_router)
app.include_router(copilot_router)

# ─── Auth ─────────────────────────────────────────────────────────────────────
# Local demo users dictionary (used when allow_demo_auth=True)
DEMO_USERS = {
    "admin@safesense.ai":   {"password": "admin123",  "role": "Administrator",   "name": "Sam Rivera"},
    "hse@safesense.ai":     {"password": "hse123",    "role": "HSE Officer",     "name": "Alex Morgan"},
    "manager@safesense.ai": {"password": "mgr123",    "role": "Safety Manager",  "name": "Jordan Lee"},
    "site@safesense.ai":    {"password": "site123",   "role": "Site Manager",    "name": "Chris Patel"},
}


class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/auth/login", tags=["Auth"])
async def login(req: LoginRequest):
    if settings.is_production and not settings.allow_demo_auth:
        logger.warning(f"[AUTH_REJECTED] Demo authentication disabled in production for {req.email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo authentication is disabled in production environments. Please configure production identity provider.",
        )

    user = DEMO_USERS.get(req.email.lower().strip())
    if not user or not verify_password(req.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token({
        "email": req.email,
        "role": user["role"],
        "name": user["name"],
    })
    return {
        "token": token,
        "user": {
            "email": req.email,
            "name": user["name"],
            "role": user["role"],
        },
    }


# ─── Direct Upload Endpoint (with Size & Extension Hardening) ─────────────────
@app.post("/api/upload", response_model=UploadResponse, tags=["Upload"])
@app.post("/upload", response_model=UploadResponse, tags=["Upload"])
async def direct_upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    filename = file.filename or "upload.csv"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in settings.allowed_upload_extensions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File extension '{ext}' is not supported. Upload a .csv, .xlsx, or .xls file.",
        )

    raw_bytes = await file.read()
    if len(raw_bytes) == 0:
        raise HTTPException(status_code=422, detail="Uploaded file is empty (0 bytes).")

    if len(raw_bytes) > settings.max_upload_size_bytes:
        max_mb = settings.max_upload_size_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum allowed upload limit ({max_mb} MB).",
        )

    try:
        result = process_csv_upload(db=db, file_bytes=raw_bytes, filename=filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return UploadResponse(
        inserted=result.inserted,
        duplicates=result.duplicates,
        total=result.total,
        filename=result.filename,
        total_rows=result.total_rows,
        processed=result.processed,
        duplicates_skipped=result.duplicates_skipped,
        file_duplicate=result.file_duplicate,
        message=result.message,
        skipped=result.skipped,
        skipped_reasons=result.skipped_reasons,
        sample=result.sample,
        risk_summary=result.risk_summary,
        sif_count=result.sif_count,
        pii_detected_count=result.pii_detected_count,
        pii_total_redacted=result.pii_total_redacted,
        description_column=result.description_column,
    )


# ─── Analyze single report (rule engine) ─────────────────────────────────────
class AnalyzeRequest(BaseModel):
    report_text:      Optional[str] = None
    description:      Optional[str] = None
    activity:         Optional[str] = None
    severity:         Optional[str] = None
    report_type:      Optional[str] = None
    life_saving_rule: Optional[str] = None
    barrier_failure:  Optional[str] = None


@app.post("/api/analyze-report", tags=["Analysis"])
async def analyze_single_report(req: AnalyzeRequest):
    data = req.dict()
    if not data.get("report_text") and data.get("description"):
        data["report_text"] = data["description"]
    raw_text = (data.get("report_text") or "").strip()
    if not raw_text or len(raw_text) < 10:
        raise HTTPException(status_code=400, detail="Please provide a detailed safety observation.")

    # ── PII Preprocessing BEFORE NLP / Risk Engine ──
    from services.pii_service import redact_pii
    pii_res = redact_pii(raw_text)
    data["report_text"] = pii_res.redacted_text
    data["description"] = pii_res.redacted_text

    result = analyze_report(data)
    result["pii_detected"] = pii_res.pii_detected
    result["pii_count"] = pii_res.pii_count
    result["pii_types"] = pii_res.pii_types
    result["redacted_text"] = pii_res.redacted_text
    return result


# ─── Multilingual endpoints ──────────────────────────────────────────────────
class DetectLanguageRequest(BaseModel):
    text:          str
    hint_language: Optional[str] = None


@app.post("/api/detect-language", tags=["Multilingual"])
async def detect_language(req: DetectLanguageRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")
    result = process_report(req.text, req.hint_language)
    return {
        "detected_language":      result["detected_language"],
        "detected_language_name": result["detected_language_name"],
        "original_text":          req.text,
    }


class TranslateRequest(BaseModel):
    text:             str
    source_language:  Optional[str] = None
    preserve_original: bool = True


@app.post("/api/translate", tags=["Multilingual"])
async def translate_report(req: TranslateRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")
    result   = process_report(req.text, req.source_language)
    analysis = analyze_report({"report_text": result["translated_report_text"]})
    return {**result, **analysis}


class MultilingualDatasetRequest(BaseModel):
    rows:     List[Dict[str, Any]]
    text_col: str = "report_text"
    lang_col: Optional[str] = None


@app.post("/api/multilingual/process-dataset", tags=["Multilingual"])
async def process_multilingual_dataset(req: MultilingualDatasetRequest):
    if not req.rows:
        raise HTTPException(status_code=400, detail="rows list is required")
    if len(req.rows) > 5000:
        raise HTTPException(status_code=400, detail="Maximum 5000 rows per request")
    enriched_rows, stats = process_dataset(req.rows, req.text_col, req.lang_col)
    return {
        "enriched_rows": enriched_rows,
        "stats":         stats,
        "message": (
            f"Processed {stats['total']} reports: "
            f"{stats['english']} English, "
            f"{stats['kannada']} Kannada, "
            f"{stats['hindi']} Hindi, "
            f"{stats['translated']} translated."
        ),
    }


# ─── Health & Readiness Probes (Phase 7) ──────────────────────────────────────
@app.get("/api/health", tags=["Health"])
@app.get("/health", tags=["Health"])
async def health():
    """
    Liveness probe: verifies that the FastAPI web service is responsive.
    """
    return {
        "status": "ok",
        "service": "SafeSense AI API",
        "version": "1.2.0",
        "environment": settings.environment,
        "database_backend": "sqlite" if IS_SQLITE else "postgresql",
        "features": ["risk-analysis", "multilingual-en-kn-hi", "pattern-intelligence", "vector-advisory"],
    }


@app.get("/api/ready", tags=["Health"])
@app.get("/ready", tags=["Health"])
async def readiness(db: Session = Depends(get_db)):
    """
    Readiness probe: validates database connectivity, schema state, and vector subsystem.
    Returns HTTP 200 when ready to accept traffic, or HTTP 503 if dependencies fail.
    """
    db_alive = ping_database()
    if not db_alive:
        logger.error("[READINESS_FAILED] Database ping returned failure.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unready: database connection failed.",
        )

    # Check schema / alembic revision if postgres
    alembic_version = None
    if not IS_SQLITE:
        try:
            alembic_version = db.execute(text("SELECT version_num FROM alembic_version;")).scalar()
        except Exception as exc:
            logger.warning(f"[READINESS_WARNING] Could not read alembic_version: {exc}")
            alembic_version = "uninitialized"

    from services.embedding_provider import get_provider_info
    from services.vector_store import get_backend_info

    return {
        "status": "ready",
        "environment": settings.environment,
        "database": {
            "connected": True,
            "backend": "sqlite" if IS_SQLITE else "postgresql",
            "alembic_version": alembic_version,
        },
        "vector_store": get_backend_info(),
        "embedding_provider": get_provider_info(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
