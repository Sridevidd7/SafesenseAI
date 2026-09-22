"""
test_pii_and_heatmap.py — Comprehensive tests for:
1. PII Detection & Redaction Pipeline
2. Operational SIF Risk Concentration Explorer & Heatmap Engine
"""
import unittest
from datetime import datetime, timezone
from services.pii_service import redact_pii
from services.analytics_service import (
    get_sif_risk_heatmap,
    _determine_node_risk_level,
    _calculate_period_trend,
    _is_fallback_name,
)
from database import SessionLocal
from models import Report


class TestPiiPipeline(unittest.TestCase):
    """Test suite for PII detection, redaction, and safety terminology whitelist."""

    def test_example_from_spec(self):
        """Test exact prompt example: Rahul Kumar (Employee ID 48392) called 9876543210."""
        text = "Rahul Kumar (Employee ID 48392) called 9876543210 after the incident."
        res = redact_pii(text)
        self.assertTrue(res.pii_detected)
        self.assertIn("[WORKER_NAME]", res.redacted_text)
        self.assertIn("[EMPLOYEE_ID]", res.redacted_text)
        self.assertIn("[PHONE]", res.redacted_text)
        self.assertNotIn("Rahul Kumar", res.redacted_text)
        self.assertNotIn("48392", res.redacted_text)
        self.assertNotIn("9876543210", res.redacted_text)
        self.assertEqual(res.pii_count, 3)
        self.assertEqual(res.pii_types, ["EMPLOYEE_ID", "PHONE", "WORKER_NAME"])

    def test_synthetic_demo_pii(self):
        """Test obviously synthetic demo PII string."""
        text = "Demo Worker Jane Doe (Employee ID DEMO-12345) called 555-0199 to report missing lockout."
        res = redact_pii(text)
        self.assertTrue(res.pii_detected)
        self.assertIn("[WORKER_NAME]", res.redacted_text)
        self.assertIn("[EMPLOYEE_ID]", res.redacted_text)
        self.assertIn("[PHONE]", res.redacted_text)
        self.assertIn("missing lockout", res.redacted_text)

    def test_contextual_roles_and_honorifics(self):
        """Test names preceded by worker roles and titles."""
        text1 = "Technician Alex Morgan reported pressure drop in pipeline."
        res1 = redact_pii(text1)
        self.assertTrue(res1.pii_detected)
        self.assertEqual(res1.redacted_text, "Technician [WORKER_NAME] reported pressure drop in pipeline.")

        text2 = "Operator Sam Rivera and Contractor Jordan Lee witnessed electrical flash."
        res2 = redact_pii(text2)
        self.assertTrue(res2.pii_detected)
        self.assertIn("Operator [WORKER_NAME]", res2.redacted_text)
        self.assertIn("Contractor [WORKER_NAME]", res2.redacted_text)

        text3 = "Mr. Chris Patel informed the supervisor about gas test failure."
        res3 = redact_pii(text3)
        self.assertTrue(res3.pii_detected)
        self.assertIn("[WORKER_NAME] informed the supervisor", res3.redacted_text)

    def test_email_and_address_redaction(self):
        """Test email and residential address patterns."""
        text = "Worker reported to supervisor at safety.lead@plant.com or visit 45 Industrial Road Apt 12."
        res = redact_pii(text)
        self.assertTrue(res.pii_detected)
        self.assertIn("[EMAIL]", res.redacted_text)
        self.assertIn("[ADDRESS]", res.redacted_text)
        self.assertNotIn("safety.lead@plant.com", res.redacted_text)
        self.assertNotIn("45 Industrial Road", res.redacted_text)

    def test_safety_operational_terms_remain_intact(self):
        """CRITICAL: Safety operational terms must NEVER be redacted."""
        safety_reports = [
            "Worker entered confined space without completing gas testing.",
            "Technician entered reactor vessel without permit and oxygen levels were not tested before entry.",
            "Pump maintenance team conducted motor overhaul without applying lockout tagout or energy isolation.",
            "Housekeeping audit in workshop noted safety glasses not worn during light material handling.",
            "maybe unsafe conditions near electrical panel, not sure if safe or if breaker was isolated.",
            "Secondary pump replacement initiated at transfer station without lockout tagout energy isolation.",
            "Emergency pump repair started on pipeline without applying lockout tagout isolation.",
            "Welding in hazardous area without hot work permit or fire watch.",
            "Scaffolder working at height without safety harness or fall arrest.",
        ]
        for sr in safety_reports:
            res = redact_pii(sr)
            self.assertFalse(
                res.pii_detected,
                f"Operational report was falsely flagged with PII: '{sr}' -> Redacted: '{res.redacted_text}'"
            )
            self.assertEqual(sr, res.redacted_text)


class TestSifHeatmapAndHierarchy(unittest.TestCase):
    """Test suite for SIF Risk Heatmap aggregation, trend windows, and risk precedence."""

    def test_mutually_exclusive_risk_precedence(self):
        """Verify strict risk precedence: HIGH -> EMERGING -> MEDIUM -> LOW."""
        # 1. High risk: sif_count >= 3 or avg_score >= 70 or critical > 0
        lvl1 = _determine_node_risk_level(sif_count=3, critical_count=0, avg_score=60.0, trend_pct=30.0)
        self.assertEqual(lvl1, "HIGH")

        lvl2 = _determine_node_risk_level(sif_count=1, critical_count=1, avg_score=50.0, trend_pct=25.0)
        self.assertEqual(lvl2, "HIGH")

        lvl3 = _determine_node_risk_level(sif_count=1, critical_count=0, avg_score=75.0, trend_pct=20.0)
        self.assertEqual(lvl3, "HIGH")

        # 2. Emerging risk: NOT HIGH, sif_count >= 1, and positive trend >= 15%
        lvl4 = _determine_node_risk_level(sif_count=2, critical_count=0, avg_score=55.0, trend_pct=25.0)
        self.assertEqual(lvl4, "EMERGING")

        lvl5 = _determine_node_risk_level(sif_count=1, critical_count=0, avg_score=40.0, trend_pct=15.0)
        self.assertEqual(lvl5, "EMERGING")

        # 3. Medium risk: NOT HIGH, NOT EMERGING, and (avg_score >= 50 or sif_count >= 1)
        lvl6 = _determine_node_risk_level(sif_count=1, critical_count=0, avg_score=40.0, trend_pct=5.0)
        self.assertEqual(lvl6, "MEDIUM")

        lvl7 = _determine_node_risk_level(sif_count=0, critical_count=0, avg_score=55.0, trend_pct=None)
        self.assertEqual(lvl7, "MEDIUM")

        # 4. Low risk: baseline safe
        lvl8 = _determine_node_risk_level(sif_count=0, critical_count=0, avg_score=20.0, trend_pct=None)
        self.assertEqual(lvl8, "LOW")

    def test_fallback_name_detection(self):
        """Verify fallback locations and unclassified barriers are clearly distinguished."""
        self.assertTrue(_is_fallback_name("Not Specified"))
        self.assertTrue(_is_fallback_name("General Unit"))
        self.assertTrue(_is_fallback_name("General Area"))
        self.assertTrue(_is_fallback_name("General Operation"))
        self.assertTrue(_is_fallback_name("Unspecified"))
        self.assertTrue(_is_fallback_name("Unknown Barrier Failure"))
        self.assertTrue(_is_fallback_name("unknown barrier"))
        self.assertTrue(_is_fallback_name(""))
        self.assertFalse(_is_fallback_name("Refinery Unit 2"))
        self.assertFalse(_is_fallback_name("Compressor Area"))
        self.assertFalse(_is_fallback_name("Site Alpha"))
        self.assertFalse(_is_fallback_name("Gas Testing Verification"))

    def test_demo_dataset_csv_structure_and_parsing(self):
        """Verify demo_dataset.csv parses with all 9 fields and valid units/areas."""
        import os
        from services.upload_service import _parse_bytes
        csv_path = os.path.join(os.path.dirname(__file__), "demo_dataset.csv")
        if not os.path.exists(csv_path):
            csv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "demo_dataset.csv")
        self.assertTrue(os.path.exists(csv_path), "demo_dataset.csv must exist")
        with open(csv_path, "rb") as f:
            data = f.read()
        df = _parse_bytes(data, "demo_dataset.csv")
        self.assertEqual(len(df), 12)
        self.assertIn("unit", df.columns)
        self.assertIn("area", df.columns)
        self.assertTrue((df["unit"] != "").all())
        self.assertTrue((df["area"] != "").all())

    def test_period_trend_insufficient_data(self):
        """Verify that when date span < 14 days, trend returns 'Insufficient data'."""
        rep1 = Report(report_id="t1", description="desc", sif_potential="YES", date="2026-03-01")
        rep2 = Report(report_id="t2", description="desc", sif_potential="YES", date="2026-03-05")
        pct, label = _calculate_period_trend([rep1, rep2])
        self.assertIsNone(pct)
        self.assertEqual(label, "Insufficient data")

    def test_period_trend_calculation_with_multi_period_data(self):
        """Verify 30-day equivalent window comparison with genuine date spans."""
        # Previous window: 2026-02-01 to 2026-02-28
        # Current window:  2026-03-01 to 2026-03-30
        rep_prev1 = Report(report_id="p1", description="desc", sif_potential="YES", date="2026-02-10")
        rep_prev2 = Report(report_id="p2", description="desc", sif_potential="NO",  date="2026-02-15")
        rep_curr1 = Report(report_id="c1", description="desc", sif_potential="YES", date="2026-03-05")
        rep_curr2 = Report(report_id="c2", description="desc", sif_potential="YES", date="2026-03-12")

        reports = [rep_prev1, rep_prev2, rep_curr1, rep_curr2]
        pct, label = _calculate_period_trend(reports, anchor_date=datetime(2026, 3, 20).date())

        self.assertIsNotNone(pct)
        # Prev SIF = 1, Curr SIF = 2 -> ((2 - 1) / 1) * 100 = +100.0%
        self.assertEqual(pct, 100.0)
        self.assertIn("+100.0% vs prev 30d", label)

    def test_database_sif_heatmap_endpoint_logic(self):
        """Verify live database query aggregation into 6-tier hierarchy."""
        db = SessionLocal()
        try:
            res = get_sif_risk_heatmap(db)
            self.assertIn("summary", res)
            self.assertIn("tree", res)
            self.assertIn("reports", res)
            summary = res["summary"]
            self.assertGreaterEqual(summary["total_reports"], 1)
            self.assertIn("overall_density", summary)
            self.assertIn("top_concentration", summary)

            # Check that tree root contains sites
            tree = res["tree"]
            self.assertGreaterEqual(len(tree), 1)
            site_node = tree[0]
            self.assertEqual(site_node["level"], "site")
            self.assertIn("children", site_node)

            # Check unit level children
            if site_node["children"]:
                unit_node = site_node["children"][0]
                self.assertEqual(unit_node["level"], "unit")
                self.assertIn("is_fallback", unit_node)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
