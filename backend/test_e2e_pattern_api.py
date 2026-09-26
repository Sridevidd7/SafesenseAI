"""
test_e2e_pattern_api.py - Test API endpoints for pattern intelligence and insights.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import asyncio
import httpx
from main import app
from database import get_db, Base, engine, SessionLocal
from models import Report
import json

async def run_tests():
    # These tests exercise business logic & response contracts, not auth
    # (covered separately in test_auth_streaming.py). Bypass authentication by
    # overriding only the auth dependency — the DB dependency stays REAL.
    from services.auth import require_authenticated
    app.dependency_overrides[require_authenticated] = lambda: None
    try:
        await _run_assertions()
    finally:
        app.dependency_overrides.pop(require_authenticated, None)


async def _run_assertions():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print("=== Testing /api/analytics/patterns endpoint ===")
        res = await client.get("/api/analytics/patterns")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert "data" in data or isinstance(data, list), "Response must have data"
        print("  -> /api/analytics/patterns response structure valid.")

        print("\n=== Testing /api/analytics/insights endpoint ===")
        res_insights = await client.get("/api/analytics/insights")
        assert res_insights.status_code == 200, f"Expected 200, got {res_insights.status_code}: {res_insights.text}"
        insights_data = res_insights.json()
        assert "data" in insights_data or "insights" in insights_data, "Response must contain data/insights envelope"
        print("  -> /api/analytics/insights response structure valid.")

        print("\n=== Testing /api/risk-intelligence/trends endpoint ===")
        res_trends = await client.get("/api/risk-intelligence/trends")
        assert res_trends.status_code == 200, f"Expected 200, got {res_trends.status_code}: {res_trends.text}"
        trends_data = res_trends.json()
        print("  -> /api/risk-intelligence/trends response structure valid.")

        print("\n>>> ALL END-TO-END PATTERN API TESTS PASSED! <<<")

if __name__ == "__main__":
    asyncio.run(run_tests())

