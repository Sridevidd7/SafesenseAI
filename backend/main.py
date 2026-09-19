"""
SafeSense AI — FastAPI Backend
================================
Endpoints
---------
Legacy (unchanged from original):
  POST /api/auth/login
  POST /api/upload
  POST /api/analyze-report
  GET  /api/dashboard
  POST /api/patterns
  POST /api/sites
  POST /api/actions
  GET  /api/actions
  POST /api/review
  POST /api/copilot/query
  POST /api/detect-language
  POST /api/translate
  POST /api/multilingual/process-dataset
  GET  /api/health

New (database-backed):
  POST /api/reports        → create + persist a report
  GET  /api/reports        → list all persisted reports
  GET  /api/reports/{id}   → single report by id
"""
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import pandas as pd
import io
import os
from datetime import datetime

# ─── Database bootstrap ───────────────────────────────────────────────────────
from database import engine, Base
import models  # registers ORM models with Base metadata

# Create all tables on startup (no-op if they already exist)
Base.metadata.create_all(bind=engine)

# ─── Legacy service imports ───────────────────────────────────────────────────
from services.risk_engine   import analyze_report, calculate_risk_score, compute_patterns, compute_site_risk
from services.auth          import create_access_token, verify_token
from services.report_generator import generate_summary_report
from services.multilingual  import process_report, process_dataset, LANG_DISPLAY

# ─── New routers ──────────────────────────────────────────────────────────────
from routes.reports   import router as reports_router
from routes.dashboard import router as dashboard_router
from routes.actions   import router as actions_router
from routes.reviews   import router as reviews_router
from routes.admin     import router as admin_router

# ─── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SafeSense AI API",
    description=(
        "AI-powered industrial safety intelligence platform API "
        "with multilingual support (EN/KN/HI) and SQLite persistence."
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

# Mount direct endpoints for /reports, /dashboard, /admin, /risk-intelligence
app.include_router(reports_router)
app.include_router(dashboard_router)
app.include_router(actions_router)
app.include_router(reviews_router)
app.include_router(admin_router)

# ─── In-memory legacy storage (kept for backward compat) ─────────────────────
_datasets: Dict[str, Any] = {}
_actions:  List[Dict]     = []
_reviews:  List[Dict]     = []

# ─── Legacy: Auth ─────────────────────────────────────────────────────────────
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


# ─── Legacy: Upload ───────────────────────────────────────────────────────────
@app.post("/api/upload", tags=["Upload"])
async def upload_file(file: UploadFile = File(...)):
    content = await file.read()
    try:
        if file.filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        elif file.filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(content))
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")

    rows      = df.fillna("").to_dict(orient="records")
    columns   = list(df.columns)
    dataset_id = f"ds_{int(datetime.now().timestamp())}"
    _datasets[dataset_id] = {"rows": rows, "columns": columns, "filename": file.filename}

    return {
        "dataset_id": dataset_id,
        "filename":   file.filename,
        "rows":       len(rows),
        "columns":    columns,
        "preview":    rows[:10],
    }


# ─── Legacy: Analyze single report (rule engine, no DB) ──────────────────────
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
    if not data.get("report_text"):
        raise HTTPException(status_code=400, detail="Either report_text or description must be provided")
    result = analyze_report(data)
    return result


# ─── Legacy: Dashboard ────────────────────────────────────────────────────────
@app.get("/api/dashboard", tags=["Dashboard"])
async def get_dashboard():
    return {"message": "Dashboard data computed client-side from uploaded dataset."}


# ─── Legacy: Patterns ─────────────────────────────────────────────────────────
class PatternRequest(BaseModel):
    reports: List[Dict[str, Any]]

@app.post("/api/patterns", tags=["Analysis"])
async def get_patterns(req: PatternRequest):
    return {"patterns": compute_patterns(req.reports)}


# ─── Legacy: Sites ────────────────────────────────────────────────────────────
@app.post("/api/sites", tags=["Analysis"])
async def get_site_risk(req: PatternRequest):
    return {"sites": compute_site_risk(req.reports)}


# ─── Legacy: Copilot ─────────────────────────────────────────────────────────
class CopilotRequest(BaseModel):
    query:   str
    reports: Optional[List[Dict[str, Any]]] = None

@app.post("/api/copilot/query", tags=["Copilot"])
async def copilot_query(req: CopilotRequest):
    return {
        "response":       "Query processed client-side.",
        "source_reports": [],
    }


# ─── Legacy: Multilingual ────────────────────────────────────────────────────
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
