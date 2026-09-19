"""
routes/dashboard.py — Database-backed dashboard & analytics endpoints.

Endpoints:
- GET /api/dashboard/stats
- GET /api/dashboard/summary
- GET /api/risk-intelligence/trends
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from schemas import (
    DashboardResponse,
    TrendPoint,
    PatternItem,
    SiteRiskItem,
    ActivityRiskItem,
    CommandCenterResponse,
    DebugCountResponse,
)
import services.dashboard_service as dash_svc

router = APIRouter(
    tags=["Dashboard & Intelligence"],
)



@router.get(
    "/dashboard/stats",
    response_model=DashboardResponse,
    summary="Live dashboard metrics from the database",
)
@router.get(
    "/dashboard/summary",
    response_model=DashboardResponse,
    summary="Live dashboard summary from the database",
)
def get_dashboard_stats(
    db: Session = Depends(get_db),
) -> DashboardResponse:
    data = dash_svc.get_dashboard_data(db)
    return DashboardResponse(
        total_reports         = data.total_reports,
        sif_count             = data.sif_count,
        non_sif_count         = data.non_sif_count,
        critical_count        = data.critical_count,
        high_risk_count       = data.high_risk_count,
        sif_percentage        = data.sif_percentage,
        risk_distribution     = data.risk_distribution,
        category_distribution = data.category_distribution,
        avg_risk_score        = data.avg_risk_score,
        top_category          = data.top_category,
        top_risk_level        = data.top_risk_level,
    )


@router.get(
    "/risk-intelligence/trends",
    response_model=list[TrendPoint],
    summary="Monthly risk and safety trend series",
)
@router.get(
    "/risk-intelligence",
    response_model=list[TrendPoint],
    summary="Monthly risk intelligence trends",
)
def get_risk_trends(
    db: Session = Depends(get_db),
) -> list[TrendPoint]:
    trends = dash_svc.get_monthly_trends(db)
    return [TrendPoint(**t) for t in trends]


@router.get(
    "/analytics/patterns",
    response_model=list[dash_svc.PatternItem] if hasattr(dash_svc, "PatternItem") else list,
    summary="Recurring safety pattern clusters grouped by category",
)
@router.get(
    "/patterns",
    summary="Safety patterns endpoint",
)
def get_patterns(
    db: Session = Depends(get_db),
):
    return dash_svc.get_patterns_data(db)


@router.get(
    "/analytics/sites",
    summary="Site risk rankings and metrics",
)
@router.get(
    "/sites",
    summary="Site risk rankings endpoint",
)
def get_sites(
    db: Session = Depends(get_db),
):
    return dash_svc.get_sites_data(db)


@router.get(
    "/analytics/activities",
    summary="Activity risk rankings and metrics",
)
@router.get(
    "/activities",
    summary="Activity risk rankings endpoint",
)
def get_activities(
    db: Session = Depends(get_db),
):
    return dash_svc.get_activities_data(db)


@router.get(
    "/analytics/command-center",
    summary="Executive KPI metrics and high priority reports for Command Center",
)
@router.get(
    "/command-center",
    summary="Command Center overview endpoint",
)
def get_command_center(
    db: Session = Depends(get_db),
):
    return dash_svc.get_command_center_data(db)


@router.get(
    "/debug/count",
    summary="Data integrity debug counts",
)
def get_debug_count(
    db: Session = Depends(get_db),
):
    return dash_svc.get_debug_counts(db)

