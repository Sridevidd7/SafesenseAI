"""
SafeSense AI — Phase 7 Performance & Load-Test Baseline
Measures latency (min, p50, p95, max) across critical production paths:
- Health probe (/api/health)
- Readiness probe (/api/ready)
- Report analysis (/api/analyze-report)
- Dashboard stats (/api/dashboard/stats)
- Pattern retrieval (/api/patterns)
- Advisory ML Semantic Layer (/api/semantic/analyze)
- Advisory Vector Store Retrieval
"""

import sys
import time
import statistics
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from fastapi.testclient import TestClient
from main import app
from services.vector_store import search_similar, get_backend_info

client = TestClient(app)


def benchmark(name: str, fn, iterations: int = 30):
    latencies = []
    # Warmup
    for _ in range(3):
        try:
            fn()
        except Exception:
            pass

    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        duration_ms = (time.perf_counter() - start) * 1000.0
        latencies.append(duration_ms)

    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[int(len(latencies) * 0.95)]
    min_lat = min(latencies)
    max_lat = max(latencies)
    avg_lat = statistics.mean(latencies)

    print(
        f"{name:<38} | {iterations:>5} reqs | Min: {min_lat:>6.2f}ms | "
        f"Avg: {avg_lat:>6.2f}ms | p50: {p50:>6.2f}ms | p95: {p95:>6.2f}ms | Max: {max_lat:>6.2f}ms"
    )
    return {
        "name": name,
        "iterations": iterations,
        "min_ms": round(min_lat, 2),
        "avg_ms": round(avg_lat, 2),
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "max_ms": round(max_lat, 2),
    }


def main():
    print("=" * 110)
    print("SafeSense AI — Phase 7 Performance & Load Baseline Benchmark")
    print("=" * 110)

    results = []

    # 1. Health probe
    def test_health():
        r = client.get("/api/health")
        assert r.status_code == 200

    results.append(benchmark("1. Health Probe (/api/health)", test_health, iterations=50))

    # 2. Readiness probe
    def test_ready():
        r = client.get("/api/ready")
        assert r.status_code in (200, 503)

    results.append(benchmark("2. Readiness Probe (/api/ready)", test_ready, iterations=30))

    # 3. Report Analysis (Authoritative Safety Decision Pipeline)
    sample_payload = {
        "report_text": (
            "During scaffolding erection on Tower B, contractor noticed unanchored safety harness "
            "and missing toe boards at 15m elevation. Work was halted immediately before any fall occurred."
        )
    }

    def test_analyze():
        r = client.post("/api/analyze-report", json=sample_payload)
        assert r.status_code == 200

    results.append(benchmark("3. Report Analysis (/api/analyze-report)", test_analyze, iterations=30))

    # 4. Dashboard Stats
    def test_dashboard():
        r = client.get("/api/dashboard/stats")
        assert r.status_code == 200

    results.append(benchmark("4. Dashboard Stats (/api/dashboard/stats)", test_dashboard, iterations=30))

    # 5. Pattern Intelligence
    def test_patterns():
        r = client.get("/api/patterns")
        assert r.status_code == 200

    results.append(benchmark("5. Pattern Intelligence (/api/patterns)", test_patterns, iterations=20))

    # 6. ML-assisted Semantic Layer
    semantic_payload = {
        "text": "worker was exposed to live electrical wire without personal protective equipment"
    }

    def test_semantic():
        r = client.post("/api/semantic/analyze", json=semantic_payload)
        assert r.status_code == 200

    results.append(benchmark("6. Advisory Semantic Layer (/api/semantic/analyze)", test_semantic, iterations=20))

    # 7. Vector Store Retrieval Probe
    backend_info = get_backend_info()

    def test_vector_retrieval():
        search_similar(
            query_vector=[0.05] * 768,
            model_id="text-embedding-3-small",
            top_k=5,
            min_score=0.3,
        )

    results.append(benchmark("7. Advisory Vector Store Retrieval", test_vector_retrieval, iterations=20))

    print("=" * 110)
    print("Baseline benchmark completed successfully.")
    print(f"Backend Target: {backend_info['backend']} | Embeddings Enabled: {backend_info['embeddings_enabled']}")
    print(f"Authoritative Safety Pipeline: p50={results[2]['p50_ms']}ms | p95={results[2]['p95_ms']}ms")
    print(f"Advisory Semantic Layer:       p50={results[5]['p50_ms']}ms | p95={results[5]['p95_ms']}ms")
    print("=" * 110)
    return 0


if __name__ == "__main__":
    sys.exit(main())
