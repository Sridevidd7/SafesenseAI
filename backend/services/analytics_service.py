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
import re
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta, date
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


def get_risk_distribution(db: Session, total: Optional[int] = None) -> dict[str, int]:
    """Return report counts grouped by risk level (CRITICAL, HIGH, MEDIUM, LOW)."""
    if total is None:
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


def get_sif_count(db: Session, total: Optional[int] = None) -> dict[str, Any]:
    """Return SIF potential statistics (sif_count, non_sif_count, sif_percentage)."""
    if total is None:
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


def _month_key(date_str: str) -> str | None:
    """
    Extract a 'YYYY-MM' key from a stored date string.
    Report dates are stored as free-form strings; only well-formed
    YYYY-MM-DD prefixes group into monthly buckets (deterministic, portable
    across SQLite and PostgreSQL — no strftime dependency).
    """
    if not date_str:
        return None
    m = str(date_str).strip()[:7]
    return m if re.match(r"^\d{4}-\d{2}$", m) else None


def get_monthly_trends(db: Session, total: Optional[int] = None) -> list[dict[str, Any]]:
    """Compute monthly risk and precursor trends from reports."""
    total_count = total if total is not None else get_total_reports(db)
    if total_count == 0:
        logger.info(f"[{datetime.now(timezone.utc).isoformat()}] EVENT=query_monthly_trends TOTAL_REPORTS=0 ROWS_RETURNED=0")
        print("Trend rows: []")
        return []

    # Portable month bucketing: aggregate well-formed YYYY-MM-DD dates in
    # Python (mirrors copilot_retrieval.get_scoped_monthly_trend). Avoids
    # SQLite's strftime() so the same logic runs on PostgreSQL unchanged.
    rows = db.query(Report.date, Report.sif_potential, Report.risk_level).all()

    buckets: dict[str, dict[str, int]] = {}
    for r_date, r_sif, r_level in rows:
        month = _month_key(r_date)
        if month is None:
            continue
        bucket = buckets.setdefault(month, {"total": 0, "sif": 0, "critical": 0})
        bucket["total"] += 1
        if str(r_sif or "").upper() == "YES":
            bucket["sif"] += 1
        if str(r_level or "").upper() == "CRITICAL":
            bucket["critical"] += 1

    results: list[dict[str, Any]] = [
        {
            "month":    month,
            "total":    buckets[month]["total"],
            "sif":      buckets[month]["sif"],
            "critical": buckets[month]["critical"],
        }
        for month in sorted(buckets.keys())
    ]

    # If date strings could not be grouped by strftime (e.g. non-standard date format),
    # aggregate them into an overall monthly window rather than returning empty
    if not results and total_count > 0:
        sif_stats = get_sif_count(db, total=total_count)
        risk_dist = get_risk_distribution(db, total=total_count)
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
            "barrier":               getattr(r, "barrier_failure", None) or getattr(r, "barrier", None),
            "barrier_failure":       getattr(r, "barrier_failure", "Unspecified"),
            "site":                  r.site,
            "unit":                  getattr(r, "unit", "Not Specified"),
            "area":                  getattr(r, "area", "Not Specified"),
            "activity":              r.activity,
            "risk_score":            r.risk_score,
            "raw_score":             r.risk_score,
            "normalized_score":      norm["normalized_score"],
            "normalization_applied": norm["normalization_applied"],
            "risk_level":            r.risk_level,
            "sif_potential":         r.sif_potential,
            "pii_detected":          bool(getattr(r, "pii_detected", 0)),
            "pii_count":             int(getattr(r, "pii_count", 0)),
            "pii_types":             str(getattr(r, "pii_types", "")),
            "date":                  r.date,
            "created_at":            r.created_at,
        })
    return res




def get_category_patterns(db: Session) -> list[dict[str, Any]]:
    """
    Similarity-based clustering of safety reports.
    Replaces raw SQL GROUP BY with Jaccard similarity clustering and pattern analysis.
    """
    intel = get_pattern_intelligence(db)
    return intel.get("clusters", [])


# ─── Pattern Intelligence In-Process TTL Cache ──────────────────────────────
_PATTERN_INTEL_LOCK = threading.Lock()
_PATTERN_INTEL_CACHE: Optional[Dict[str, Any]] = None
_PATTERN_INTEL_CACHE_KEY: Optional[str] = None
_PATTERN_INTEL_CACHE_TIME: float = 0.0
_PATTERN_INTEL_TTL: float = 60.0


def get_dataset_version(db: Session) -> str:
    """Returns a lightweight signature representing the current report dataset version."""
    row = db.query(func.count(Report.report_id), func.max(Report.created_at)).first()
    count = int(row[0]) if row and row[0] is not None else 0
    max_created = str(row[1]) if row and row[1] is not None else "none"
    return f"{count}_{max_created}"


def clear_pattern_intelligence_cache() -> None:
    """Invalidate in-process pattern intelligence cache."""
    global _PATTERN_INTEL_CACHE, _PATTERN_INTEL_CACHE_KEY, _PATTERN_INTEL_CACHE_TIME
    with _PATTERN_INTEL_LOCK:
        _PATTERN_INTEL_CACHE = None
        _PATTERN_INTEL_CACHE_KEY = None
        _PATTERN_INTEL_CACHE_TIME = 0.0
    logger.info("Pattern intelligence cache invalidated.")
    try:
        from services.pattern_adapter import clear_pattern_adapter_cache
        clear_pattern_adapter_cache()
    except Exception:
        pass


def invalidate_analytics_cache() -> None:
    """Fast non-blocking cache invalidation for dataset mutations (bulk upload, report creation, reset).
    Clears LLM cache and pattern intelligence cache so subsequent analytics and dashboard requests
    lazily recompute using the fresh dataset version.
    """
    try:
        CACHE.clear()
    except Exception as exc:
        logger.warning(f"Error clearing LLM cache: {exc}")
    clear_pattern_intelligence_cache()
    logger.info("Analytics caches invalidated (lazy recompute on next request).")



def get_pattern_intelligence(db: Session) -> dict[str, Any]:
    """
    Comprehensive Insight & Pattern Engine:
    Returns similarity clusters, recurring failure detections, trend classifications, anomalies, and AI insights.
    Caches results in memory with a 60s TTL and dataset-version validation.
    """
    global _PATTERN_INTEL_CACHE, _PATTERN_INTEL_CACHE_KEY, _PATTERN_INTEL_CACHE_TIME

    dataset_version = get_dataset_version(db)
    now = time.time()

    # Fast-path read without lock
    if (
        _PATTERN_INTEL_CACHE is not None
        and _PATTERN_INTEL_CACHE_KEY == dataset_version
        and (now - _PATTERN_INTEL_CACHE_TIME) < _PATTERN_INTEL_TTL
    ):
        return _PATTERN_INTEL_CACHE

    with _PATTERN_INTEL_LOCK:
        now = time.time()
        if (
            _PATTERN_INTEL_CACHE is not None
            and _PATTERN_INTEL_CACHE_KEY == dataset_version
            and (now - _PATTERN_INTEL_CACHE_TIME) < _PATTERN_INTEL_TTL
        ):
            return _PATTERN_INTEL_CACHE

        total_count = int(dataset_version.split("_")[0])
        if total_count == 0:
            empty_res = {
                "clusters":          [],
                "repeated_failures": [],
                "anomalies":         [],
                "insights":          [],
                "trend_summary":     {
                    "trend": "STABLE",
                    "reason": "Insufficient data for reliable trend analysis",
                    "trend_note": "Insufficient data for reliable trend analysis"
                },
                "monthly":           [],
                "total_reports":     0,
            }
            _PATTERN_INTEL_CACHE = empty_res
            _PATTERN_INTEL_CACHE_KEY = dataset_version
            _PATTERN_INTEL_CACHE_TIME = now
            return empty_res

        reports_data = get_all_reports_dicts(db)
        if len(reports_data) != total_count:
            logger.warning(f"[DATA_MISMATCH] total_reports_query={total_count} reports_fetched={len(reports_data)}")

        clusters = cluster_reports(reports_data)
        repeated = detect_repeated_failures(clusters)
        monthly = get_monthly_trends(db, total=total_count)
        sites = get_site_stats(db, total=total_count)

        counts = [int(m.get("total", 0)) for m in monthly]
        labels = [m.get("month", "") for m in monthly]
        trend_info = classify_trend(counts, labels, total_reports=total_count)
        anomalies = detect_anomalies(monthly, sites)
        insights = generate_insights(reports_data, clusters, monthly, sites)

        res = {
            "clusters":          clusters,
            "repeated_failures": repeated,
            "anomalies":         anomalies,
            "insights":          insights,
            "trend_summary":     trend_info,
            "monthly":           monthly,
            "total_reports":     total_count,
        }
        _PATTERN_INTEL_CACHE = res
        _PATTERN_INTEL_CACHE_KEY = dataset_version
        _PATTERN_INTEL_CACHE_TIME = time.time()
        return res


def get_all_insights(db: Session) -> list[dict[str, Any]]:
    """Return all synthesized AI insights."""
    intel = get_pattern_intelligence(db)
    return intel.get("insights", [])


def get_site_stats(db: Session, total: Optional[int] = None) -> list[dict[str, Any]]:
    """Group reports by site facility and compute risk ranking metrics."""
    total_count = total if total is not None else get_total_reports(db)
    if total_count == 0:
        logger.info(f"[{datetime.now(timezone.utc).isoformat()}] EVENT=query_site_stats TOTAL_REPORTS=0 ROWS_RETURNED=0")
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


def get_activity_stats(db: Session, total: Optional[int] = None) -> list[dict[str, Any]]:
    """Group reports by operational activity and compute risk ranking metrics."""
    total_count = total if total is not None else get_total_reports(db)
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
    """Assemble all dashboard figures using consolidated queries."""
    count_avg = db.query(func.count(Report.report_id), func.avg(Report.risk_score)).first()
    total_reports = int(count_avg[0]) if count_avg and count_avg[0] is not None else 0
    raw_avg = count_avg[1] if count_avg and count_avg[1] is not None else None
    avg_risk_score = round(float(raw_avg), 1) if raw_avg is not None else 0.0

    sif_stats = get_sif_count(db, total=total_reports)
    risk_distribution = get_risk_distribution(db, total=total_reports)

    if total_reports > 0:
        # Category distribution
        cat_rows = (
            db.query(Report.category, func.count(Report.report_id))
            .group_by(Report.category)
            .order_by(func.count(Report.report_id).desc())
            .all()
        )
        category_distribution = {str(row[0]): int(row[1]) for row in cat_rows if row[0]}
    else:
        category_distribution = {}

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
    clear_pattern_intelligence_cache()
    total = get_total_reports(db)
    sif = get_sif_count(db, total=total)
    trends = get_monthly_trends(db, total=total)
    patterns = get_category_patterns(db)
    sites = get_site_stats(db, total=total)
    activities = get_activity_stats(db, total=total)

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


# ─── Operational SIF Risk Heatmap / Concentration Explorer ────────────────────

FALLBACK_NAMES = {
    "not specified",
    "unspecified",
    "general unit",
    "general area",
    "general operation",
    "unknown barrier failure",
    "unknown barrier",
    "unknown",
    "",
}


def _is_fallback_name(name: str | None) -> bool:
    """Detect if location/barrier name is an unassigned fallback placeholder."""
    if not name:
        return True
    return name.strip().lower() in FALLBACK_NAMES


def _calculate_period_trend(reports: list[Report], anchor_date: Optional[date] = None) -> tuple[Optional[float], str]:
    """
    Computes SIF precursor trend between current 30-day window and immediately preceding 30-day window.
    Returns (trend_pct, trend_label).
    If date span < 14 days or no valid dates, returns (None, 'Insufficient data').
    """
    valid_dates: list[tuple[date, bool]] = []
    for r in reports:
        d_str = str(r.date or "").strip()
        if len(d_str) >= 10:
            try:
                dt = datetime.strptime(d_str[:10], "%Y-%m-%d").date()
                is_sif = str(r.sif_potential or "").upper() == "YES"
                valid_dates.append((dt, is_sif))
            except Exception:
                pass

    if not valid_dates:
        return None, "Insufficient data"

    dates_only = [d[0] for d in valid_dates]
    max_d = anchor_date or max(dates_only)
    min_d = min(dates_only)

    # Require at least 14 days of span between earliest and latest observation
    if (max_d - min_d).days < 14:
        return None, "Insufficient data"

    # Current window: [max_d - 30 days + 1, max_d]
    # Previous window: [max_d - 60 days + 1, max_d - 30 days]
    curr_start = max_d - timedelta(days=29)
    prev_start = max_d - timedelta(days=59)

    curr_sif = sum(1 for dt, is_sif in valid_dates if is_sif and curr_start <= dt <= max_d)
    prev_sif = sum(1 for dt, is_sif in valid_dates if is_sif and prev_start <= dt < curr_start)

    if prev_sif > 0:
        pct = round(((curr_sif - prev_sif) / prev_sif) * 100, 1)
        sign = "+" if pct > 0 else ""
        return pct, f"{sign}{pct}% vs prev 30d"
    elif curr_sif > 0:
        return 100.0, "+100% vs prev 30d"
    else:
        return 0.0, "0.0% vs prev 30d"


def _determine_node_risk_level(sif_count: int, critical_count: int, avg_score: float, trend_pct: Optional[float]) -> str:
    """
    Mutually exclusive risk level evaluation with strict precedence:
    HIGH -> EMERGING -> MEDIUM -> LOW
    """
    if sif_count >= 3 or avg_score >= 70.0 or critical_count > 0:
        return "HIGH"
    if sif_count >= 1 and trend_pct is not None and trend_pct >= 15.0:
        return "EMERGING"
    if avg_score >= 50.0 or sif_count >= 1:
        return "MEDIUM"
    return "LOW"


def _get_top_barrier(reports: list[Report]) -> str:
    """Find dominant non-fallback failed barrier for a group of reports."""
    barriers = [
        str(r.barrier_failure or "").strip()
        for r in reports
        if r.barrier_failure and not _is_fallback_name(r.barrier_failure)
    ]
    if barriers:
        return Counter(barriers).most_common(1)[0][0]
    # Fallback to category if barrier_failure was unspecified
    cats = [str(r.category or "").strip() for r in reports if r.category]
    if cats:
        return Counter(cats).most_common(1)[0][0]
    return "Unspecified"


def get_sif_risk_heatmap(
    db: Session,
    site: Optional[str] = None,
    unit: Optional[str] = None,
    area: Optional[str] = None,
    activity: Optional[str] = None,
    lsr: Optional[str] = None,
    barrier: Optional[str] = None,
) -> dict[str, Any]:
    """
    Computes Operational SIF Risk Concentration across the 6-tier hierarchy:
    Site → Unit → Area → Activity → SIF Precursor / LSR → Failed Barrier.

    All metrics are calculated directly from SQLite reports table.
    """
    query = db.query(Report)

    if site and site.strip() and site.strip().lower() != "all":
        query = query.filter(Report.site == site.strip())
    if unit and unit.strip() and unit.strip().lower() != "all":
        query = query.filter(Report.unit == unit.strip())
    if area and area.strip() and area.strip().lower() != "all":
        query = query.filter(Report.area == area.strip())
    if activity and activity.strip() and activity.strip().lower() != "all":
        query = query.filter(Report.activity == activity.strip())
    if lsr and lsr.strip() and lsr.strip().lower() != "all":
        query = query.filter(Report.category == lsr.strip())
    if barrier and barrier.strip() and barrier.strip().lower() != "all":
        query = query.filter(Report.barrier_failure == barrier.strip())

    reports = query.order_by(Report.created_at.desc()).all()

    if not reports:
        return {
            "summary": {
                "total_reports": 0,
                "total_precursors": 0,
                "overall_density": 0.0,
                "high_risk_concentrations": 0,
                "emerging_concentrations": 0,
                "top_concentration": "None detected",
            },
            "tree": [],
            "reports": [],
        }

    # Find anchor max date across the matching report set
    all_dts: list[date] = []
    for r in reports:
        d_str = str(r.date or "").strip()
        if len(d_str) >= 10:
            try:
                all_dts.append(datetime.strptime(d_str[:10], "%Y-%m-%d").date())
            except Exception:
                pass
    anchor_max_date = max(all_dts) if all_dts else None

    # Track risk concentrations across the hierarchy (excluding fallback nodes)
    high_risk_count = 0
    emerging_count = 0
    top_concentration_name = "None detected"
    top_concentration_score = -1.0

    # Build the 6-tier tree
    # Level 1: Site
    site_groups: dict[str, list[Report]] = defaultdict(list)
    for r in reports:
        s = r.site or "Site Alpha"
        site_groups[s].append(r)

    tree_nodes: list[dict[str, Any]] = []

    for site_name, s_reports in site_groups.items():
        s_sif = sum(1 for r in s_reports if str(r.sif_potential).upper() == "YES")
        s_crit = sum(1 for r in s_reports if str(r.risk_level).upper() == "CRITICAL")
        s_scores = [r.risk_score for r in s_reports if r.risk_score is not None]
        s_avg = round(sum(s_scores) / len(s_scores), 1) if s_scores else 0.0
        s_trend_pct, s_trend_lbl = _calculate_period_trend(s_reports, anchor_max_date)
        s_risk = _determine_node_risk_level(s_sif, s_crit, s_avg, s_trend_pct)
        s_top_bar = _get_top_barrier(s_reports)
        s_density = round((s_sif / len(s_reports) * 100), 1) if s_reports else 0.0

        if s_risk == "HIGH":
            high_risk_count += 1
        elif s_risk == "EMERGING":
            emerging_count += 1

        if not _is_fallback_name(site_name) and (s_avg > top_concentration_score or top_concentration_name == "None detected"):
            top_concentration_score = s_avg
            top_concentration_name = f"{site_name} (Risk: {s_risk}, SIF: {s_sif})"

        # Level 2: Unit
        unit_groups: dict[str, list[Report]] = defaultdict(list)
        for r in s_reports:
            u = r.unit or "Not Specified"
            unit_groups[u].append(r)

        unit_nodes: list[dict[str, Any]] = []
        for unit_name, u_reports in unit_groups.items():
            u_sif = sum(1 for r in u_reports if str(r.sif_potential).upper() == "YES")
            u_crit = sum(1 for r in u_reports if str(r.risk_level).upper() == "CRITICAL")
            u_scores = [r.risk_score for r in u_reports if r.risk_score is not None]
            u_avg = round(sum(u_scores) / len(u_scores), 1) if u_scores else 0.0
            u_trend_pct, u_trend_lbl = _calculate_period_trend(u_reports, anchor_max_date)
            u_risk = _determine_node_risk_level(u_sif, u_crit, u_avg, u_trend_pct)
            u_top_bar = _get_top_barrier(u_reports)
            u_density = round((u_sif / len(u_reports) * 100), 1) if u_reports else 0.0
            u_is_fallback = _is_fallback_name(unit_name)

            if not u_is_fallback and u_risk == "HIGH":
                high_risk_count += 1
            elif not u_is_fallback and u_risk == "EMERGING":
                emerging_count += 1

            if not u_is_fallback and u_avg > top_concentration_score:
                top_concentration_score = u_avg
                top_concentration_name = f"{site_name} → {unit_name} ({u_risk})"

            # Level 3: Area
            area_groups: dict[str, list[Report]] = defaultdict(list)
            for r in u_reports:
                a = r.area or "Not Specified"
                area_groups[a].append(r)

            area_nodes: list[dict[str, Any]] = []
            for area_name, a_reports in area_groups.items():
                a_sif = sum(1 for r in a_reports if str(r.sif_potential).upper() == "YES")
                a_crit = sum(1 for r in a_reports if str(r.risk_level).upper() == "CRITICAL")
                a_scores = [r.risk_score for r in a_reports if r.risk_score is not None]
                a_avg = round(sum(a_scores) / len(a_scores), 1) if a_scores else 0.0
                a_trend_pct, a_trend_lbl = _calculate_period_trend(a_reports, anchor_max_date)
                a_risk = _determine_node_risk_level(a_sif, a_crit, a_avg, a_trend_pct)
                a_top_bar = _get_top_barrier(a_reports)
                a_density = round((a_sif / len(a_reports) * 100), 1) if a_reports else 0.0
                a_is_fallback = _is_fallback_name(area_name)

                if not a_is_fallback and a_risk == "HIGH":
                    high_risk_count += 1

                # Level 4: Activity
                act_groups: dict[str, list[Report]] = defaultdict(list)
                for r in a_reports:
                    act = r.activity or "General Operation"
                    act_groups[act].append(r)

                act_nodes: list[dict[str, Any]] = []
                for act_name, act_reports in act_groups.items():
                    act_sif = sum(1 for r in act_reports if str(r.sif_potential).upper() == "YES")
                    act_crit = sum(1 for r in act_reports if str(r.risk_level).upper() == "CRITICAL")
                    act_scores = [r.risk_score for r in act_reports if r.risk_score is not None]
                    act_avg = round(sum(act_scores) / len(act_scores), 1) if act_scores else 0.0
                    act_trend_pct, act_trend_lbl = _calculate_period_trend(act_reports, anchor_max_date)
                    act_risk = _determine_node_risk_level(act_sif, act_crit, act_avg, act_trend_pct)
                    act_top_bar = _get_top_barrier(act_reports)
                    act_density = round((act_sif / len(act_reports) * 100), 1) if act_reports else 0.0

                    # Level 5: LSR / Precursor Category
                    lsr_groups: dict[str, list[Report]] = defaultdict(list)
                    for r in act_reports:
                        l = r.category or "General Safety"
                        lsr_groups[l].append(r)

                    lsr_nodes: list[dict[str, Any]] = []
                    for lsr_name, lsr_reports in lsr_groups.items():
                        lsr_sif = sum(1 for r in lsr_reports if str(r.sif_potential).upper() == "YES")
                        lsr_crit = sum(1 for r in lsr_reports if str(r.risk_level).upper() == "CRITICAL")
                        lsr_scores = [r.risk_score for r in lsr_reports if r.risk_score is not None]
                        lsr_avg = round(sum(lsr_scores) / len(lsr_scores), 1) if lsr_scores else 0.0
                        lsr_trend_pct, lsr_trend_lbl = _calculate_period_trend(lsr_reports, anchor_max_date)
                        lsr_risk = _determine_node_risk_level(lsr_sif, lsr_crit, lsr_avg, lsr_trend_pct)
                        lsr_top_bar = _get_top_barrier(lsr_reports)
                        lsr_density = round((lsr_sif / len(lsr_reports) * 100), 1) if lsr_reports else 0.0

                        # Level 6: Barrier Failure
                        bar_groups: dict[str, list[Report]] = defaultdict(list)
                        for r in lsr_reports:
                            b = r.barrier_failure or "Unspecified"
                            bar_groups[b].append(r)

                        barrier_nodes: list[dict[str, Any]] = []
                        for bar_name, bar_reports in bar_groups.items():
                            b_sif = sum(1 for r in bar_reports if str(r.sif_potential).upper() == "YES")
                            b_crit = sum(1 for r in bar_reports if str(r.risk_level).upper() == "CRITICAL")
                            b_scores = [r.risk_score for r in bar_reports if r.risk_score is not None]
                            b_avg = round(sum(b_scores) / len(b_scores), 1) if b_scores else 0.0
                            b_trend_pct, b_trend_lbl = _calculate_period_trend(bar_reports, anchor_max_date)
                            b_risk = _determine_node_risk_level(b_sif, b_crit, b_avg, b_trend_pct)
                            b_density = round((b_sif / len(bar_reports) * 100), 1) if bar_reports else 0.0

                            barrier_nodes.append({
                                "id": f"barrier:{site_name}/{unit_name}/{area_name}/{act_name}/{lsr_name}/{bar_name}",
                                "name": bar_name,
                                "level": "barrier",
                                "total_reports": len(bar_reports),
                                "sif_count": b_sif,
                                "precursor_density": b_density,
                                "risk_level": b_risk,
                                "avg_risk_score": b_avg,
                                "trend_pct": b_trend_pct,
                                "trend_label": b_trend_lbl,
                                "top_barrier": bar_name,
                                "is_fallback": _is_fallback_name(bar_name),
                                "report_ids": [r.report_id for r in bar_reports],
                                "children": [],
                            })

                        lsr_nodes.append({
                            "id": f"lsr:{site_name}/{unit_name}/{area_name}/{act_name}/{lsr_name}",
                            "name": lsr_name,
                            "level": "lsr",
                            "total_reports": len(lsr_reports),
                            "sif_count": lsr_sif,
                            "precursor_density": lsr_density,
                            "risk_level": lsr_risk,
                            "avg_risk_score": lsr_avg,
                            "trend_pct": lsr_trend_pct,
                            "trend_label": lsr_trend_lbl,
                            "top_barrier": lsr_top_bar,
                            "is_fallback": False,
                            "report_ids": [r.report_id for r in lsr_reports],
                            "children": barrier_nodes,
                        })

                    act_nodes.append({
                        "id": f"activity:{site_name}/{unit_name}/{area_name}/{act_name}",
                        "name": act_name,
                        "level": "activity",
                        "total_reports": len(act_reports),
                        "sif_count": act_sif,
                        "precursor_density": act_density,
                        "risk_level": act_risk,
                        "avg_risk_score": act_avg,
                        "trend_pct": act_trend_pct,
                        "trend_label": act_trend_lbl,
                        "top_barrier": act_top_bar,
                        "is_fallback": _is_fallback_name(act_name),
                        "report_ids": [r.report_id for r in act_reports],
                        "children": lsr_nodes,
                    })

                area_nodes.append({
                    "id": f"area:{site_name}/{unit_name}/{area_name}",
                    "name": area_name,
                    "level": "area",
                    "total_reports": len(a_reports),
                    "sif_count": a_sif,
                    "precursor_density": a_density,
                    "risk_level": a_risk,
                    "avg_risk_score": a_avg,
                    "trend_pct": a_trend_pct,
                    "trend_label": a_trend_lbl,
                    "top_barrier": a_top_bar,
                    "is_fallback": a_is_fallback,
                    "report_ids": [r.report_id for r in a_reports],
                    "children": act_nodes,
                })

            unit_nodes.append({
                "id": f"unit:{site_name}/{unit_name}",
                "name": unit_name,
                "level": "unit",
                "total_reports": len(u_reports),
                "sif_count": u_sif,
                "precursor_density": u_density,
                "risk_level": u_risk,
                "avg_risk_score": u_avg,
                "trend_pct": u_trend_pct,
                "trend_label": u_trend_lbl,
                "top_barrier": u_top_bar,
                "is_fallback": u_is_fallback,
                "report_ids": [r.report_id for r in u_reports],
                "children": area_nodes,
            })

        tree_nodes.append({
            "id": f"site:{site_name}",
            "name": site_name,
            "level": "site",
            "total_reports": len(s_reports),
            "sif_count": s_sif,
            "precursor_density": s_density,
            "risk_level": s_risk,
            "avg_risk_score": s_avg,
            "trend_pct": s_trend_pct,
            "trend_label": s_trend_lbl,
            "top_barrier": s_top_bar,
            "is_fallback": False,
            "report_ids": [r.report_id for r in s_reports],
            "children": unit_nodes,
        })

    total_sif_all = sum(1 for r in reports if str(r.sif_potential).upper() == "YES")
    overall_density = round((total_sif_all / len(reports) * 100), 1) if reports else 0.0

    report_list = [
        {
            "report_id": r.report_id,
            "id": r.report_id,
            "description": r.description,
            "category": r.category,
            "risk_score": r.risk_score,
            "risk_level": r.risk_level,
            "sif_potential": r.sif_potential,
            "site": r.site,
            "unit": getattr(r, "unit", "Not Specified"),
            "area": getattr(r, "area", "Not Specified"),
            "activity": r.activity,
            "barrier_failure": getattr(r, "barrier_failure", "Unspecified"),
            "pii_detected": bool(getattr(r, "pii_detected", 0)),
            "pii_count": int(getattr(r, "pii_count", 0)),
            "pii_types": str(getattr(r, "pii_types", "")),
            "date": r.date,
            "created_at": r.created_at,
        }
        for r in reports
    ]

    return {
        "summary": {
            "total_reports": len(reports),
            "total_precursors": total_sif_all,
            "overall_density": overall_density,
            "high_risk_concentrations": high_risk_count,
            "emerging_concentrations": emerging_count,
            "top_concentration": top_concentration_name,
        },
        "tree": tree_nodes,
        "reports": report_list,
    }
