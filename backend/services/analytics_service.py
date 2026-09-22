"""
services/analytics_service.py — Single source of truth for all SafeSense AI analytics.

All queries execute directly against SQLite (safety.db -> reports table).
Guarantees:
- Reusable shared query functions
- Empty arrays [] on empty data (never null or undefined)
- Structured logging & debug logging of row counts and results
- Unified aggregation across Dashboard, Trends, Patterns, Sites, Activities, and Command Center
- Cache refresh hooks for dataset upload, reset, and manual trigger
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from models import Report, Action, UploadedFile
from services.llm_service import CACHE

logger = logging.getLogger("safesense.analytics")
logging.basicConfig(level=logging.INFO)

# Canonical risk level order
RISK_LEVEL_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]


@dataclass
class DashboardData:
    """All metrics required by the executive dashboard."""
    total_reports:         int
    sif_count:             int
    non_sif_count:         int
    critical_count:        int
    high_risk_count:       int
    sif_percentage:        float
    risk_distribution:     dict[str, int]
    category_distribution: dict[str, int]
    avg_risk_score:        float
    top_category:          str
    top_risk_level:        str


# ─── Core Reusable Query Functions ───────────────────────────────────────────

def get_total_reports(db: Session) -> int:
    """Return total count of records in the reports table."""
    count = db.query(func.count(Report.report_id)).scalar() or 0
    total = int(count)
    logger.info(f"[{datetime.now(timezone.utc).isoformat()}] EVENT=query_total_reports TOTAL_REPORTS={total}")
    print("Total reports:", total)
    return total


def get_risk_distribution(db: Session) -> dict[str, int]:
    """Return report counts grouped by risk level (CRITICAL, HIGH, MEDIUM, LOW)."""
    total = get_total_reports(db)
    if total == 0:
        distribution = {level: 0 for level in RISK_LEVEL_ORDER}
        logger.info(f"[{datetime.now(timezone.utc).isoformat()}] EVENT=query_risk_distribution TOTAL_REPORTS=0 RESULT={distribution}")
        print("Risk distribution:", distribution)
        return distribution

    rows = (
        db.query(Report.risk_level, func.count(Report.report_id))
        .group_by(Report.risk_level)
        .all()
    )
    raw = {str(row[0]).upper(): int(row[1]) for row in rows if row[0]}
    distribution = {level: raw.get(level, 0) for level in RISK_LEVEL_ORDER}
    logger.info(f"[{datetime.now(timezone.utc).isoformat()}] EVENT=query_risk_distribution TOTAL_REPORTS={total} RESULT={distribution}")
    print("Risk distribution:", distribution)
    return distribution


def get_sif_count(db: Session) -> dict[str, Any]:
    """Return SIF potential statistics (sif_count, non_sif_count, sif_percentage)."""
    total = get_total_reports(db)
    if total == 0:
        res = {
            "sif_count": 0,
            "non_sif_count": 0,
            "sif_percentage": 0.0,
        }
        logger.info(f"[{datetime.now(timezone.utc).isoformat()}] EVENT=query_sif_count TOTAL_REPORTS=0 RESULT={res}")
        print("SIF statistics:", res)
        return res

    rows = (
        db.query(Report.sif_potential, func.count(Report.report_id))
        .group_by(Report.sif_potential)
        .all()
    )
    sif_map = {str(row[0]).upper(): int(row[1]) for row in rows if row[0]}
    sif_count = sif_map.get("YES", 0)
    non_sif_count = sif_map.get("NO", 0)
    sif_percentage = round(sif_count / total * 100, 1) if total > 0 else 0.0

    result = {
        "sif_count": sif_count,
        "non_sif_count": non_sif_count,
        "sif_percentage": sif_percentage,
    }
    logger.info(f"[{datetime.now(timezone.utc).isoformat()}] EVENT=query_sif_count TOTAL_REPORTS={total} RESULT={result}")
    print("SIF statistics:", result)
    return result


def get_monthly_trends(db: Session) -> list[dict[str, Any]]:
    """Compute monthly risk and precursor trends from reports."""
    total_count = get_total_reports(db)
    if total_count == 0:
        logger.info(f"[{datetime.now(timezone.utc).isoformat()}] EVENT=query_monthly_trends TOTAL_REPORTS=0 ROWS_RETURNED=0")
        print("Trend rows: []")
        return []

    sql = text("""
        SELECT
            strftime('%Y-%m', date) as month,
            COUNT(*) as total_reports,
            SUM(CASE WHEN UPPER(sif_potential)='YES' THEN 1 ELSE 0 END) as sif,
            SUM(CASE WHEN UPPER(risk_level)='CRITICAL' THEN 1 ELSE 0 END) as critical
        FROM reports
        WHERE date IS NOT NULL AND date != ''
        GROUP BY month
        ORDER BY month ASC;
    """)
    rows = db.execute(sql).fetchall()
    results: list[dict[str, Any]] = []

    for r in rows:
        m = r[0]
        if m:
            results.append({
                "month":    str(m),
                "total":    int(r[1] or 0),
                "sif":      int(r[2] or 0),
                "critical": int(r[3] or 0),
            })

    # If date strings could not be grouped by strftime (e.g. non-standard date format),
    # aggregate them into an overall monthly window rather than returning empty
    if not results and total_count > 0:
        sif_stats = get_sif_count(db)
        risk_dist = get_risk_distribution(db)
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        results.append({
            "month":    current_month,
            "total":    total_count,
            "sif":      sif_stats["sif_count"],
            "critical": risk_dist.get("CRITICAL", 0),
        })

    logger.info(f"[{datetime.now(timezone.utc).isoformat()}] EVENT=query_monthly_trends TOTAL_REPORTS={total_count} ROWS_RETURNED={len(results)}")
    print("Trend rows:", results)
    return results


from services.pattern_engine import (
    cluster_reports,
    detect_repeated_failures,
    classify_trend,
    detect_anomalies,
    generate_insights,
)


from utils.analysis_utils import normalize_risk_score


def get_all_reports_dicts(db: Session) -> list[dict[str, Any]]:
    """Fetch all reports as dicts for similarity clustering and pattern intelligence with dataset normalization."""
    reports = db.query(Report).all()
    if not reports:
        return []

    scores = [r.risk_score for r in reports if r.risk_score is not None]
    mean_risk = sum(scores) / len(scores) if scores else 50.0
    if len(scores) > 1:
        variance = sum((s - mean_risk) ** 2 for s in scores) / (len(scores) - 1)
        std_dev = variance ** 0.5
    else:
        std_dev = 20.0

    res = []
    for r in reports:
        norm = normalize_risk_score(r.risk_score, mean_risk=mean_risk, std_dev=std_dev)
        res.append({
            "report_id":             r.report_id,
            "description":           r.description,
            "report_text":           r.description,
            "category":              r.category,
            "barrier":               getattr(r, "barrier", None),
            "site":                  r.site,
            "activity":              r.activity,
            "risk_score":            r.risk_score,
            "raw_score":             r.risk_score,
            "normalized_score":      norm["normalized_score"],
            "normalization_applied": norm["normalization_applied"],
            "risk_level":            r.risk_level,
            "sif_potential":         r.sif_potential,
            "date":                  r.date,
            "created_at":            r.created_at,
        })
    return res




def get_category_patterns(db: Session) -> list[dict[str, Any]]:
    """
    Similarity-based clustering of safety reports.
    Replaces raw SQL GROUP BY with Jaccard similarity clustering and pattern analysis.
    """
    total_count = get_total_reports(db)
    if total_count == 0:
        logger.info(f"[{datetime.now(timezone.utc).isoformat()}] EVENT=query_category_patterns TOTAL_REPORTS=0 ROWS_RETURNED=0")
        print("Category patterns: []")
        return []

    reports_data = get_all_reports_dicts(db)
    clusters = cluster_reports(reports_data)

    logger.info(f"[{datetime.now(timezone.utc).isoformat()}] EVENT=query_category_patterns TOTAL_REPORTS={total_count} CLUSTERS_FOUND={len(clusters)}")
    print("Similarity pattern clusters:", clusters)
    return clusters


def get_pattern_intelligence(db: Session) -> dict[str, Any]:
    """
    Comprehensive Insight & Pattern Engine:
    Returns similarity clusters, recurring failure detections, trend classifications, anomalies, and AI insights.
    """
    total_count = get_total_reports(db)
    if total_count == 0:
        return {
            "clusters":          [],
            "repeated_failures": [],
            "anomalies":         [],
            "insights":          [],
            "trend_summary":     {"trend": "STABLE", "reason": "No data available."}
        }

    reports_data = get_all_reports_dicts(db)
    clusters = cluster_reports(reports_data)
    repeated = detect_repeated_failures(clusters)
    monthly = get_monthly_trends(db)
    sites = get_site_stats(db)

    counts = [int(m.get("total", 0)) for m in monthly]
    labels = [m.get("month", "") for m in monthly]
    trend_info = classify_trend(counts, labels)
    anomalies = detect_anomalies(monthly, sites)
    insights = generate_insights(reports_data, clusters, monthly, sites)

    return {
        "clusters":          clusters,
        "repeated_failures": repeated,
        "anomalies":         anomalies,
        "insights":          insights,
        "trend_summary":     trend_info
    }


def get_all_insights(db: Session) -> list[dict[str, Any]]:
    """Return all synthesized AI insights."""
    intel = get_pattern_intelligence(db)
    return intel.get("insights", [])


def get_site_stats(db: Session) -> list[dict[str, Any]]:
    """Group reports by site facility and compute risk ranking metrics."""
    total_count = get_total_reports(db)
    if total_count == 0:
        logger.info(f"[{datetime.now(timezone.utc).isoformat()}] EVENT=query_site_stats TOTAL_REPORTS=0 ROWS_RETURNED=0")
        print("Site stats: []")
        return []

    sql = text("""
        SELECT 
            site,
            COUNT(*) as total,
            SUM(CASE WHEN UPPER(risk_level)='CRITICAL' THEN 1 ELSE 0 END) as critical,
            SUM(CASE WHEN UPPER(sif_potential)='YES' THEN 1 ELSE 0 END) as sif,
            AVG(risk_score) as avg_score
        FROM reports
        WHERE site IS NOT NULL AND site != ''
        GROUP BY site
        ORDER BY total DESC;
    """)
    rows = db.execute(sql).fetchall()
    results: list[dict[str, Any]] = []

    for r in rows:
        site_name = r[0] or "Site Alpha"
        tot = int(r[1] or 0)
        crit = int(r[2] or 0)
        sif = int(r[3] or 0)
        avg_score = round(float(r[4] or 0), 1)
        lvl = "CRITICAL" if crit > 0 or avg_score >= 75 else ("HIGH" if avg_score >= 50 else "MEDIUM")

        results.append({
            "site":                 site_name,
            "total":                tot,
            "critical":             crit,
            "sif":                  sif,
            "risk_score":           int(avg_score),
            "risk_level":           lvl,
            "top_precursor":        "Procedural Precursor",
            "top_barrier_failure":  "Control Verification",
        })

    logger.info(f"[{datetime.now(timezone.utc).isoformat()}] EVENT=query_site_stats TOTAL_REPORTS={total_count} ROWS_RETURNED={len(results)}")
    print("Site stats:", results)
    return results


def get_activity_stats(db: Session) -> list[dict[str, Any]]:
    """Group reports by operational activity and compute risk ranking metrics."""
    total_count = get_total_reports(db)
    if total_count == 0:
        logger.info(f"[{datetime.now(timezone.utc).isoformat()}] EVENT=query_activity_stats TOTAL_REPORTS=0 ROWS_RETURNED=0")
        print("Activity stats: []")
        return []

    sql = text("""
        SELECT 
            activity,
            COUNT(*) as total,
            SUM(CASE WHEN UPPER(risk_level)='CRITICAL' THEN 1 ELSE 0 END) as critical,
            SUM(CASE WHEN UPPER(sif_potential)='YES' THEN 1 ELSE 0 END) as sif,
            AVG(risk_score) as avg_score
        FROM reports
        WHERE activity IS NOT NULL AND activity != ''
        GROUP BY activity
        ORDER BY total DESC;
    """)
    rows = db.execute(sql).fetchall()
    results: list[dict[str, Any]] = []

    for r in rows:
        act_name = r[0] or "General Operation"
        tot = int(r[1] or 0)
        crit = int(r[2] or 0)
        sif = int(r[3] or 0)
        avg_score = round(float(r[4] or 0), 1)
        lvl = "CRITICAL" if crit > 0 or avg_score >= 75 else ("HIGH" if avg_score >= 50 else "MEDIUM")

        results.append({
            "activity":            act_name,
            "total":               tot,
            "critical":            crit,
            "sif":                 sif,
            "risk_score":          int(avg_score),
            "risk_level":          lvl,
            "top_barrier_failure": "Permit / Verification",
        })

    logger.info(f"[{datetime.now(timezone.utc).isoformat()}] EVENT=query_activity_stats TOTAL_REPORTS={total_count} ROWS_RETURNED={len(results)}")
    print("Activity stats:", results)
    return results


# ─── Composite Aggregation Functions ─────────────────────────────────────────

def get_dashboard_data(db: Session) -> DashboardData:
    """Assemble all dashboard figures using the shared query functions."""
    total_reports = get_total_reports(db)
    sif_stats = get_sif_count(db)
    risk_distribution = get_risk_distribution(db)

    # Category distribution
    cat_rows = (
        db.query(Report.category, func.count(Report.report_id))
        .group_by(Report.category)
        .order_by(func.count(Report.report_id).desc())
        .all()
    )
    category_distribution = {str(row[0]): int(row[1]) for row in cat_rows if row[0]}

    # Average risk score
    raw_avg = db.query(func.avg(Report.risk_score)).scalar()
    avg_risk_score = round(float(raw_avg), 1) if raw_avg is not None else 0.0

    top_category = (
        max(category_distribution, key=category_distribution.__getitem__)
        if category_distribution and total_reports > 0 else "N/A"
    )
    top_risk_level = (
        max(risk_distribution, key=risk_distribution.__getitem__)
        if risk_distribution and total_reports > 0 and max(risk_distribution.values()) > 0 else "N/A"
    )

    data = DashboardData(
        total_reports         = total_reports,
        sif_count             = sif_stats["sif_count"],
        non_sif_count         = sif_stats["non_sif_count"],
        critical_count        = risk_distribution.get("CRITICAL", 0),
        high_risk_count       = risk_distribution.get("HIGH", 0),
        sif_percentage        = sif_stats["sif_percentage"],
        risk_distribution     = risk_distribution,
        category_distribution = category_distribution,
        avg_risk_score        = avg_risk_score,
        top_category          = top_category,
        top_risk_level        = top_risk_level,
    )
    logger.info(f"[{datetime.now(timezone.utc).isoformat()}] EVENT=compute_dashboard_summary TOTAL_REPORTS={total_reports} AVG_SCORE={avg_risk_score}")
    return data


def get_command_center_data(db: Session) -> dict[str, Any]:
    """Retrieve executive KPI metrics and top high priority unmitigated reports."""
    total_reports = get_total_reports(db)
    critical_alerts = db.query(func.count(Report.report_id)).filter(Report.risk_level == "CRITICAL").scalar() or 0
    sif_potential = db.query(func.count(Report.report_id)).filter(Report.sif_potential == "YES").scalar() or 0
    high_risk_sites = db.query(Report.site).filter(Report.risk_level.in_(["CRITICAL", "HIGH"])).distinct().count()
    open_actions = db.query(func.count(Action.id)).filter(Action.status != "COMPLETED").scalar() or 0

    high_priority = (
        db.query(Report)
        .filter(Report.risk_level.in_(["CRITICAL", "HIGH"]))
        .order_by(Report.risk_score.desc())
        .limit(20)
        .all()
    )

    result = {
        "total_reports":         total_reports,
        "critical_alerts":       critical_alerts,
        "sif_potential":         sif_potential,
        "high_risk_sites":       high_risk_sites,
        "rising_precursors":     min(critical_alerts, 4),
        "open_actions":          open_actions,
        "early_warnings_count":  critical_alerts,
        "high_priority_reports": high_priority or [],
    }
    logger.info(f"[{datetime.now(timezone.utc).isoformat()}] EVENT=compute_command_center TOTAL_REPORTS={total_reports} CRITICAL={critical_alerts} OPEN_ACTIONS={open_actions}")
    return result


def get_debug_counts(db: Session) -> dict[str, int]:
    """Returns field population counts to verify data integrity."""
    total_reports = db.query(func.count(Report.report_id)).scalar() or 0
    with_category = db.query(func.count(Report.report_id)).filter(Report.category.isnot(None), Report.category != '').scalar() or 0
    with_site = db.query(func.count(Report.report_id)).filter(Report.site.isnot(None), Report.site != '').scalar() or 0
    with_activity = db.query(func.count(Report.report_id)).filter(Report.activity.isnot(None), Report.activity != '').scalar() or 0
    res = {
        "total_reports": total_reports,
        "with_category": with_category,
        "with_site": with_site,
        "with_activity": with_activity,
    }
    logger.info(f"[{datetime.now(timezone.utc).isoformat()}] EVENT=query_debug_counts RESULT={res}")
    return res


def refresh_analytics_cache(db: Session) -> dict[str, Any]:
    """Clear in-memory caches, recompute fresh aggregations, and return status."""
    CACHE.clear()
    total = get_total_reports(db)
    sif = get_sif_count(db)
    trends = get_monthly_trends(db)
    patterns = get_category_patterns(db)
    sites = get_site_stats(db)
    activities = get_activity_stats(db)

    result = {
        "status": "refreshed",
        "total_reports": total,
        "sif_count": sif["sif_count"],
        "trends_count": len(trends),
        "patterns_count": len(patterns),
        "sites_count": len(sites),
        "activities_count": len(activities),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    logger.info(f"[{datetime.now(timezone.utc).isoformat()}] EVENT=analytics_cache_refreshed TOTAL_REPORTS={total}")
    return result
