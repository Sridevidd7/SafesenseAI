"""
test_semantic_api.py — Phase 5 API tests for the advisory semantic layer.

Covers:
- POST /api/semantic/analyze returns validated candidates with advisory labeling
- PII is sanitized before semantic processing
- Input validation (length bounds)
- GET /api/semantic/model-info reports provenance, availability and the safety boundary
"""
import asyncio
import unittest
from unittest.mock import patch

import httpx

from main import app


class TestSemanticApi(unittest.TestCase):
    """These tests exercise semantic-layer behavior and response contracts, not
    authentication (covered separately in test_auth_streaming.py). The auth
    dependency is overridden per-test and removed again in tearDown so the
    override never leaks into other test modules."""

    def setUp(self):
        from services.auth import require_authenticated
        app.dependency_overrides[require_authenticated] = lambda: None

    def tearDown(self):
        from services.auth import require_authenticated
        app.dependency_overrides.pop(require_authenticated, None)

    def _client(self):
        transport = httpx.ASGITransport(app=app)
        return httpx.AsyncClient(transport=transport, base_url="http://test")

    def test_analyze_returns_validated_candidates(self):
        async def _run():
            async with self._client() as client:
                res = await client.post(
                    "/api/semantic/analyze",
                    json={"text": "worker entered tank without gas test", "top_k": 2},
                )
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertTrue(data["advisory_only"])
                self.assertTrue(data["available"])
                self.assertTrue(data["candidates"])
                top = data["candidates"][0]
                for key in ("canonical_concept", "concept_type", "confidence",
                            "status", "validation", "source_text"):
                    self.assertIn(key, top)
                self.assertIn(top["status"], ("accepted", "rejected", "suggested"))
        asyncio.run(_run())

    def test_analyze_sanitizes_pii(self):
        async def _run():
            async with self._client() as client:
                res = await client.post(
                    "/api/semantic/analyze",
                    json={"text": "Worker Arjun Mehta (Employee ID 9911) called 9876543210 before entering the vessel without gas test"},
                )
                self.assertEqual(res.status_code, 200)
                payload = res.text
                self.assertNotIn("Arjun Mehta", payload)
                self.assertNotIn("9876543210", payload)
                self.assertNotIn("9911", payload)
        asyncio.run(_run())

    def test_analyze_rejects_short_text(self):
        async def _run():
            async with self._client() as client:
                res = await client.post("/api/semantic/analyze", json={"text": "hi"})
                self.assertEqual(res.status_code, 422)
        asyncio.run(_run())

    def test_model_info_reports_boundary(self):
        async def _run():
            async with self._client() as client:
                res = await client.get("/api/semantic/model-info")
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertTrue(data["advisory_only"])
                self.assertIn("model_id", data)
                self.assertIn("available", data)
                self.assertIn("safety_boundary", data)
                self.assertIn("deterministic", data["safety_boundary"].lower())
        asyncio.run(_run())

    def test_analyze_still_works_when_ml_degraded(self):
        """Simulate a fresh process where the ML model failed to build."""
        async def _run():
            from services import semantic_service as S
            S.reset_model_state()
            try:
                with patch("services.semantic_service._build_model", return_value=False):
                    async with self._client() as client:
                        res = await client.post(
                            "/api/semantic/analyze",
                            json={"text": "no lockout applied during pump repair"},
                        )
                        self.assertEqual(res.status_code, 200)
                        data = res.json()
                        self.assertFalse(data["available"])
                        self.assertEqual(data["candidates"], [])
                        self.assertIsNotNone(data["degraded_reason"])
            finally:
                S.reset_model_state()
        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
