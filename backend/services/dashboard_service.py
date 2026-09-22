"""
services/dashboard_service.py — Backwards-compatibility wrapper delegating to analytics_service.py.

All analytics queries and metrics are unified in services/analytics_service.py (single source of truth).
"""
from services.analytics_service import (
    DashboardData,
    get_total_reports,
    get_risk_distribution,
    get_sif_count,
    get_monthly_trends,
    get_category_patterns as get_patterns_data,
    get_site_stats as get_sites_data,
    get_activity_stats as get_activities_data,
    get_dashboard_data,
    get_command_center_data,
    get_debug_counts,
    refresh_analytics_cache,
)

__all__ = [
    "DashboardData",
    "get_total_reports",
    "get_risk_distribution",
    "get_sif_count",
    "get_monthly_trends",
    "get_patterns_data",
    "get_sites_data",
    "get_activities_data",
    "get_dashboard_data",
    "get_command_center_data",
    "get_debug_counts",
    "refresh_analytics_cache",
]
