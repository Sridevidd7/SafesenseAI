"""
SafeSense AI — FastAPI Backend
================================
Unified backend using SQLite (safety.db) as single source of truth for all safety intelligence.
"""
import io
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

# ─── Database bootstrap ───────────────────────────────────────────────────────
from database import engine, Base, get_db
import models  # registers ORM models with Base metadata

# Create all tables on startup (no-op if they already exist)
Base.metadata.create_all(bind=engine)

# ─── Service imports ──────────────────────────────────────────────────────────
from services.risk_engine   import analyze_report, calculate_risk_score, compute_patterns, compute_site_risk
from services.auth          import create_access_token, verify_token
from services.report_generator import generate_summary_report
from services.multilingual  import process_report, process_dataset, LANG_DISPLAY
from services.upload_service import process_csv_upload
from schemas import UploadResponse

# ─── Routers ──────────────────────────────────────────────────────────────────
from routes.reports   import router as reports_router
from routes.dashboard import router as dashboard_router
from routes.actions   import router as actions_router
from routes.reviews   import router as reviews_router
from routes.admin     import router as admin_router
from routes.copilot   import router as copilot_router

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SafeSense AI API",
    description=(
        "AI-powered industrial safety intelligence platform API "
        "with multilingual support (EN/KN/HI) and unified SQLite persistence."
    ),
    version="1.2.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

_allowed_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=False)

# ─── Mount database-backed routers ───────────────────────────────────────────
app.include_router(reports_router,   prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(actions_router,   prefix="/api")
app.include_router(reviews_router,   prefix="/api")
app.include_router(admin_router,     prefix="/api")
app.include_router(copilot_router,   prefix="/api")

# Mount direct endpoints (without /api prefix) for direct client requests
app.include_router(reports_router)
app.include_router(dashboard_router)
app.include_router(actions_router)
app.include_router(reviews_router)
app.include_router(admin_router)
app.include_router(copilot_router)

# ─── Auth ─────────────────────────────────────────────────────────────────────
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
    user = DEMO_USERS.get(req.email)
    if not user or user["password"] != req.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"email": req.email, "role": user["role"]})
    return {"token": token, "user": {"email": req.email, "name": user["name"], "role": user["role"]}}


# ─── Legacy Upload Alias (delegates directly to database-backed upload) ──────
@app.post("/api/upload", response_model=UploadResponse, tags=["Upload"])
@app.post("/upload", response_model=UploadResponse, tags=["Upload"])
async def direct_upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    raw_bytes = await file.read()
    if len(raw_bytes) == 0:
        raise HTTPException(status_code=422, detail="Uploaded file is empty (0 bytes).")
    try:
        result = process_csv_upload(db=db, file_bytes=raw_bytes, filename=file.filename or "upload.csv")
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


# ─── Health check ─────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["Health"])
@app.get("/health", tags=["Health"])
async def health():
    return {
        "status":   "ok",
        "service":  "SafeSense AI API",
        "version":  "1.2.0",
        "database": "SQLite (safety.db)",
        "features": ["risk-analysis", "multilingual-en-kn-hi", "sqlite-persistence"],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
