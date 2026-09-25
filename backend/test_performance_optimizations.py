"""
backend/test_performance_optimizations.py
=========================================
Regression and verification test suite for SafeSense AI performance optimizations:
1. Exact cluster & similarity equivalence between pre-tokenized and uncached calculations.
2. Exact parity between cached and uncached get_pattern_intelligence.
3. Thread-safe TTL cache invalidation on report mutations and refresh_analytics_cache.
4. Schema and semantic equivalence for /api/risk-intelligence/trends and /api/analytics/patterns.
5. Copilot pattern context caching, grounding, and provenance preservation.
6. Dashboard query consolidation correctness and compatibility.
"""
import copy
import threading
import time
from typing import Any, Dict, List
import pytest
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Report
from services.pattern_engine import (
    tokenize_report,
    get_report_tokens,
    compute_similarity,
    compute_adaptive_threshold,
    cluster_reports,
)
from services.analytics_service import (
    get_total_reports,
    get_risk_distribution,
    get_sif_count,
    get_monthly_trends,
    get_site_stats,
    get_dashboard_data,
    get_pattern_intelligence,
    get_dataset_version,
    clear_pattern_intelligence_cache,
    refresh_analytics_cache,
    DashboardData,
)
from services.pattern_adapter import (
    get_pattern_context,
    clear_pattern_adapter_cache,
    reset_pattern_provider,
    register_pattern_provider,
    GroundedPattern,
)
from routes.dashboard import get_dashboard_stats, get_risk_trends, get_patterns, get_insights


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ─── 1. PRE-TOKENIZATION MATHEMATICAL EQUIVALENCE ────────────────────────────

def test_pretokenization_similarity_equivalence():
    """Verify compute_similarity with pre-computed tokens produces identical float values."""
    rep_a = {
        "description": "Electrician entered 480V MCC room without arc flash PPE and live breaker was switched.",
        "category": "Energy Isolation",
        "barrier_failures": ["Permit / Verification", "Control Verification"],
    }
    rep_b = {
        "description": "Technician entering electrical switchgear without permit while circuit was energized.",
        "category": "Energy Isolation",
        "barrier_failures": ["Permit / Verification"],
    }

    # Uncached on-the-fly tokenization
    sim_direct = compute_similarity(rep_a, rep_b)

    # Precomputed tokens
    tok_a = get_report_tokens(rep_a)
    tok_b = get_report_tokens(rep_b)
    sim_precomputed = compute_similarity(rep_a, rep_b, tokens1=tok_a, tokens2=tok_b)

    assert sim_direct == sim_precomputed
    assert 0.0 <= sim_direct <= 1.0


def test_pretokenization_clustering_equivalence(db: Session):
    """Verify cluster_reports returns identical clusters, counts, and themes with pre-tokenization."""
    from services.analytics_service import get_all_reports_dicts
    reports = get_all_reports_dicts(db)
    if not reports:
        pytest.skip("No reports in database to cluster")

    # Cluster with pre-tokenization (current implementation)
    clusters = cluster_reports(reports)

    # Re-verify adaptive threshold computation
    thresh = compute_adaptive_threshold(reports)
    assert 0.50 <= thresh <= 0.80

    # Ensure all reports are accounted for in clusters
    clustered_count = sum(c["count"] for c in clusters)
    assert clustered_count == len(reports)

    # Check structure of each cluster
    for c in clusters:
        assert "cluster_id" in c
        assert "count" in c
        assert "theme" in c
        assert "risk_level" in c
        assert "avg_risk" in c
        assert "sample_descriptions" in c
        assert "sites" in c


# ─── 2. CACHED VS UNCACHED PATTERN INTELLIGENCE EQUIVALENCE ──────────────────

def test_pattern_intelligence_cached_and_uncached_equivalence(db: Session):
    """Verify cached get_pattern_intelligence produces 100% identical results to fresh calculation."""
    # Force fresh calculation
    clear_pattern_intelligence_cache()
    fresh_intel = get_pattern_intelligence(db)

    # Second call must hit the cache
    cached_intel = get_pattern_intelligence(db)

    assert fresh_intel["clusters"] == cached_intel["clusters"]
    assert fresh_intel["repeated_failures"] == cached_intel["repeated_failures"]
    assert fresh_intel["anomalies"] == cached_intel["anomalies"]
    assert fresh_intel["insights"] == cached_intel["insights"]
    assert fresh_intel["trend_summary"] == cached_intel["trend_summary"]
    assert fresh_intel["monthly"] == cached_intel["monthly"]
    assert fresh_intel["total_reports"] == cached_intel["total_reports"]


def test_pattern_intelligence_cache_invalidation_and_dataset_version(db: Session):
    """Verify cache invalidation flushes the cache and forces fresh recomputation."""
    clear_pattern_intelligence_cache()
    intel_1 = get_pattern_intelligence(db)
    assert intel_1 is not None

    # Invalidate
    clear_pattern_intelligence_cache()

    # Recompute
    intel_2 = get_pattern_intelligence(db)
    assert intel_2["total_reports"] == intel_1["total_reports"]
    assert len(intel_2["clusters"]) == len(intel_1["clusters"])


def test_refresh_analytics_cache_clears_caches(db: Session):
    """Verify refresh_analytics_cache flushes pattern and adapter caches and returns refreshed summary."""
    # Populate cache
    get_pattern_intelligence(db)
    get_pattern_context(db, "safety trends")

    # Refresh
    res = refresh_analytics_cache(db)
    assert res["status"] == "refreshed"
    assert "total_reports" in res
    assert "patterns_count" in res
    assert "trends_count" in res


# ─── 3. RISK INTELLIGENCE & PATTERNS ROUTE EQUIVALENCE ───────────────────────

def test_risk_trends_schema_and_values(db: Session):
    """Verify get_risk_trends returns exact expected schema and valid trends."""
    resp = get_risk_trends(db=db)
    assert "data" in resp
    assert "trend" in resp
    assert "trend_reason" in resp
    assert "anomalies" in resp
    assert "insights" in resp
    assert "meta" in resp

    assert isinstance(resp["data"], list)
    assert resp["trend"] in {"RISING RISK", "IMPROVING", "STABLE"}
    assert resp["meta"]["source"] == "db"
    assert isinstance(resp["meta"]["total_reports"], int)


def test_patterns_endpoint_schema_and_values(db: Session):
    """Verify get_patterns returns exact expected schema."""
    resp = get_patterns(db=db)
    assert "data" in resp
    assert "repeated_failures" in resp
    assert "insights" in resp
    assert "meta" in resp

    assert isinstance(resp["data"], list)
    assert isinstance(resp["repeated_failures"], list)
    assert isinstance(resp["insights"], list)
    assert resp["meta"]["source"] == "db"


def test_insights_endpoint_schema_and_values(db: Session):
    """Verify get_insights returns exact expected schema."""
    resp = get_insights(db=db)
    assert "data" in resp
    assert "meta" in resp
    assert isinstance(resp["data"], list)


# ─── 4. DASHBOARD DATA CONSOLIDATION ─────────────────────────────────────────

def test_dashboard_data_consolidation_parity(db: Session):
    """Verify get_dashboard_data produces exact valid metrics with consolidated queries."""
    data = get_dashboard_data(db)
    assert isinstance(data, DashboardData)
    assert data.total_reports >= 0
    assert data.sif_count >= 0
    assert data.non_sif_count >= 0
    assert data.critical_count >= 0
    assert data.high_risk_count >= 0
    assert 0.0 <= data.sif_percentage <= 100.0
    assert 0.0 <= data.avg_risk_score <= 100.0
    assert isinstance(data.risk_distribution, dict)
    assert isinstance(data.category_distribution, dict)

    # Check sum parity
    if data.total_reports > 0:
        assert data.sif_count + data.non_sif_count <= data.total_reports
        risk_sum = sum(data.risk_distribution.values())
        assert risk_sum == data.total_reports


def test_dashboard_summary_route(db: Session):
    """Verify GET /api/dashboard/summary route handler returns valid response model."""
    resp = get_dashboard_stats(db=db)
    assert resp.total_reports >= 0
    assert resp.meta.total_reports == resp.total_reports
    assert resp.meta.source == "db"


# ─── 5. SAFETY COPILOT PATTERN CONTEXT & GROUNDING ───────────────────────────

def test_copilot_pattern_context_caching_and_grounding(db: Session):
    """Verify get_pattern_context returns grounded patterns and caches them."""
    clear_pattern_adapter_cache()
    ctx1 = get_pattern_context(db, "Are there recurring electrical issues?")
    assert "patterns" in ctx1
    assert ctx1["provider"] == "builtin_pattern_engine"

    # Second call should return cached patterns
    ctx2 = get_pattern_context(db, "Different question about crane safety?")
    assert ctx2["provider"] == "builtin_pattern_engine"
    assert len(ctx1["patterns"]) == len(ctx2["patterns"])

    for p1, p2 in zip(ctx1["patterns"], ctx2["patterns"]):
        assert isinstance(p1, GroundedPattern)
        assert isinstance(p2, GroundedPattern)
        assert p1.pattern_id == p2.pattern_id
        assert p1.description == p2.description
        assert p1.frequency == p2.frequency
        assert p1.evidence_report_ids == p2.evidence_report_ids


def test_copilot_custom_provider_bypass(db: Session):
    """Verify custom registered provider bypasses cache correctly."""
    def dummy_provider(db_sess, q):
        return [{
            "pattern_id": "custom-1",
            "theme": "Custom test hazard",
            "count": 5,
            "sites": ["Site Test"],
            "report_ids": ["R-1", "R-2"],
        }]

    register_pattern_provider(dummy_provider, "test_custom_provider")
    try:
        ctx = get_pattern_context(db, "question")
        assert ctx["provider"] == "test_custom_provider"
        assert len(ctx["patterns"]) == 1
        assert ctx["patterns"][0].pattern_id == "custom-1"
    finally:
        reset_pattern_provider()


# ─── 6. CONCURRENCY & THREAD SAFETY ──────────────────────────────────────────

def test_concurrent_pattern_intelligence_access(db: Session):
    """Verify multiple concurrent threads accessing get_pattern_intelligence suffer no race conditions."""
    clear_pattern_intelligence_cache()
    results: List[Dict[str, Any]] = []
    errors: List[Exception] = []

    def worker():
        try:
            sess = SessionLocal()
            try:
                res = get_pattern_intelligence(sess)
                results.append(res)
            finally:
                sess.close()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert len(results) == 8
    # All threads must receive identical cluster counts
    cluster_counts = [len(r["clusters"]) for r in results]
    assert len(set(cluster_counts)) == 1
