"""
test_copilot.py â€” Comprehensive unit and integration tests for SafeSense AI Safety Copilot.

Tests:
1. Missing GROQ_API_KEY raises HTTP 503 (no fake/mock silent responses).
2. Grounded baseline summary generation from SQLite.
3. Multi-field dynamic database retrieval (token matching across description, site, activity, category, barrier).
4. User prompt PII sanitization before retrieval and LLM context construction.
5. Database report text PII sanitization during context construction.
6. Mocked Groq LLM integration returning grounded answer and source report IDs.
7. End-to-end API endpoint tests for POST /api/copilot/chat.
8. Empty database handling.
"""
import os
import unittest
from unittest.mock import MagicMock, patch
import httpx
import pytest
from fastapi import HTTPException

from database import SessionLocal, engine, Base
import models
from schemas import CopilotHistoryMessage
from services.copilot_service import (
    get_baseline_summary,
    format_context,
    chat_with_copilot,
)
from services import copilot_retrieval
from services.copilot_retrieval import retrieve_relevant_reports
from main import app


class TestSafetyCopilot(unittest.TestCase):

    def setUp(self):
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_missing_groq_api_key_raises_503(self):
        """Verify missing GROQ_API_KEY raises HTTP 503 with informative message."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GROQ_API_KEY", None)
            with self.assertRaises(HTTPException) as ctx:
                chat_with_copilot(self.db, "What is our highest risk site?")
            self.assertEqual(ctx.exception.status_code, 503)
            self.assertIn("Groq API key is not configured", ctx.exception.detail)

    def test_baseline_summary_generation(self):
        """Verify baseline summary accurately reflects SQLite database rows."""
        summary = get_baseline_summary(self.db)
        self.assertIsInstance(summary, str)
        # Phase 3 grounded format: deterministic aggregates with explicit scope lines
        self.assertIn("Reports examined", summary)
        self.assertIn("SIF-potential reports in scope:", summary)
        self.assertIn("Risk level distribution in scope:", summary)
        self.assertIn("Reports by site", summary)
        self.assertIn("Barrier failure frequency:", summary)

    def test_dynamic_retrieval_relevance(self):
        """Verify token matching retrieves relevant reports for specific queries."""
        # Query for confined space
        reports = retrieve_relevant_reports(self.db, "Show me confined space issues", max_records=5)
        self.assertTrue(len(reports) > 0)
        # Verify at least one report matches confined space in category, activity, or description
        has_match = any(
            "confined" in (r.category or "").lower() or
            "confined" in (r.activity or "").lower() or
            "confined" in (r.description or "").lower()
            for r in reports
        )
        self.assertTrue(has_match, "Should retrieve confined space related reports")

    def test_user_prompt_pii_sanitization(self):
        """Verify user question with PII is sanitized before reaching retrieval and prompt."""
        raw_question = "Worker Rahul Kumar (Employee ID 48392) called 9876543210 about a gas leak"

        # Mock Groq to capture messages argument passed to create()
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(message=MagicMock(content="Verified safety response citing [Report SAF-001]"))
        ]
        mock_client.chat.completions.create.return_value = mock_completion

        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test_key_12345"}), \
             patch("services.copilot_service.Groq", return_value=mock_client):

            chat_with_copilot(self.db, raw_question)

            # Check calls to completions.create
            call_args = mock_client.chat.completions.create.call_args
            self.assertIsNotNone(call_args)
            messages = call_args.kwargs.get("messages", [])

            # Verify the user message passed to Groq does NOT contain raw PII
            user_msg = [m for m in messages if m["role"] == "user"][-1]
            self.assertNotIn("Rahul Kumar", user_msg["content"])
            self.assertNotIn("48392", user_msg["content"])
            self.assertNotIn("9876543210", user_msg["content"])
            self.assertIn("[WORKER_NAME]", user_msg["content"])
            self.assertIn("[EMPLOYEE_ID]", user_msg["content"])
            self.assertIn("[PHONE]", user_msg["content"])

    def test_context_pii_sanitization_on_retrieved_reports(self):
        """Verify that any PII present in report descriptions is sanitized in format_context."""
        # Create a mock report with PII in description
        fake_report = models.Report(
            report_id="TEST-PII-001",
            description="Technician Alex Morgan at alex@company.com bypassed safety interlock.",
            category="Energy Isolation",
            risk_level="HIGH",
            risk_score=75,
            sif_potential="YES",
            site="Site Alpha",
            unit="Cracker Unit",
            area="Furnace",
            activity="Maintenance",
            barrier_failure="Interlock Bypass",
            date="2024-03-15"
        )
        context_text, source_ids = format_context("Macro baseline summary", [fake_report])

        self.assertIn("TEST-PII-001", source_ids)
        self.assertNotIn("alex@company.com", context_text)
        self.assertIn("[EMAIL]", context_text)
        self.assertNotIn("Alex Morgan", context_text)
        self.assertIn("[WORKER_NAME]", context_text)

    def test_chat_with_copilot_success(self):
        """Verify chat_with_copilot returns CopilotChatResponse with citations."""
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(message=MagicMock(content="Based on the database, Site Alpha has the highest SIF count [Report SAF-001]."))
        ]
        mock_client.chat.completions.create.return_value = mock_completion

        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test_key_12345"}), \
             patch("services.copilot_service.Groq", return_value=mock_client):

            resp = chat_with_copilot(
                db=self.db,
                message="Which site has the highest SIF risk?",
                history=[CopilotHistoryMessage(role="user", content="Hello")]
            )

            self.assertEqual(resp.data_source, "SQLite")
            # Model must match the service's env-based configuration, not a hardcoded name
            from services.copilot_service import DEFAULT_GROQ_MODEL
            self.assertEqual(resp.model, os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL))
            self.assertIn("Site Alpha", resp.answer)
    def test_empty_database_handling(self):
        """Verify baseline summary and retrieval handle an empty DB gracefully."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        # Create an in-memory SQLite DB with empty tables
        mem_engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=mem_engine)
        MemSession = sessionmaker(bind=mem_engine)
        mem_db = MemSession()
        try:
            summary = get_baseline_summary(mem_db)
            self.assertIn("Database Status: Empty", summary)
            reports = retrieve_relevant_reports(mem_db, "any query")
            self.assertEqual(len(reports), 0)
            context_text, source_ids = format_context(summary, reports)
            self.assertEqual(len(source_ids), 0)
            self.assertIn("No specific individual reports retrieved", context_text)
        finally:
            mem_db.close()



    def test_copilot_api_endpoint_503_when_no_api_key(self):
        """Verify POST /api/copilot/chat returns 503 if GROQ_API_KEY is not configured."""
        import asyncio

        async def _test():
            with patch.dict(os.environ, {}, clear=True):
                os.environ.pop("GROQ_API_KEY", None)
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    res = await client.post(
                        "/api/copilot/chat",
                        json={"message": "What is our highest risk site?"}
                    )
                    self.assertEqual(res.status_code, 503)
                    self.assertIn("Groq API key is not configured", res.json()["detail"])

        asyncio.run(_test())

    def test_copilot_api_endpoint_success_with_mocked_groq(self):
        """Verify POST /api/copilot/chat returns 200 with proper schema when Groq succeeds."""
        import asyncio

        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(message=MagicMock(content="Critical safety analysis completed. High risk detected."))
        ]
        mock_client.chat.completions.create.return_value = mock_completion

        async def _test():
            with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test_endpoint_key"}), \
                 patch("services.copilot_service.Groq", return_value=mock_client):

                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    res = await client.post(
                        "/api/copilot/chat",
                        json={
                            "message": "What are the primary barrier failures in our dataset?",
                            "history": [
                                {"role": "user", "content": "Hi copilot"},
                                {"role": "assistant", "content": "Hello! How can I help?"}
                            ]
                        }
                    )
                    self.assertEqual(res.status_code, 200)
                    data = res.json()
                    self.assertIn("answer", data)
                    self.assertIn("source_reports", data)
                    self.assertEqual(data["data_source"], "SQLite")
                    self.assertIsInstance(data["source_reports"], list)

        asyncio.run(_test())
