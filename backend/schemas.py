"""
schemas.py — Pydantic v2 schemas for request validation and response serialization.

Separation of concerns:
  ReportCreate   → validates incoming POST body
  ReportResponse → shapes the API response (never exposes ORM internals)
"""
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


# ─── Request schemas ──────────────────────────────────────────────────────────

class ReportCreate(BaseModel):
    """
    Body expected by POST /reports.
    Only description is required from the caller —
    category and risk_score are computed by the service layer.
    """
    description: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Full text of the safety observation (10–5000 characters)",
        examples=["Worker entered confined space without completing gas testing."],
    )


# ─── Response schemas ─────────────────────────────────────────────────────────

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
    site:          str = "Site Alpha"
    activity:      str = "General Operation"
    date:          str | None = None
    created_at:    datetime | None = None

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


# ─── CSV Upload schemas ───────────────────────────────────────────────────────

class ProcessedRowSchema(BaseModel):
    """One row from the CSV upload, after analysis and DB save."""
    row_index:     int    = Field(description="1-based row number in the original file (including header)")
    saved_id:      str    = Field(description="Primary key assigned in the database")
    report_id:     str    = Field(default="", description="Unique identifier for report")
    description:   str
    category:      str    = Field(description="Life-Saving Rule category detected")
    risk_score:    int    = Field(description="Risk score 0–100")
    risk_level:    str    = Field(description="LOW | MEDIUM | HIGH | CRITICAL")
    sif_potential: str    = Field(description="YES | NO")
    site:          str    = Field(default="Site Alpha", description="Facility or site name")
    activity:      str    = Field(default="General Operation", description="Activity or task name")
    date:          str | None = None


# ─── Analytics & Pattern schemas ──────────────────────────────────────────────

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
    description_column: str  = Field(default="", description="Column name used as 'description'")


# ─── Dashboard schemas ────────────────────────────────────────────────────────

class DashboardResponse(BaseModel):
    """
    Returned by GET /api/dashboard/stats and /api/dashboard/summary.
    All values are computed live from the reports table — no hardcoded data.
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


# ─── Risk Intelligence Trends schema ─────────────────────────────────────────

class TrendPoint(BaseModel):
    """
    Monthly trend data point for Risk Intelligence chart.
    """
    month:    str = Field(description="Month in YYYY-MM format")
    total:    int = Field(description="Total safety reports in this month")
    sif:      int = Field(description="SIF potential reports in this month")
    critical: int = Field(description="Critical severity reports in this month")


# ─── Corrective Action schemas ────────────────────────────────────────────────

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


# ─── Human Review (HITL) schemas ──────────────────────────────────────────────

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

