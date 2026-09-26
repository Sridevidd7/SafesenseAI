"""
schemas.py â€” Pydantic v2 schemas for request validation and response serialization.

Separation of concerns:
  ReportCreate   â†’ validates incoming POST body
  ReportResponse â†’ shapes the API response (never exposes ORM internals)
"""
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, ConfigDict


# â”€â”€â”€ Request schemas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ReportCreate(BaseModel):
    """
    Body expected by POST /reports.
    Only description is required from the caller â€”
    category and risk_score are computed by the service layer.
    """
    description: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Full text of the safety observation (10â€“5000 characters)",
        examples=["Worker entered confined space without completing gas testing."],
    )


# â”€â”€â”€ Metadata & Response Envelope schemas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class MetaInfo(BaseModel):
    total_reports: int = 0
    last_updated:  str = ""
    source:        str = "db"


class GenericResponse(BaseModel):
    data: Any
    meta: MetaInfo


# â”€â”€â”€ Response schemas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ReportResponse(BaseModel):
    """
    Shape returned by POST /reports and items in GET /reports.
    model_config from_attributes=True lets Pydantic read SQLAlchemy ORM objects.
    """
    model_config = ConfigDict(from_attributes=True)

    report_id:     str
    id:            str | None = None
    description:   str
    category:      str
    risk_score:    int
    sif_potential: str
    risk_level:    str
    risk_reason:   str | None = None
    site:          str = "Site Alpha"
    unit:          str = "Not Specified"
    area:          str = "Not Specified"
    activity:      str = "General Operation"
    barrier_failure: str = "Unspecified"
    pii_detected:  bool = False
    pii_count:     int = 0
    pii_types:     str = ""
    date:          str | None = None
    created_at:    datetime | None = None
    data:          dict[str, Any] | None = None
    meta:          MetaInfo | None = None

    def __init__(self, **data):
        if "id" not in data or data["id"] is None:
            if "report_id" in data:
                data["id"] = str(data["report_id"])
        if "report_id" not in data or data["report_id"] is None:
            if "id" in data:
                data["report_id"] = str(data["id"])
        super().__init__(**data)


class ReportListResponse(BaseModel):
    """Wrapper for the GET /reports list endpoint."""
    total:   int
    reports: list[ReportResponse]
    data:    list[ReportResponse] | None = None
    meta:    MetaInfo | None = None


# â”€â”€â”€ CSV Upload schemas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ProcessedRowSchema(BaseModel):
    """One row from the CSV upload, after analysis and DB save."""
    row_index:     int    = Field(description="1-based row number in the original file (including header)")
    saved_id:      str    = Field(description="Primary key assigned in the database")
    report_id:     str    = Field(default="", description="Unique identifier for report")
    description:   str
    category:      str    = Field(description="Life-Saving Rule category detected")
    risk_score:    int    = Field(description="Risk score 0â€“100")
    risk_level:    str    = Field(description="LOW | MEDIUM | HIGH | CRITICAL")
    risk_reason:   str | None = Field(default=None, description="Short explanation of WHY score is high/low")
    sif_potential: str    = Field(description="YES | NO")
    site:          str    = Field(default="Site Alpha", description="Facility or site name")
    unit:          str    = Field(default="Not Specified", description="Unit or operating plant")
    area:          str    = Field(default="Not Specified", description="Area or specific zone")
    activity:      str    = Field(default="General Operation", description="Activity or task name")
    barrier_failure: str  = Field(default="Unspecified", description="Barrier failure identified")
    pii_detected:  bool   = Field(default=False, description="Whether PII was detected and redacted")
    pii_count:     int    = Field(default=0, description="Count of PII identifiers redacted")
    pii_types:     str    = Field(default="", description="Comma-separated PII identifier categories")
    date:          str | None = None


# â”€â”€â”€ Analytics & Pattern schemas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class PatternItem(BaseModel):
    category:     str
    count:        int
    name:         str = ""
    description:  str = ""
    frequency:    int = 0
    risk_level:   str = "MEDIUM"
    sites:        list[str] = Field(default_factory=list)
    trend:        str = "stable"


class SiteRiskItem(BaseModel):
    site:                 str
    total:                int
    critical:             int
    sif:                  int = 0
    risk_score:           int = 0
    risk_level:           str = "LOW"
    top_precursor:        str = "General Observation"
    top_barrier_failure:  str = "Unspecified"


class ActivityRiskItem(BaseModel):
    activity:             str
    total:                int
    critical:             int = 0
    sif:                  int = 0
    risk_score:           int = 0
    risk_level:           str = "LOW"
    top_barrier_failure:  str = "Unspecified"


class CommandCenterResponse(BaseModel):
    total_reports:         int
    critical_alerts:       int
    sif_potential:         int
    high_risk_sites:       int
    rising_precursors:     int
    open_actions:          int
    early_warnings_count:  int
    high_priority_reports: list[ReportResponse]


class DebugCountResponse(BaseModel):
    total_reports: int
    with_category: int
    with_site:     int
    with_activity: int


# â”€â”€â”€ SIF Risk Concentration Heatmap schemas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class SifHeatmapNode(BaseModel):
    id:                 str
    name:               str
    level:              str   # 'site' | 'unit' | 'area' | 'activity' | 'lsr' | 'barrier'
    total_reports:      int = 0
    sif_count:          int = 0
    precursor_density:  float = 0.0
    risk_level:         str = "LOW"  # HIGH | EMERGING | MEDIUM | LOW
    avg_risk_score:     float = 0.0
    trend_pct:          float | None = None
    trend_label:        str = "Insufficient data"
    top_barrier:        str = "Unspecified"
    is_fallback:        bool = False
    report_ids:         list[str] = Field(default_factory=list)
    children:           list["SifHeatmapNode"] = Field(default_factory=list)


class SifHeatmapSummary(BaseModel):
    total_reports:            int = 0
    total_precursors:         int = 0
    overall_density:          float = 0.0
    high_risk_concentrations: int = 0
    emerging_concentrations:  int = 0
    top_concentration:        str = "None detected"


class SifHeatmapResponse(BaseModel):
    summary:    SifHeatmapSummary
    tree:       list[SifHeatmapNode]
    reports:    list[ReportResponse] = Field(default_factory=list)
    meta:       MetaInfo | None = None


class UploadResponse(BaseModel):
    """
    Returned by POST /api/reports/upload after processing a full CSV file.
    """
    inserted:           int  = Field(default=0, description="New records inserted into the database")
    duplicates:         int  = Field(default=0, description="Duplicate rows skipped during ingestion")
    total:              int  = Field(default=0, description="Total rows in the uploaded file (excluding header)")
    filename:           str  = ""
    total_rows:         int  = Field(default=0, description="Total data rows in the uploaded file")
    processed:          int  = Field(default=0, description="Rows processed")
    duplicates_skipped: int  = Field(default=0, description="Duplicate rows skipped during ingestion")
    file_duplicate:     bool = Field(default=False, description="Whether the entire file was skipped as duplicate")
    message:            str  = Field(default="Upload processed successfully", description="Status message")
    skipped:            int  = Field(default=0, description="Rows skipped due to empty or too-short description")
    skipped_reasons:    list[str] = Field(default_factory=list, description="Up to 20 skip reason messages")
    sample:             list[dict] = Field(default_factory=list, description="First 5 processed rows")
    risk_summary:       dict[str, int] = Field(default_factory=dict, description="Count per risk level")
    sif_count:          int  = Field(default=0, description="Number of rows classified as SIF potential YES")
    pii_detected_count: int  = Field(default=0, description="Number of uploaded rows with PII redacted")
    pii_total_redacted: int  = Field(default=0, description="Total number of PII items sanitized")
    description_column: str  = Field(default="", description="Column name used as 'description'")


# â”€â”€â”€ Dashboard schemas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class DashboardResponse(BaseModel):
    """
    Returned by GET /api/dashboard/stats and /api/dashboard/summary.
    All values are computed live from the reports table â€” no hardcoded data.
    """
    total_reports:         int   = Field(description="Total rows in the reports table")
    sif_count:             int   = Field(description="Reports classified as SIF potential YES")
    non_sif_count:         int   = Field(description="Reports classified as SIF potential NO")
    critical_count:        int   = Field(default=0, description="Reports classified as CRITICAL")
    high_risk_count:       int   = Field(default=0, description="Reports classified as HIGH")
    sif_percentage:        float = Field(description="sif_count / total_reports * 100")
    risk_distribution:     dict[str, int] = Field(
        description="Count per risk level. Keys: CRITICAL, HIGH, MEDIUM, LOW"
    )
    category_distribution: dict[str, int] = Field(
        description="Count per Life-Saving Rule category, sorted by count descending"
    )
    avg_risk_score:        float = Field(description="Arithmetic mean of all risk_score values")
    top_category:          str   = Field(description="Category with the most reports")
    top_risk_level:        str   = Field(description="Risk level with the most reports")
    data:                  dict[str, Any] | None = Field(default=None, description="Enveloped data dictionary")
    meta:                  MetaInfo | None = Field(default=None, description="Metadata with total count, source, timestamp")


# â”€â”€â”€ Risk Intelligence Trends schema â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TrendPoint(BaseModel):
    """
    Monthly trend data point for Risk Intelligence chart.
    """
    month:    str = Field(description="Month in YYYY-MM format")
    total:    int = Field(description="Total safety reports in this month")
    sif:      int = Field(description="SIF potential reports in this month")
    critical: int = Field(description="Critical severity reports in this month")


# â”€â”€â”€ Corrective Action schemas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ActionCreate(BaseModel):
    """
    Body expected by POST /api/actions.
    """
    report_id:   str | None = Field(None, description="Optional ID of associated safety report")
    description: str        = Field(..., min_length=3, description="Action description / mitigation plan")
    owner:       str        = Field(..., min_length=1, max_length=100, description="Responsible person or team")
    status:      str        = Field("OPEN", description="OPEN | IN_PROGRESS | COMPLETED")
    deadline:    str | None = Field(None, description="Due date (e.g. YYYY-MM-DD)")


class ActionUpdate(BaseModel):
    """
    Body expected by PATCH /api/actions/{id}. All fields optional.
    """
    report_id:   str | None = None
    description: str | None = Field(None, min_length=3)
    owner:       str | None = Field(None, min_length=1, max_length=100)
    status:      str | None = None
    deadline:    str | None = None


class ActionResponse(BaseModel):
    """
    Shape returned by action endpoints.
    """
    model_config = ConfigDict(from_attributes=True)

    id:          int
    report_id:   str | None = None
    description: str
    owner:       str
    status:      str
    deadline:    str | None = None
    created_at:  datetime | None = None


# â”€â”€â”€ Human Review (HITL) schemas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ReviewCreate(BaseModel):
    """
    Body expected by POST /api/reviews.
    """
    report_id: str        = Field(..., description="ID of the safety report being reviewed")
    decision:  str        = Field(..., description="CONFIRMED | CORRECTED | REJECTED")
    comment:   str | None = Field(None, description="Reviewer notes or corrective justification")
    reviewer:  str        = Field("HSE Officer", min_length=1, max_length=100, description="Name or role of reviewer")


class ReviewResponse(BaseModel):
    """
    Shape returned by review endpoints.
    """
    model_config = ConfigDict(from_attributes=True)

    id:         int
    report_id:  str
    decision:   str
    comment:    str | None = None
    reviewer:   str
    created_at: datetime


# â”€â”€â”€ Copilot schemas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class CopilotHistoryMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message text")


class CopilotChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="User's natural language question")
    history: list[CopilotHistoryMessage] | None = Field(default=None, description="Optional conversation history")


class CopilotAggregate(BaseModel):
    """A single deterministic database aggregate backing the answer."""
    metric: str = Field(..., description="Aggregate name, e.g. 'sif_count' or 'barrier_frequency:Gas Testing Not Completed'")
    value: float | int | str = Field(..., description="Deterministic value returned by the retrieval layer")
    scope: str = Field("database", description="Scope the aggregate was computed over")


class CopilotPatternInfo(BaseModel):
    """Pattern intelligence result surfaced to the Copilot via the Phase 2 adapter."""
    pattern_id: str
    pattern_type: str
    description: str
    frequency: int
    trend: str | None = None
    sites: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    barriers: list[str] = Field(default_factory=list)
    evidence_report_ids: list[str] = Field(default_factory=list)
    confidence: float | None = None


class CopilotGrounding(BaseModel):
    """
    Deterministic grounding metadata attached to a Copilot answer.

    Everything in this model is computed by the retrieval layer from the SafeSense
    database — never generated by the LLM — so the UI can display the exact
    evidence behind an answer.
    """
    reports_examined: int = Field(0, description="Number of reports matching the extracted scope")
    sif_count: int = Field(0, description="SIF-potential reports within the scope")
    date_range: str | None = Field(None, description="Human-readable date range applied, if any")
    filters_applied: dict[str, str] = Field(default_factory=dict, description="Scope filters extracted and applied")
    filters_unapplied: list[str] = Field(
        default_factory=list,
        description="Requested scopes that could not be reliably applied",
    )
    aggregates: list[CopilotAggregate] = Field(
        default_factory=list,
        description="Key deterministic aggregates supporting the answer",
    )
    source_reports: list[str] = Field(
        default_factory=list,
        description="Individual report IDs retrieved as evidence",
    )
    patterns: list[CopilotPatternInfo] = Field(
        default_factory=list,
        description="Pattern intelligence results (via the Phase 2 adapter), if available",
    )
    pattern_source: str | None = Field(
        None,
        description="Provenance of pattern intelligence, e.g. 'builtin_pattern_engine' or a Phase 2 provider",
    )


class CopilotChatResponse(BaseModel):
    answer: str = Field(..., description="Grounded natural-language answer synthesized by the LLM")
    source_reports: list[str] = Field(default_factory=list, description="IDs of reports retrieved from SQLite and used as context")
    data_source: str = Field("SQLite", description="Underlying database source")
    model: str = Field(..., description="Model identifier used to generate the answer")
    grounding: CopilotGrounding | None = Field(
        default=None,
        description="Deterministic grounding metadata: scope, aggregates, filters and patterns backing the answer",
    )


# ─── Authentication schemas (Phase 8 — production auth) ─────────────────────

class RegisterRequest(BaseModel):
    """Body for POST /api/auth/register (account creation)."""
    name: str = Field(..., min_length=2, max_length=200, description="Full name")
    email: str = Field(..., max_length=255, description="Work email address")
    password: str = Field(..., min_length=8, max_length=128, description="Password (min 8 chars, letters + numbers)")
    confirm_password: str = Field(..., description="Must match password")
    organization: str | None = Field(None, max_length=200, description="Organization / company (optional)")


class LoginRequest(BaseModel):
    """Body for POST /api/auth/login."""
    email: str = Field(..., max_length=255)
    password: str = Field(..., max_length=128)


class UserResponse(BaseModel):
    """Public user shape — NEVER includes the password hash."""
    id: int
    email: str
    name: str
    role: str
    organization: str | None = None
    site: str | None = None
    is_active: bool = True


class AuthResponse(BaseModel):
    """Response for login / register: user + signed JWT."""
    token: str = Field(..., description="Bearer JWT")
    token_type: str = Field("bearer")
    expires_in_minutes: int = Field(480)
    user: UserResponse


class ForgotPasswordRequest(BaseModel):
    """Body for POST /api/auth/forgot-password."""
    email: str = Field(..., max_length=255)


class ForgotPasswordResponse(BaseModel):
    """Uniform response regardless of account existence (no account enumeration)."""
    message: str = Field(
        "If an account exists for that address, a password reset link has been sent.",
    )
    # ONLY populated when SAFESENSE_DEV_EXPOSE_RESET_TOKEN=1 AND no email
    # provider is configured (explicit local-development escape hatch).
    # Always None in production.
    dev_reset_token: str | None = None


class ResetPasswordRequest(BaseModel):
    """Body for POST /api/auth/reset-password."""
    token: str = Field(..., min_length=16, description="Reset token from the email link")
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(...)


class PlatformInfoResponse(BaseModel):
    """Non-sensitive runtime/platform metadata for UI labels."""
    database: str = Field(..., description="e.g. 'PostgreSQL' or 'SQLite (local)' — never credentials")
    vector_store: str = Field(..., description="e.g. 'pgvector' or 'Unavailable'")
    environment: str = Field(..., description="'production' | 'development' | 'local'")
    version: str = Field(...)
