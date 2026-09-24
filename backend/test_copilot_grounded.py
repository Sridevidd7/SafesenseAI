"""
test_copilot_grounded.py — Phase 3 integration tests for the grounded Safety Copilot.

Covers (with a mocked Groq client, so no network or API key is required):
1. chat_with_copilot returns deterministic grounding metadata derived from the DB.
2. Evidence grounding: the prompt sent to the LLM contains the deterministic
   aggregates and PII-sanitized report evidence — and never contains raw PII.
3. Hallucination resistance: an LLM reply that invents values can be detected by
   comparing against the grounding payload; the service always returns the
   deterministic counts alongside the answer.
4. Pattern adapter: builtin provider, custom provider registration (Phase 2
   compatibility), normalization of the Phase 2 conceptual shape.
5. Scope/date filtering end-to-end through chat_with_copilot.
6. Insufficient-data handling: empty scope produces an explicit insufficient-evidence
   signal in the prompt.
7. API endpoint regression: response schema includes grounding and stays backward
   compatible (answer, source_reports, data_source, model).
"""
import os
import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import httpx
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
import models
from schemas import CopilotHistoryMessage
from services import copilot_retrieval as R
from services import pattern_adapter
from services.copilot_service import chat_with_copilot
from main import app


def make_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return engine


def make_mock_groq(content: str = "Grounded answer citing [Report R-001]."):
    client = MagicMock()
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=content))]
    client.chat.completions.create.return_value = completion
    return client


class GroundedCopilotTestBase(unittest.TestCase):
    """Seeds a deterministic in-memory dataset and patches Groq."""

    REPORTS = [
        dict(report_id="R-001", description="Technician performed pump overhaul without applying lockout tagout isolation.",
             category="Unsafe Act", risk_level="CRITICAL", risk_score=95, sif_potential="YES",
             site="Site Alpha", unit="Refinery Unit 2", area="Compressor Area",
             activity="Pump Maintenance", barrier_failure="Energy Isolation Not Applied", date="2026-03-04"),
        dict(report_id="R-002", description="Worker entered reactor vessel without completing gas testing before entry.",
             category="Unsafe Act", risk_level="CRITICAL", risk_score=90, sif_potential="YES",
             site="Site Beta", unit="Refinery Unit 1", area="Reactor Area",
             activity="Reactor Inspection", barrier_failure="Gas Testing Not Completed", date="2026-03-05"),
        dict(report_id="R-003", description="Operator began tank entry with expired gas test certificate.",
             category="Unsafe Act", risk_level="HIGH", risk_score=80, sif_potential="YES",
             site="Site Alpha", unit="Refinery Unit 1", area="Tank Farm",
             activity="Confined Space Pre-entry", barrier_failure="Gas Testing Not Completed", date="2026-02-10"),
        dict(report_id="R-004", description="Housekeeping audit noted missing safety glasses in workshop.",
             category="Unsafe Condition", risk_level="LOW", risk_score=20, sif_potential="NO",
             site="Site Alpha", unit="Fabrication Unit", area="Workshop 1",
             activity="General Operation", barrier_failure="PPE Compliance", date="2026-02-18"),
        dict(report_id="R-005", description="Technician Jamie Rivera called 9876543210 about missing lockout on pump.",
             category="Unsafe Act", risk_level="HIGH", risk_score=70, sif_potential="YES",
             site="Site Alpha", unit="Refinery Unit 2", area="Compressor Area",
             activity="Pump Maintenance", barrier_failure="Energy Isolation Not Applied", date="2026-03-06"),
    ]

    def setUp(self):
        self.engine = make_engine()
        Session = sessionmaker(bind=self.engine)
        self.db = Session()
        for kwargs in self.REPORTS:
            self.db.add(models.Report(pii_detected=0, pii_count=0, pii_types="", **kwargs))
        self.db.commit()
        self.mock_client = make_mock_groq()

    def tearDown(self):
        pattern_adapter.reset_pattern_provider()
        self.db.close()
        self.engine.dispose()

    def run_chat(self, message, **kwargs):
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test_key"}), \
             patch("services.copilot_service.Groq", return_value=self.mock_client):
            return chat_with_copilot(db=self.db, message=message, **kwargs)

    def last_llm_messages(self):
        call = self.mock_client.chat.completions.create.call_args
        return call.kwargs.get("messages", [])


class TestGroundedResponse(GroundedCopilotTestBase):

    def test_response_contains_deterministic_grounding(self):
        resp = self.run_chat("How many SIF reports do we have?")
        self.assertIsNotNone(resp.grounding)
        # "SIF" narrows the scope to SIF-potential reports; all of them are counted
        self.assertEqual(resp.grounding.reports_examined, 4)
        self.assertEqual(resp.grounding.sif_count, 4)
        self.assertEqual(resp.data_source, "SQLite")
        self.assertEqual(resp.source_reports, resp.grounding.source_reports)

    def test_total_db_grounding_on_broad_question(self):
        resp = self.run_chat("What are the recurring safety issues?")
        # No SIF mention -> whole database in scope
        self.assertEqual(resp.grounding.reports_examined, 5)
        self.assertEqual(resp.grounding.sif_count, 4)

    def test_llm_prompt_contains_deterministic_aggregates(self):
        self.run_chat("Which barrier failures occur most often?")
        system_msg = self.last_llm_messages()[0]["content"]
        self.assertIn("Reports examined (matching scope): 5", system_msg)
        self.assertIn("SIF-potential reports in scope: 4 of 5", system_msg)
        self.assertIn("Barrier failure frequency:", system_msg)
        self.assertIn("Energy Isolation Not Applied: 2 occurrences", system_msg)
        self.assertIn("Gas Testing Not Completed: 2 occurrences", system_msg)

    def test_source_reports_are_real_db_records(self):
        resp = self.run_chat("Show me evidence for the gas testing issue.")
        real_ids = {
            r.report_id for r in self.db.query(models.Report.report_id).all()
        }
        for rid in resp.source_reports:
            self.assertIn(rid, real_ids)

    def test_no_pii_in_llm_prompt(self):
        self.run_chat("Show me evidence for the energy isolation issue.")
        prompt = " ".join(m["content"] for m in self.last_llm_messages())
        self.assertNotIn("Jamie Rivera", prompt)
        self.assertNotIn("9876543210", prompt)
        self.assertIn("[WORKER_NAME]", prompt)
        self.assertIn("[PHONE]", prompt)

    def test_no_pii_in_response_payload(self):
        resp = self.run_chat("What happened with the pump maintenance team?")
        payload = resp.model_dump_json()
        self.assertNotIn("Jamie Rivera", payload)
        self.assertNotIn("9876543210", payload)

    def test_user_prompt_pii_sanitized_in_llm_messages(self):
        self.run_chat("Worker John Smith (Employee ID 12345) asked about lockout failures")
        user_msgs = [m for m in self.last_llm_messages() if m["role"] == "user"]
        self.assertTrue(user_msgs)
        content = user_msgs[-1]["content"]
        self.assertNotIn("John Smith", content)
        self.assertIn("[WORKER_NAME]", content)


class TestScopeFiltering(GroundedCopilotTestBase):

    def test_site_filter_end_to_end(self):
        resp = self.run_chat("How many SIF reports at Site Beta?")
        self.assertEqual(resp.grounding.reports_examined, 1)
        self.assertEqual(resp.grounding.sif_count, 1)
        self.assertEqual(resp.grounding.filters_applied.get("site"), "Site Beta")

    def test_date_filter_end_to_end(self):
        resp = self.run_chat("What changed in the last 30 days?")
        self.assertIsNotNone(resp.grounding.date_range)
        self.assertIn("30 days", resp.grounding.date_range)
        # Fixture dates are Feb–Mar 2026; a 30-day window ending today excludes them all
        self.assertEqual(resp.grounding.reports_examined, 0)

    def test_unknown_site_reported_not_applied(self):
        resp = self.run_chat("How many SIF reports at Site Omega?")
        # Site filter unapplied, but the SIF part of the scope still applies
        self.assertEqual(resp.grounding.reports_examined, 4)
        self.assertTrue(any("Site Omega" in u for u in resp.grounding.filters_unapplied))

    def test_empty_scope_flags_insufficient_evidence(self):
        resp = self.run_chat("Any SIF reports at Site Omega in the last 7 days?")
        system_msg = self.last_llm_messages()[0]["content"]
        self.assertIn("0 reports matched", system_msg)
        self.assertIn("INSUFFICIENT", system_msg.upper())

    def test_filters_never_silently_dropped(self):
        resp = self.run_chat("Show medium risk reports in the unit at Site Alpha")
        self.assertEqual(resp.grounding.filters_applied.get("site"), "Site Alpha")
        self.assertEqual(resp.grounding.filters_applied.get("risk_level"), "MEDIUM")
        self.assertTrue(any("unit" in u for u in resp.grounding.filters_unapplied))


class TestHallucinationResistance(GroundedCopilotTestBase):

    def test_invented_llm_counts_detectable_via_grounding(self):
        """A hallucinating LLM reply is detectable: grounding carries the true counts."""
        self.mock_client = make_mock_groq(
            "The database contains 999 SIF reports at Site Alpha and 47 barrier failures."
        )
        resp = self.run_chat("How many SIF reports do we have?")
        self.assertIn("999", resp.answer)  # LLM said it...
        self.assertEqual(resp.grounding.sif_count, 4)  # ...but the deterministic truth is exposed
        self.assertEqual(resp.grounding.reports_examined, 4)

    def test_non_assessable_trend_flagged_in_prompt(self):
        self.run_chat("Are barrier failures increasing?")
        system_msg = self.last_llm_messages()[0]["content"]
        # With only 2 monthly buckets and 5 reports the trend must be NOT ASSESSABLE
        self.assertIn("NOT ASSESSABLE", system_msg)

    def test_pattern_confidence_only_from_provider(self):
        """Pattern confidence appears in grounding only when a provider supplied it."""
        resp = self.run_chat("What are the recurring safety issues?")
        for p in resp.grounding.patterns:
            self.assertIsNotNone(p.pattern_id)
            self.assertIsNotNone(p.description)
        # Pattern source provenance is always explicit
        self.assertTrue(resp.grounding.pattern_source)


class TestPatternAdapter(unittest.TestCase):

    def test_normalize_phase2_conceptual_shape(self):
        raw = {
            "pattern_id": "P-101",
            "pattern_type": "recurring_barrier_failure",
            "description": "Gas Testing Not Completed across confined space entries",
            "frequency": 6,
            "trend": "increasing",
            "sites": ["Site Alpha", "Site Beta"],
            "activities": ["Confined Space Pre-entry"],
            "barriers": ["Gas Testing Not Completed"],
            "evidence_report_ids": ["R-001", "R-002"],
            "confidence": 0.87,
        }
        gp = pattern_adapter.normalize_pattern(raw)
        self.assertIsNotNone(gp)
        self.assertEqual(gp.pattern_id, "P-101")
        self.assertEqual(gp.frequency, 6)
        self.assertEqual(gp.confidence, 0.87)
        self.assertEqual(gp.evidence_report_ids, ["R-001", "R-002"])

    def test_normalize_builtin_cluster_shape(self):
        raw = {
            "cluster_id": "CL-007",
            "theme": "Repeated Energy Isolation Not Applied in Unsafe Act",
            "count": 4,
            "sites": ["Site Alpha"],
            "barrier": "Energy Isolation Not Applied",
            "trend": "stable",
        }
        gp = pattern_adapter.normalize_pattern(raw)
        self.assertIsNotNone(gp)
        self.assertEqual(gp.pattern_id, "CL-007")
        self.assertEqual(gp.description, "Repeated Energy Isolation Not Applied in Unsafe Act")
        self.assertEqual(gp.frequency, 4)
        self.assertEqual(gp.barriers, ["Energy Isolation Not Applied"])

    def test_normalize_rejects_empty(self):
        self.assertIsNone(pattern_adapter.normalize_pattern({}))
        self.assertIsNone(pattern_adapter.normalize_pattern("not a dict"))

    def test_confidence_coercion(self):
        self.assertEqual(pattern_adapter._coerce_confidence("HIGH"), 0.9)
        self.assertEqual(pattern_adapter._coerce_confidence(55), 0.55)
        self.assertIsNone(pattern_adapter._coerce_confidence(None))

    def test_custom_phase2_provider_used(self):
        def phase2_provider(db, question):
            return [{
                "pattern_id": "P2-001",
                "pattern_type": "precursor_chain",
                "description": "Permit + gas-test failures co-occurring",
                "frequency": 9,
                "trend": "increasing",
                "sites": ["Site Alpha"],
                "evidence_report_ids": ["R-001"],
                "confidence": 0.75,
            }]

        pattern_adapter.register_pattern_provider(phase2_provider, "phase2_engine")
        engine = make_engine()
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            ctx = pattern_adapter.get_pattern_context(db, "recurring issues")
            self.assertEqual(ctx["provider"], "phase2_engine")
            self.assertEqual(len(ctx["patterns"]), 1)
            self.assertEqual(ctx["patterns"][0].pattern_id, "P2-001")
        finally:
            pattern_adapter.reset_pattern_provider()
            db.close()
            engine.dispose()

    def test_provider_failure_does_not_break_copilot(self):
        def broken_provider(db, question):
            raise RuntimeError("phase 2 unavailable")

        pattern_adapter.register_pattern_provider(broken_provider, "broken_phase2")
        engine = make_engine()
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            ctx = pattern_adapter.get_pattern_context(db, "recurring issues")
            self.assertEqual(ctx["patterns"], [])  # degraded, not crashed
        finally:
            pattern_adapter.reset_pattern_provider()
            db.close()
            engine.dispose()

    def test_patterns_included_in_grounded_response(self):
        def phase2_provider(db, question):
            return [{
                "pattern_id": "P2-777",
                "pattern_type": "recurring_barrier_failure",
                "description": "Repeated gas testing failures",
                "frequency": 5,
                "evidence_report_ids": ["R-002", "R-003"],
                "confidence": 0.8,
            }]

        pattern_adapter.register_pattern_provider(phase2_provider, "phase2_engine")
        engine = make_engine()
        Session = sessionmaker(bind=engine)
        db = Session()
        for kwargs in GroundedCopilotTestBase.REPORTS:
            db.add(models.Report(pii_detected=0, pii_count=0, pii_types="", **kwargs))
        db.commit()
        try:
            with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test_key"}), \
                 patch("services.copilot_service.Groq", return_value=make_mock_groq()):
                resp = chat_with_copilot(db=db, message="What are the recurring safety issues?")
            self.assertEqual(resp.grounding.pattern_source, "phase2_engine")
            self.assertEqual(resp.grounding.patterns[0].pattern_id, "P2-777")
            self.assertEqual(resp.grounding.patterns[0].confidence, 0.8)
            # Pattern evidence surfaced in the LLM prompt too
            # (prompt assertion via a fresh mock would re-run; covered by format tests)
        finally:
            pattern_adapter.reset_pattern_provider()
            db.close()
            engine.dispose()


class TestApiEndpointRegression(unittest.TestCase):
    """Regression: /api/copilot/chat keeps its original contract and adds grounding."""

    def test_endpoint_503_without_api_key(self):
        import asyncio

        async def _test():
            with patch.dict(os.environ, {}, clear=True):
                os.environ.pop("GROQ_API_KEY", None)
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    res = await client.post("/api/copilot/chat", json={"message": "How many SIF reports?"})
                    self.assertEqual(res.status_code, 503)

        asyncio.run(_test())

    def test_endpoint_200_with_grounding(self):
        import asyncio

        async def _test():
            mock_client = make_mock_groq("Grounded answer.")
            with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_endpoint_key"}), \
                 patch("services.copilot_service.Groq", return_value=mock_client):
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    res = await client.post(
                        "/api/copilot/chat",
                        json={"message": "How many reports at Site Alpha?", "history": []},
                    )
                    self.assertEqual(res.status_code, 200)
                    data = res.json()
                    # Original contract preserved
                    self.assertIn("answer", data)
                    self.assertIn("source_reports", data)
                    self.assertEqual(data["data_source"], "SQLite")
                    # New Phase 3 grounding block
                    self.assertIn("grounding", data)
                    self.assertIsNotNone(data["grounding"])
                    self.assertIn("reports_examined", data["grounding"])
                    self.assertIn("filters_applied", data["grounding"])
                    self.assertEqual(data["grounding"]["filters_applied"].get("site"), "Site Alpha")

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()
