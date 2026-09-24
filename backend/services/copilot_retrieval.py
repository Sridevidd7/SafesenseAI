"""
services/copilot_retrieval.py — Deterministic SafeSense retrieval layer for the Safety Copilot.

This module is the deterministic half of the grounded Copilot pipeline (Phase 3):

    User question → intent/filter extraction → deterministic retrieval → structured evidence

Responsibilities:
1. Extract explicit and implicit scope filters from a natural-language question
   (site, unit, area, activity, life-saving rule/category, barrier failure,
   risk/severity level, SIF potential, date range such as "last 30 days").
2. Execute deterministic SQL aggregations against the `reports` table to build a
   structured evidence packet: counts, breakdowns, rankings, trends, and
   individual report evidence.
3. Never invent data: every value returned here comes from a real database query.
4. Never expose PII: report descriptions are passed through `redact_pii` before
   being formatted for the LLM.

This layer must stay free of any LLM calls — it is the source of truth that the
LLM later synthesizes. The risk engine, SIF classification, and concept
extraction logic are consumed read-only and never modified here.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

import models
from services.pii_service import redact_pii

logger = logging.getLogger("safesense.copilot_retrieval")

# ─── Constants ────────────────────────────────────────────────────────────────

RISK_LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]

# Barrier values that carry no analytical meaning (mirrors baseline summary logic
# in copilot_service.get_baseline_summary: "Unspecified", "Unknown", "Unknown Barrier Failure")
UNSPECIFIED_BARRIERS = {"Unspecified", "Unknown", "Unknown Barrier Failure"}

SITE_SYNONYMS: Dict[str, str] = {
    "alpha": "Site Alpha",
    "beta": "Site Beta",
    "gamma": "Site Gamma",
    "delta": "Site Delta",
}

LSR_KEYWORDS: Dict[str, str] = {
    "confined space": "Confined Space",
    "confined-space": "Confined Space",
    "energy isolation": "Energy Isolation",
    "lockout": "Energy Isolation",
    "loto": "Energy Isolation",
    "hot work": "Hot Work",
    "working at height": "Working at Height",
    "work at height": "Working at Height",
    "line of fire": "Line of Fire",
    "vehicle movement": "Vehicle Movement",
    "chemical handling": "Chemical Handling",
    "fire prevention": "Fire Prevention",
    "general safety": "General Safety",
}

# Common words filtered out when deriving free-text evidence keywords
RETRIEVAL_STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "if", "in", "on", "at", "to", "for",
    "with", "by", "about", "against", "between", "into", "through", "during",
    "before", "after", "above", "below", "from", "up", "down", "is", "are",
    "was", "were", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "can", "could", "shall", "should", "will", "would", "may", "might",
    "must", "what", "which", "who", "whom", "this", "that", "these", "those",
    "am", "how", "where", "when", "why", "there", "here", "all", "any", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not",
    "only", "own", "same", "so", "than", "too", "very", "s", "t", "just",
    "don", "now", "tell", "show", "give", "find", "list", "me", "our", "us",
    "we", "i", "you", "report", "reports", "safety", "database", "data",
    "incident", "incidents", "issue", "issues", "please", "help", "many",
    "much", "often", "have", "trend", "trends", "top", "highest", "highest",
    "common", "commonly", "frequent", "recurring", "recurring", "occur",
    "occurs", "occurred", "compare", "compared", "month", "months", "day",
    "days", "last", "past", "week", "weeks", "year", "years", "increase",
    "increasing", "decrease", "decreasing", "changed", "change", "current",
    "previous", "evidence", "explain", "happened", "failures", "failure",
    "barriers", "barrier", "potential", "site", "sites", "unit", "units",
    "area", "areas", "activity", "activities", "category", "categories",
    "severity", "risk", "risky", "sif", "show", "number", "count", "counts",
    "total", "summarize", "summary", "overview", "status",
}

MONTH_NAME_TO_NUM = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

# Suffixes stripped from "2026-05" style tokens so "May 2026" also matches months
_DATE_TOKEN_STRIP = ".,!?:;()[]\"'"


# ─── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class CopilotFilters:
    """Scope filters extracted from the user's question."""
    site: Optional[str] = None
    unit: Optional[str] = None
    area: Optional[str] = None
    activity: Optional[str] = None
    category: Optional[str] = None          # life-saving rule / hazard category
    barrier_failure: Optional[str] = None
    risk_level: Optional[str] = None
    sif_potential: Optional[str] = None     # "YES" | "NO"
    date_from: Optional[str] = None         # inclusive, "YYYY-MM-DD" strings (DB stores dates as strings)
    date_to: Optional[str] = None           # inclusive
    date_label: Optional[str] = None        # human label e.g. "last 30 days"
    keywords: List[str] = field(default_factory=list)
    unapplied: List[str] = field(default_factory=list)  # requested scopes we could not resolve

    def applied(self) -> Dict[str, str]:
        """Filters that will actually be applied to queries."""
        out: Dict[str, str] = {}
        if self.site:
            out["site"] = self.site
        if self.unit:
            out["unit"] = self.unit
        if self.area:
            out["area"] = self.area
        if self.activity:
            out["activity"] = self.activity
        if self.category:
            out["category"] = self.category
        if self.barrier_failure:
            out["barrier_failure"] = self.barrier_failure
        if self.risk_level:
            out["risk_level"] = self.risk_level
        if self.sif_potential:
            out["sif_potential"] = self.sif_potential
        if self.date_from:
            out["date_from"] = self.date_from
        if self.date_to:
            out["date_to"] = self.date_to
        return out


@dataclass
class EvidencePacket:
    """Structured, database-grounded evidence returned by the retrieval layer."""
    filters: CopilotFilters
    total_reports: int
    sif_count: int
    non_sif_count: int
    risk_distribution: Dict[str, int]
    top_sites: List[Dict[str, Any]]
    top_categories: List[Dict[str, Any]]
    barrier_frequency: List[Dict[str, Any]]
    monthly_trend: List[Dict[str, Any]]
    trend_assessment: Dict[str, Any]
    evidence_reports: List[Dict[str, Any]]
    scoped_sif_count: int = 0

    @property
    def has_data(self) -> bool:
        return self.total_reports > 0


# ─── Filter extraction ────────────────────────────────────────────────────────

def _resolve_site_token(token: str) -> Optional[str]:
    """Resolve 'alpha'/'site alpha' style tokens against known site synonyms."""
    if "site" in token:
        for syn, full in SITE_SYNONYMS.items():
            if syn in token:
                return full
    elif token in SITE_SYNONYMS:
        return SITE_SYNONYMS[token]
    return None


def _best_db_match(db: Session, column, value: str) -> Optional[str]:
    """
    Resolve a free-text scope token to the exact distinct value stored in the DB
    using case-insensitive matching. Returns None when nothing matches so the
    caller can report the filter as unapplied instead of silently dropping it.
    """
    if not value:
        return None
    # Exact (case-insensitive) match first
    row = (
        db.query(column)
        .filter(func.lower(column) == value.lower())
        .first()
    )
    if row and row[0]:
        return str(row[0])
    # Substring match for tokens like "Alpha" vs "Site Alpha"
    row = (
        db.query(column)
        .filter(func.lower(column).ilike(f"%{value.lower()}%"))
        .first()
    )
    if row and row[0]:
        return str(row[0])
    return None


def _extract_date_range(question_lower: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Extract an explicit date range from the question text.
    Returns (date_from, date_to, human_label) or (None, None, None).

    Supports: "last/previous N days", "this month", "last month",
    "in <Month> YYYY" / "in <Month>" (most recent occurrence).
    Uses "today" as the reference point because report dates are stored as
    strings in the database; queries compare lexicographically on YYYY-MM-DD.
    """
    today = date.today()

    m = re.search(r"\b(?:last|past|previous)\s+(\d{1,4})\s+days?\b", question_lower)
    if m:
        n = int(m.group(1))
        if 0 < n <= 3650:
            date_to = today.isoformat()
            date_from = (today - timedelta(days=n)).isoformat()
            return date_from, date_to, f"last {n} days"

    m = re.search(r"\b(?:last|past|previous)\s+(\d{1,3})\s+months?\b", question_lower)
    if m:
        n = int(m.group(1))
        if 0 < n <= 120:
            date_to = today.isoformat()
            date_from = (today - timedelta(days=30 * n)).isoformat()
            return date_from, date_to, f"last {n} months"

    if re.search(r"\bthis\s+month\b", question_lower):
        date_from = today.replace(day=1).isoformat()
        return date_from, today.isoformat(), f"this month ({today.strftime('%Y-%m')})"

    if re.search(r"\blast\s+month\b", question_lower):
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        return (
            first_prev.isoformat(),
            last_prev.isoformat(),
            f"previous month ({last_prev.strftime('%Y-%m')})",
        )

    # Named month, optionally with year: "in March 2026", "May 2026", "March"
    m = re.search(
        r"\b(" + "|".join(MONTH_NAME_TO_NUM.keys()) + r")\s*,?\s*(\d{4})?\b",
        question_lower,
    )
    if m:
        month_num = MONTH_NAME_TO_NUM[m.group(1)]
        year = int(m.group(2)) if m.group(2) else None
        if year is None:
            # Choose the most recent year where the month has already started
            year = today.year if month_num <= today.month else today.year - 1
        if 1 <= month_num <= 12 and 2000 <= year <= 2100:
            first = date(year, month_num, 1)
            if month_num == 12:
                last = date(year, 12, 31)
            else:
                last = date(year, month_num + 1, 1) - timedelta(days=1)
            return first.isoformat(), last.isoformat(), f"{m.group(1).capitalize()} {year}"

    return None, None, None


def extract_filters(db: Session, question: str) -> CopilotFilters:
    """
    Extract scope filters from the user's question.
    Scope values are validated against the database so filters either apply to a
    real value or are reported as unapplied — never silently ignored.
    """
    filters = CopilotFilters()
    raw = redact_pii(question).redacted_text
    q = raw.lower()
    tokens = re.findall(r"[a-z0-9\-]+", q)

    # 1. Site — detect explicit "site X" mentions generically so unknown sites
    #    are reported as unapplied instead of silently ignored.
    site_match = re.search(r"\bsite\s+([a-z0-9\-]+)\b", q)
    if site_match:
        token = site_match.group(1)
        candidate = SITE_SYNONYMS.get(token, f"Site {token.capitalize()}")
        resolved = _best_db_match(db, models.Report.site, candidate)
        if resolved:
            filters.site = resolved
        else:
            filters.unapplied.append(f"site '{candidate}' (no such site in the database)")
    else:
        # Bare synonyms without the word "site" (e.g. "at alpha")
        for tok in tokens:
            if tok in SITE_SYNONYMS:
                resolved = _best_db_match(db, models.Report.site, SITE_SYNONYMS[tok])
                if resolved:
                    filters.site = resolved
                break

    # 2. Risk level / severity
    for level in RISK_LEVELS:
        if re.search(rf"\b{level.lower()}\b", q):
            filters.risk_level = level
            break
    if filters.risk_level is None and re.search(r"\bseverity\b", q):
        filters.unapplied.append("severity level (no specific level named)")

    # 3. SIF potential
    if re.search(r"\bsif\b|\bserious\s+injur|\bfatality\s+potential\b", q):
        if re.search(r"\b(non[- ]?sif|without\s+sif|no\s+sif)\b", q):
            filters.sif_potential = "NO"
        else:
            filters.sif_potential = "YES"

    # 4. Life-saving rule / category keywords
    for kw, cat in LSR_KEYWORDS.items():
        if kw in q:
            resolved = _best_db_match(db, models.Report.category, cat)
            if resolved:
                filters.category = resolved
            else:
                filters.unapplied.append(f"life-saving rule '{cat}' (not present in the database)")
            break

    # 5. Barrier failure keywords
    barrier_rows = (
        db.query(models.Report.barrier_failure)
        .filter(models.Report.barrier_failure.isnot(None))
        .distinct()
        .all()
    )
    known_barriers = [str(r[0]) for r in barrier_rows if r[0] and str(r[0]) not in UNSPECIFIED_BARRIERS]
    if re.search(r"\bgas[- ]?test", q):
        gas_matches = [b for b in known_barriers if "gas" in b.lower()]
        if gas_matches:
            filters.barrier_failure = gas_matches[0]
        else:
            filters.unapplied.append("barrier failure 'Gas Testing' (not present in the database)")
    else:
        # Match a question token against stored barrier names (e.g. "lockout" -> "LOTO / Energy Isolation Failure")
        for b in known_barriers:
            b_low = b.lower()
            for tok in tokens:
                if len(tok) >= 5 and tok in b_low:
                    filters.barrier_failure = b
                    break
            if filters.barrier_failure:
                break

    # 6. Unit / area / activity
    if re.search(r"\bunit\b", q):
        filters.unapplied.append("unit (no specific unit named)")
    if re.search(r"\barea\b", q):
        filters.unapplied.append("area (no specific area named)")
    if re.search(r"\bactivity\b", q):
        filters.unapplied.append("activity (no specific activity named)")

    # 7. Date range
    date_from, date_to, label = _extract_date_range(q)
    if date_from:
        filters.date_from = date_from
        filters.date_to = date_to
        filters.date_label = label

    # 8. Free-text evidence keywords (top few meaningful tokens)
    keywords: List[str] = []
    for tok in tokens:
        if len(tok) >= 3 and tok not in RETRIEVAL_STOP_WORDS and tok not in keywords:
            keywords.append(tok)
        if len(keywords) >= 6:
            break
    filters.keywords = keywords

    return filters


def apply_filters(query, filters: CopilotFilters):
    """Apply the extracted filters to a Report query. Returns the filtered query."""
    if filters.site:
        query = query.filter(models.Report.site == filters.site)
    if filters.unit:
        query = query.filter(models.Report.unit == filters.unit)
    if filters.area:
        query = query.filter(models.Report.area == filters.area)
    if filters.activity:
        query = query.filter(models.Report.activity == filters.activity)
    if filters.category:
        query = query.filter(models.Report.category == filters.category)
    if filters.barrier_failure:
        query = query.filter(models.Report.barrier_failure == filters.barrier_failure)
    if filters.risk_level:
        query = query.filter(models.Report.risk_level == filters.risk_level)
    if filters.sif_potential:
        query = query.filter(models.Report.sif_potential == filters.sif_potential)
    if filters.date_from:
        query = query.filter(models.Report.date >= filters.date_from)
    if filters.date_to:
        query = query.filter(models.Report.date <= filters.date_to)
    return query


# ─── Aggregations ─────────────────────────────────────────────────────────────

def _base_query(db: Session, filters: CopilotFilters):
    return apply_filters(db.query(models.Report), filters)


def _count(query) -> int:
    return int(query.count() or 0)


def retrieve_relevant_reports(
    db: Session,
    sanitized_query: str,
    max_records: int = 8,
) -> List[models.Report]:
    """
    Backward-compatible multi-field keyword retrieval used by earlier Copilot
    versions and their tests. Extracts meaningful tokens from the sanitized
    query and matches them across operational fields, with risk-weighted
    ordering; falls back to top-risk reports when nothing matches.
    """
    from services.copilot_retrieval import RETRIEVAL_STOP_WORDS  # local import: module-level constant

    words = re.findall(r"[A-Za-z0-9_-]{2,}", sanitized_query.lower())
    tokens = [w for w in words if w not in RETRIEVAL_STOP_WORDS]

    order_clause = (
        case((models.Report.sif_potential == "YES", 1), else_=0).desc(),
        models.Report.risk_score.desc(),
        models.Report.date.desc(),
    )

    conditions = []
    for tok in tokens[:6]:
        pattern = f"%{tok}%"
        conditions.append(
            or_(
                models.Report.description.ilike(pattern),
                models.Report.site.ilike(pattern),
                models.Report.unit.ilike(pattern),
                models.Report.area.ilike(pattern),
                models.Report.activity.ilike(pattern),
                models.Report.category.ilike(pattern),
                models.Report.barrier_failure.ilike(pattern),
                models.Report.report_id.ilike(pattern),
            )
        )

    if conditions:
        matched = (
            db.query(models.Report)
            .filter(or_(*conditions))
            .order_by(*order_clause)
            .limit(max_records)
            .all()
        )
        if matched:
            return matched

    return (
        db.query(models.Report)
        .order_by(*order_clause)
        .limit(max_records)
        .all()
    )


def get_scoped_counts(db: Session, filters: CopilotFilters) -> Dict[str, int]:
    """Total and SIF counts under the extracted scope."""
    base = _base_query(db, filters)
    total = _count(base)
    sif_q = _base_query(db, filters).filter(models.Report.sif_potential == "YES")
    return {"total": total, "sif": _count(sif_q)}


def get_scoped_risk_distribution(db: Session, filters: CopilotFilters) -> Dict[str, int]:
    """Risk-level counts under the extracted scope."""
    rows = (
        _base_query(db, filters)
        .with_entities(models.Report.risk_level, func.count(models.Report.report_id))
        .group_by(models.Report.risk_level)
        .all()
    )
    raw = {str(r[0]).upper(): int(r[1]) for r in rows if r[0]}
    return {level: raw.get(level, 0) for level in RISK_LEVELS}


def get_scoped_site_ranking(db: Session, filters: CopilotFilters, limit: int = 5) -> List[Dict[str, Any]]:
    """Sites ranked by report count with SIF sub-counts, under the extracted scope."""
    rows = (
        _base_query(db, filters)
        .with_entities(
            models.Report.site,
            func.count(models.Report.report_id).label("total"),
            func.sum(case((models.Report.sif_potential == "YES", 1), else_=0)).label("sifs"),
            func.avg(models.Report.risk_score).label("avg_score"),
        )
        .group_by(models.Report.site)
        .order_by(func.count(models.Report.report_id).desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "site": str(r[0]),
            "total": int(r[1]),
            "sif": int(r[2] or 0),
            "avg_risk_score": round(float(r[3]), 1) if r[3] is not None else 0.0,
        }
        for r in rows
    ]


def get_scoped_category_ranking(db: Session, filters: CopilotFilters, limit: int = 5) -> List[Dict[str, Any]]:
    """Life-saving rule / hazard categories ranked by count, under the extracted scope."""
    rows = (
        _base_query(db, filters)
        .with_entities(
            models.Report.category,
            func.count(models.Report.report_id).label("total"),
            func.sum(case((models.Report.sif_potential == "YES", 1), else_=0)).label("sifs"),
        )
        .group_by(models.Report.category)
        .order_by(func.count(models.Report.report_id).desc())
        .limit(limit)
        .all()
    )
    return [
        {"category": str(r[0]), "total": int(r[1]), "sif": int(r[2] or 0)}
        for r in rows
    ]


def get_barrier_frequency(db: Session, filters: CopilotFilters, limit: int = 8) -> List[Dict[str, Any]]:
    """
    Barrier failures ranked by occurrence count under the extracted scope.
    Unspecified/unknown barriers are excluded from the ranking.
    """
    rows = (
        _base_query(db, filters)
        .filter(models.Report.barrier_failure.isnot(None))
        .filter(~models.Report.barrier_failure.in_(list(UNSPECIFIED_BARRIERS)))
        .with_entities(
            models.Report.barrier_failure,
            func.count(models.Report.report_id).label("count"),
            func.sum(case((models.Report.sif_potential == "YES", 1), else_=0)).label("sifs"),
        )
        .group_by(models.Report.barrier_failure)
        .order_by(func.count(models.Report.report_id).desc())
        .limit(limit)
        .all()
    )
    return [
        {"barrier": str(r[0]), "count": int(r[1]), "sif_count": int(r[2] or 0)}
        for r in rows
    ]


def get_scoped_monthly_trend(db: Session, filters: CopilotFilters, limit: int = 12) -> List[Dict[str, Any]]:
    """
    Monthly report/SIF counts under the extracted scope.
    Month grouping is computed in Python because report dates are stored as
    free-form strings; malformed dates are skipped deterministically.
    """
    reports = _base_query(db, filters).with_entities(
        models.Report.date,
        models.Report.sif_potential,
        models.Report.risk_level,
    ).all()

    buckets: Dict[str, Dict[str, int]] = {}
    for r_date, r_sif, r_level in reports:
        if not r_date:
            continue
        month = str(r_date)[:7]
        if not re.match(r"^\d{4}-\d{2}$", month):
            continue
        bucket = buckets.setdefault(month, {"total": 0, "sif": 0, "critical": 0})
        bucket["total"] += 1
        if str(r_sif or "").upper() == "YES":
            bucket["sif"] += 1
        if str(r_level or "").upper() == "CRITICAL":
            bucket["critical"] += 1

    return [
        {"month": m, **buckets[m]}
        for m in sorted(buckets.keys())[-limit:]
    ]


def assess_trend(monthly: List[Dict[str, Any]], scope_label: str = "overall") -> Dict[str, Any]:
    """
    Deterministic trend assessment with a conservative sufficiency gate.
    Only reports a direction when there are at least 3 monthly observations and
    at least 10 underlying reports (mirrors pattern_engine.classify_trend logic).
    """
    total_underlying = sum(int(m.get("total", 0)) for m in monthly)
    if len(monthly) < 3 or total_underlying < 10:
        return {
            "assessable": False,
            "reason": (
                f"Insufficient data for a reliable {scope_label} trend "
                f"({len(monthly)} monthly observations, {total_underlying} reports); "
                f"at least 3 months and 10 reports are required."
            ),
        }

    mid = len(monthly) // 2
    first_half = sum(int(m.get("total", 0)) for m in monthly[:mid]) / max(mid, 1)
    second_half = sum(int(m.get("total", 0)) for m in monthly[mid:]) / max(len(monthly) - mid, 1)

    if first_half == 0:
        if second_half > 0:
            return {
                "assessable": True,
                "direction": "INCREASING",
                "detail": (
                    f"Monthly report volume rose from 0 (first half) to "
                    f"{second_half:.1f}/month (second half) of the observed window."
                ),
            }
        return {"assessable": True, "direction": "STABLE", "detail": "Monthly report volume is flat."}

    delta_pct = (second_half - first_half) / first_half * 100.0
    if delta_pct >= 20.0:
        direction = "INCREASING"
    elif delta_pct <= -20.0:
        direction = "DECREASING"
    else:
        direction = "STABLE"
    return {
        "assessable": True,
        "direction": direction,
        "detail": (
            f"Monthly report volume changed by {delta_pct:+.0f}% between the first and "
            f"second half of the {len(monthly)}-month observation window."
        ),
    }


def get_evidence_reports(
    db: Session,
    filters: CopilotFilters,
    max_records: int = 8,
) -> List[Dict[str, Any]]:
    """
    Retrieve individual report evidence under the extracted scope.
    Prioritizes SIF potential and risk score; falls back to keyword search when
    the scoped set is broader than needed, and finally to top-risk reports.
    All descriptions are PII-redacted before returning.
    """
    base = _base_query(db, filters)
    order_clause = (
        case((models.Report.sif_potential == "YES", 1), else_=0).desc(),
        models.Report.risk_score.desc(),
        models.Report.date.desc(),
    )

    reports: List[models.Report] = []

    # Prefer keyword matches when the question carries meaningful free text
    if filters.keywords:
        conditions = []
        for tok in filters.keywords[:6]:
            pattern = f"%{tok}%"
            conditions.append(
                or_(
                    models.Report.description.ilike(pattern),
                    models.Report.category.ilike(pattern),
                    models.Report.barrier_failure.ilike(pattern),
                    models.Report.activity.ilike(pattern),
                    models.Report.site.ilike(pattern),
                    models.Report.unit.ilike(pattern),
                    models.Report.area.ilike(pattern),
                    models.Report.report_id.ilike(pattern),
                )
            )
        scoped = apply_filters(db.query(models.Report), filters)
        matched = (
            scoped.filter(or_(*conditions))
            .order_by(*order_clause)
            .limit(max_records)
            .all()
        )
        if matched:
            reports = matched

    if not reports:
        reports = (
            base.order_by(*order_clause)
            .limit(max_records)
            .all()
        )

    evidence: List[Dict[str, Any]] = []
    for r in reports:
        sanitized = redact_pii(r.description or "").redacted_text.strip()
        evidence.append({
            "report_id": r.report_id,
            "date": r.date,
            "site": r.site,
            "unit": r.unit,
            "area": r.area,
            "activity": r.activity,
            "category": r.category,
            "risk_level": r.risk_level,
            "risk_score": r.risk_score,
            "sif_potential": r.sif_potential,
            "barrier_failure": r.barrier_failure,
            "description": sanitized,
        })
    return evidence


def collect_evidence(db: Session, filters: CopilotFilters) -> EvidencePacket:
    """
    Run the full deterministic retrieval pipeline and return a structured
    evidence packet for LLM synthesis. Every value originates from a SQL query.
    """
    counts = get_scoped_counts(db, filters)
    evidence = EvidencePacket(
        filters=filters,
        total_reports=counts["total"],
        sif_count=counts["sif"],
        non_sif_count=counts["total"] - counts["sif"],
        risk_distribution=get_scoped_risk_distribution(db, filters),
        top_sites=get_scoped_site_ranking(db, filters),
        top_categories=get_scoped_category_ranking(db, filters),
        barrier_frequency=get_barrier_frequency(db, filters),
        monthly_trend=get_scoped_monthly_trend(db, filters),
        trend_assessment={},  # filled below
        evidence_reports=get_evidence_reports(db, filters),
        scoped_sif_count=counts["sif"],
    )
    evidence.trend_assessment = assess_trend(
        evidence.monthly_trend,
        scope_label=filters.date_label or "overall",
    )
    return evidence


# ─── Context formatting ───────────────────────────────────────────────────────

def format_filters_block(filters: CopilotFilters) -> str:
    """Human-readable description of applied and unapplied filters."""
    applied = filters.applied()
    if not applied:
        applied_str = "None (whole database in scope)"
    else:
        applied_str = "; ".join(f"{k}={v}" for k, v in applied.items())
    if filters.keywords:
        applied_str += f"; keyword hints: {', '.join(filters.keywords)}"

    unapplied_str = (
        "; ".join(filters.unapplied) if filters.unapplied else "None"
    )
    return (
        f"Filters applied: {applied_str}\n"
        f"Filters requested but NOT applied: {unapplied_str}"
    )


def format_evidence_context(packet: EvidencePacket) -> str:
    """
    Render the evidence packet as a structured text block for the LLM system prompt.
    The block explicitly separates deterministic aggregates from report evidence
    so the model can cite exact figures without guessing.
    """
    f = packet.filters

    if not packet.has_data:
        lines = [
            "--- RETRIEVED SAFESENSE EVIDENCE ---",
            format_filters_block(f),
            "RESULT: 0 reports matched the requested scope. The SafeSense database "
            "contains no evidence for this question under these filters.",
        ]
        return "\n".join(lines)

    sif_pct = round(packet.sif_count / packet.total_reports * 100, 1) if packet.total_reports else 0.0
    lines = [
        "--- RETRIEVED SAFESENSE EVIDENCE (deterministic database aggregates) ---",
        format_filters_block(f),
        f"Reports examined (matching scope): {packet.total_reports}",
        f"SIF-potential reports in scope: {packet.sif_count} of {packet.total_reports} ({sif_pct}%)",
        (
            f"Risk level distribution in scope: "
            f"CRITICAL={packet.risk_distribution.get('CRITICAL', 0)}, "
            f"HIGH={packet.risk_distribution.get('HIGH', 0)}, "
            f"MEDIUM={packet.risk_distribution.get('MEDIUM', 0)}, "
            f"LOW={packet.risk_distribution.get('LOW', 0)}"
        ),
    ]

    if f.date_label:
        lines.append(f"Date range applied: {f.date_label} ({f.date_from} to {f.date_to})")

    if packet.top_sites:
        site_strs = [
            f"{s['site']}: {s['total']} reports, {s['sif']} SIF-potential"
            for s in packet.top_sites
        ]
        lines.append(f"Reports by site (top {len(site_strs)}): " + "; ".join(site_strs))

    if packet.top_categories:
        cat_strs = [
            f"{c['category']}: {c['total']} reports, {c['sif']} SIF-potential"
            for c in packet.top_categories
        ]
        lines.append(f"Life-saving rules / categories (top {len(cat_strs)}): " + "; ".join(cat_strs))

    if packet.barrier_frequency:
        barrier_strs = [
            f"{b['barrier']}: {b['count']} occurrences ({b['sif_count']} SIF-potential)"
            for b in packet.barrier_frequency
        ]
        lines.append("Barrier failure frequency: " + "; ".join(barrier_strs))

    if packet.monthly_trend:
        trend_strs = [
            f"{m['month']}: {m['total']} reports, {m['sif']} SIF, {m['critical']} critical"
            for m in packet.monthly_trend
        ]
        lines.append("Monthly counts in scope: " + "; ".join(trend_strs))

    ta = packet.trend_assessment
    if ta:
        if ta.get("assessable"):
            lines.append(f"Trend assessment: {ta.get('direction')} — {ta.get('detail')}")
        else:
            lines.append(f"Trend assessment: NOT ASSESSABLE — {ta.get('reason')}")

    lines.append(f"--- Individual report evidence ({len(packet.evidence_reports)} records) ---")
    for ev in packet.evidence_reports:
        lines.append(
            f"- [Report {ev['report_id']}]\n"
            f"  Date: {ev['date'] or 'N/A'} | Site: {ev['site']} | Unit: {ev['unit']} | Area: {ev['area']}\n"
            f"  Activity: {ev['activity']} | Category: {ev['category']}\n"
            f"  Risk Level: {ev['risk_level']} (Score: {ev['risk_score']}) | SIF Potential: {ev['sif_potential']}\n"
            f"  Barrier Failure: {ev['barrier_failure'] or 'Unspecified'}\n"
            f"  Observation: {ev['description']}"
        )

    return "\n".join(lines)
