"""
routes/dashboard.py — Database-backed dashboard & analytics endpoints.

Single Source of Truth: All endpoints query services/analytics_service.py directly.

Endpoints:
- GET  /api/dashboard/stats
- GET  /api/dashboard/summary
- GET  /api/risk-intelligence/trends
- GET  /api/analytics/patterns
- GET  /api/analytics/sites
- GET  /api/analytics/activities
- GET  /api/analytics/command-center
- POST /api/refresh-analytics
- GET  /api/debug/count
"""
from datetime import datetime, timezone
from typing import Any
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
    MetaInfo,
)
import services.analytics_service as analytics_svc

router = APIRouter(
    tags=["Dashboard & Intelligence"],
)


def _build_meta(total_reports: int) -> dict[str, Any]:
    return {
        "total_reports": total_reports,
        "last_updated":  datetime.now(timezone.utc).isoformat(),
        "source":        "db",
    }


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
    data = analytics_svc.get_dashboard_data(db)
    meta = _build_meta(data.total_reports)
    raw_dict = {
        "total_reports":         data.total_reports,
        "sif_count":             data.sif_count,
        "non_sif_count":         data.non_sif_count,
        "critical_count":        data.critical_count,
        "high_risk_count":       data.high_risk_count,
        "sif_percentage":        data.sif_percentage,
        "risk_distribution":     data.risk_distribution,
        "category_distribution": data.category_distribution,
        "avg_risk_score":        data.avg_risk_score,
        "top_category":          data.top_category,
        "top_risk_level":        data.top_risk_level,
    }
    return DashboardResponse(
        **raw_dict,
        data=raw_dict,
        meta=MetaInfo(**meta),
    )


@router.get(
    "/risk-intelligence/trends",
    summary="Monthly risk and safety trend series with trend direction and anomaly insights",
)
@router.get(
    "/risk-intelligence",
    summary="Monthly risk intelligence trends",
)
def get_risk_trends(
    db: Session = Depends(get_db),
):
    total = analytics_svc.get_total_reports(db)
    intel = analytics_svc.get_pattern_intelligence(db)
    trends = analytics_svc.get_monthly_trends(db)
    meta = _build_meta(total)
    return {
        "data":          trends,
        "trend":         intel["trend_summary"]["trend"],
        "trend_reason":  intel["trend_summary"]["reason"],
        "anomalies":     intel["anomalies"],
        "insights":      intel["insights"],
        "meta":          meta,
    }


@router.get(
    "/analytics/patterns",
    summary="Recurring safety pattern clusters grouped by similarity clustering",
)
@router.get(
    "/patterns",
    summary="Safety patterns endpoint",
)
def get_patterns(
    db: Session = Depends(get_db),
):
    total = analytics_svc.get_total_reports(db)
    intel = analytics_svc.get_pattern_intelligence(db)
    return {
        "data":              intel["clusters"],
        "repeated_failures": intel["repeated_failures"],
        "insights":          intel["insights"],
        "meta":              _build_meta(total),
    }


@router.get(
    "/analytics/insights",
    summary="AI safety intelligence insights across patterns, anomalies, and trends",
)
@router.get(
    "/insights",
    summary="AI safety intelligence insights endpoint",
)
def get_insights(
    db: Session = Depends(get_db),
):
    total = analytics_svc.get_total_reports(db)
    insights = analytics_svc.get_all_insights(db)
    return {
        "data": insights,
        "meta": _build_meta(total),
    }


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
    total = analytics_svc.get_total_reports(db)
    sites = analytics_svc.get_site_stats(db)
    return {
        "data": sites,
        "meta": _build_meta(total),
    }


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
    total = analytics_svc.get_total_reports(db)
    activities = analytics_svc.get_activity_stats(db)
    return {
        "data": activities,
        "meta": _build_meta(total),
    }


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
    cc_data = analytics_svc.get_command_center_data(db)
    return {
        "data": cc_data,
        "meta": _build_meta(cc_data.get("total_reports", 0)),
        **cc_data,  # backward compatibility for direct field access
    }


@router.post(
    "/refresh-analytics",
    summary="Force refresh analytics cache and recompute aggregations",
)
def refresh_analytics(
    db: Session = Depends(get_db),
):
    """
    Clears cache, recomputes all metric aggregations across reports, and returns fresh state.
    """
    result = analytics_svc.refresh_analytics_cache(db)
    return {
        "data": result,
        "meta": _build_meta(result["total_reports"]),
        **result,
    }


@router.get(
    "/debug/count",
    summary="Data integrity debug counts",
)
def get_debug_count(
    db: Session = Depends(get_db),
):
    counts = analytics_svc.get_debug_counts(db)
    return {
        "data": counts,
        "meta": _build_meta(counts.get("total_reports", 0)),
        **counts,
    }


@router.get(
    "/analytics/sif-heatmap",
    summary="Operational SIF Risk Heatmap & Concentration Explorer",
    description=(
        "Hierarchical operational risk concentration view across: "
        "Site -> Unit -> Area -> Activity -> LSR/Precursor -> Failed Barrier."
    ),
)
@router.get(
    "/sif-heatmap",
    summary="Operational SIF Risk Heatmap (direct alias)",
)
def get_sif_heatmap(
    site: str | None = None,
    unit: str | None = None,
    area: str | None = None,
    activity: str | None = None,
    lsr: str | None = None,
    barrier: str | None = None,
    db: Session = Depends(get_db),
):
    heatmap_data = analytics_svc.get_sif_risk_heatmap(
        db=db,
        site=site,
        unit=unit,
        area=area,
        activity=activity,
        lsr=lsr,
        barrier=barrier,
    )
    total = heatmap_data["summary"]["total_reports"]
    return {
        "data": heatmap_data,
        "meta": _build_meta(total),
        **heatmap_data,
    }
