"""
services/pattern_adapter.py — Phase 2 Pattern Intelligence adapter for the Safety Copilot.

Phase 2 (Pattern Intelligence) is developed separately on another branch. To keep
this branch independent of uncommitted Phase 2 code, the Copilot consumes pattern
results only through this adapter:

    Pattern provider (Phase 2) → normalize_pattern() → structured pattern context → Copilot LLM

The adapter exposes:
- `GroundedPattern`: the canonical structured pattern shape the Copilot understands
  (pattern_id, pattern_type, description, frequency, trend, sites, activities,
  barriers, evidence_report_ids, confidence).
- `register_pattern_provider()`: a hook so a future Phase 2 service can supply its
  results without touching Copilot code.
- `get_pattern_context()`: returns normalized patterns plus a provenance label.

Default provider: the pattern intelligence already present in this repository
(`analytics_service.get_pattern_intelligence`, powered by `pattern_engine`), so the
Copilot is grounded today and Phase 2 can later replace/extend the provider.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("safesense.pattern_adapter")

# Provider signature: (db, question) -> list of pattern dicts (any shape the provider uses).
# The adapter normalizes whatever comes back into GroundedPattern objects.
PatternProvider = Callable[[Session, str], List[Dict[str, Any]]]

_PROVIDER: Optional[PatternProvider] = None
_PROVIDER_NAME: str = "builtin_pattern_engine"


def register_pattern_provider(provider: PatternProvider, name: str) -> None:
    """
    Register a Phase 2 pattern intelligence provider.

    The provider receives (db, question) and returns a list of pattern dicts.
    Dicts may use the Phase 2 conceptual shape (pattern_id, pattern_type,
    description, frequency, trend, sites, activities, barriers,
    evidence_report_ids, confidence) or the repository's current cluster shape
    (cluster_id, theme, barrier, count, sites, ...); normalization handles both.
    """
    global _PROVIDER, _PROVIDER_NAME
    _PROVIDER = provider
    _PROVIDER_NAME = name
    logger.info("Pattern provider registered: %s", name)


def reset_pattern_provider() -> None:
    """Restore the built-in provider (used by tests)."""
    global _PROVIDER, _PROVIDER_NAME
    _PROVIDER = None
    _PROVIDER_NAME = "builtin_pattern_engine"


@dataclass
class GroundedPattern:
    """Canonical structured pattern shape consumed by the Copilot."""
    pattern_id: str
    pattern_type: str
    description: str
    frequency: int
    trend: Optional[str] = None
    sites: List[str] = field(default_factory=list)
    activities: List[str] = field(default_factory=list)
    barriers: List[str] = field(default_factory=list)
    evidence_report_ids: List[str] = field(default_factory=list)
    confidence: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "pattern_type": self.pattern_type,
            "description": self.description,
            "frequency": self.frequency,
            "trend": self.trend,
            "sites": self.sites,
            "activities": self.activities,
            "barriers": self.barriers,
            "evidence_report_ids": self.evidence_report_ids,
            "confidence": self.confidence,
        }


def _as_list(value: Any) -> List[str]:
    """Coerce a field to a clean list of strings."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def _coerce_confidence(value: Any) -> Optional[float]:
    """Map arbitrary confidence representations into 0..1, or None when absent."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        if f > 1.0:  # expressed as percentage
            f = f / 100.0
        return round(min(max(f, 0.0), 1.0), 3)
    s = str(value).strip().lower()
    if s in {"high"}:
        return 0.9
    if s in {"medium", "med"}:
        return 0.6
    if s in {"low"}:
        return 0.3
    return None


def normalize_pattern(raw_pattern: Dict[str, Any]) -> Optional[GroundedPattern]:
    """
    Normalize a provider-specific pattern dict into a GroundedPattern.
    Accepts the Phase 2 conceptual shape and the repository's current cluster
    shape. Returns None for dicts without enough information to be useful.
    """
    if not isinstance(raw_pattern, dict):
        return None

    pattern_id = (
        raw_pattern.get("pattern_id")
        or raw_pattern.get("cluster_id")
        or raw_pattern.get("id")
        or raw_pattern.get("name")
    )
    description = (
        raw_pattern.get("description")
        or raw_pattern.get("theme")
        or raw_pattern.get("simplified_insight")
        or raw_pattern.get("human_insight")
    )
    frequency = raw_pattern.get("frequency", raw_pattern.get("count", 0))

    if not pattern_id or not description:
        return None

    try:
        frequency = int(frequency or 0)
    except (TypeError, ValueError):
        frequency = 0

    barriers = _as_list(raw_pattern.get("barriers") or raw_pattern.get("barrier"))
    risk_level = raw_pattern.get("risk_level")

    return GroundedPattern(
        pattern_id=str(pattern_id),
        pattern_type=str(raw_pattern.get("pattern_type") or "recurring_cluster"),
        description=str(description),
        frequency=frequency,
        trend=raw_pattern.get("trend"),
        sites=_as_list(raw_pattern.get("sites")),
        activities=_as_list(raw_pattern.get("activities")),
        barriers=[b for b in barriers if b],
        evidence_report_ids=_as_list(
            raw_pattern.get("evidence_report_ids") or raw_pattern.get("report_ids")
        ),
        confidence=_coerce_confidence(
            raw_pattern.get("confidence", raw_pattern.get("confidence_level"))
        ),
        raw=dict(raw_pattern),
    )


# ─── Built-in provider (repository's existing pattern intelligence) ───────────

def _builtin_provider(db: Session, question: str) -> List[Dict[str, Any]]:
    """
    Default provider backed by the pattern intelligence already in this repo.
    Returns repeated-failure clusters from `analytics_service`.
    Kept lazy so a Phase 2 provider can replace it at startup without import cycles.
    """
    try:
        from services.analytics_service import get_pattern_intelligence
        intel = get_pattern_intelligence(db)
        return list(intel.get("repeated_failures") or [])
    except Exception as exc:  # retrieval errors must be visible, never silently dropped
        logger.warning("Built-in pattern provider failed: %s", exc)
        return []


def get_pattern_context(db: Session, question: str, max_patterns: int = 5) -> Dict[str, Any]:
    """
    Retrieve normalized patterns for the Copilot question.

    Returns:
        {
            "patterns": List[GroundedPattern],
            "provider": provider name (provenance),
        }
    """
    provider = _PROVIDER or _builtin_provider
    name = _PROVIDER_NAME if _PROVIDER else "builtin_pattern_engine"

    try:
        raw_patterns = provider(db, question) or []
    except Exception as exc:
        logger.warning("Pattern provider '%s' failed: %s", name, exc)
        raw_patterns = []

    patterns: List[GroundedPattern] = []
    for rp in raw_patterns:
        normalized = normalize_pattern(rp)
        if normalized is not None and normalized.frequency >= 2:
            patterns.append(normalized)
        if len(patterns) >= max_patterns:
            break

    return {"patterns": patterns, "provider": name}


def format_pattern_context(patterns: List[GroundedPattern], provider: str) -> str:
    """Render normalized patterns as a structured block for the LLM system prompt."""
    if not patterns:
        return (
            "--- PATTERN INTELLIGENCE (provider: %s) ---\n"
            "No recurring patterns with sufficient frequency are currently available."
        ) % provider

    lines = [
        "--- PATTERN INTELLIGENCE (provider: %s) ---" % provider,
        "Pre-verified recurring patterns detected across the report database:",
    ]
    for p in patterns:
        parts = [
            f"Pattern {p.pattern_id} [{p.pattern_type}] — {p.description}",
            f"  Frequency: {p.frequency} reports",
        ]
        if p.sites:
            parts.append(f"  Sites: {', '.join(p.sites)}")
        if p.activities:
            parts.append(f"  Activities: {', '.join(p.activities)}")
        if p.barriers:
            parts.append(f"  Barriers: {', '.join(p.barriers)}")
        if p.trend:
            parts.append(f"  Trend: {p.trend}")
        if p.confidence is not None:
            parts.append(f"  Confidence: {p.confidence:.2f}")
        if p.evidence_report_ids:
            parts.append(f"  Evidence reports: {', '.join(p.evidence_report_ids[:10])}")
        lines.extend(parts)

    return "\n".join(lines)
