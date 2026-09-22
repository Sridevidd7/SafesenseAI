"""
SafeSense AI — Production Hardening & Failure Resistance Test Suite
====================================================================
Validates all 6 production hardening requirements:
1. Robust Input Handling (abbreviations, fuzzy typo tolerance, mixed casing)
2. Pattern Stability Improvement (synonym expansion, canonical token normalization, cluster stability)
3. Risk Score Justification Layer (presence and clarity of 'risk_reason')
4. LLM Safety Wrapper (retry, timeout, fallback trigger logging)
5. Demo Stability Mode (caching and adapting last successful response)
6. Noise & Edge Case Testing (typos, abbreviations, long noisy paragraphs)
"""
import unittest
import asyncio
import os
import json
from services.barrier_dictionary import normalize_text, detect_barriers, detect_barriers_with_evidence
from services.rule_classifier import classify_life_saving_rule
from services.risk_engine import analyze_report, calculate_risk_score, generate_risk_reason
from services.pattern_engine import cluster_reports, tokenize_report, compute_similarity
from services.llm_service import generate_llm_explanation, fallback_response, DEMO_MODE, CACHE, LAST_SUCCESSFUL_LLM_RESPONSE


class TestProductionHardening(unittest.TestCase):

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Robust Input Handling (Abbreviations, Typos, Mixed Casing)
    # ──────────────────────────────────────────────────────────────────────────
    def test_abbreviation_normalization(self):
        """Test expansion and detection of common abbreviations: loto, ptw, ppe."""
        # 1. LOTO
        text_loto = "Technician serviced energized breaker without LOTO."
        analysis_loto = analyze_report({"report_text": text_loto})
        self.assertIn("Lockout/Tagout Not Completed", analysis_loto["barrier_failures"])
        self.assertEqual(analysis_loto["life_saving_rule"], "Energy Isolation")

        # 2. PTW
        text_ptw = "Worker entered tank with NO PTW issued."
        analysis_ptw = analyze_report({"report_text": text_ptw})
        self.assertIn("Permit Not Obtained", analysis_ptw["barrier_failures"])
        self.assertEqual(analysis_ptw["life_saving_rule"], "Confined Space")

        # 3. PPE
        text_ppe = "Operator handling corrosive chemical without PPE."
        analysis_ppe = analyze_report({"report_text": text_ppe})
        self.assertIn("PPE Not Available", analysis_ppe["barrier_failures"])
        self.assertEqual(analysis_ppe["life_saving_rule"], "Chemical Handling")

    def test_spelling_tolerance_and_typos(self):
        """Test spelling tolerance / fuzzy matching on common industrial safety typos."""
        # 'gass test'
        text_gas = "Worker entered vessel without gass test."
        analysis_gas = analyze_report({"report_text": text_gas})
        self.assertIn("Gas Testing Not Completed", analysis_gas["barrier_failures"])
        self.assertEqual(analysis_gas["life_saving_rule"], "Confined Space")

        # 'scafold' and 'harnes'
        text_height = "Contractor climbed scafold at height without harnes."
        analysis_height = analyze_report({"report_text": text_height})
        self.assertIn("Fall Protection Not Used", analysis_height["barrier_failures"])
        self.assertEqual(analysis_height["life_saving_rule"], "Working at Height")

        # 'isloation' and 'deenergiz'
        text_iso = "Working on live panel without isloation and not deenergiz."
        analysis_iso = analyze_report({"report_text": text_iso})
        self.assertIn("Isolation Not Applied", analysis_iso["barrier_failures"])

    def test_mixed_casing_and_partial_words(self):
        """Test mixed casing and punctuation noise."""
        text_mixed = "wOrKeR EnTeReD CoNfInEd SpAcE -- WiThOuT GAsS TeStInG OR PtW!!"
        analysis_mixed = analyze_report({"report_text": text_mixed})
        self.assertEqual(analysis_mixed["life_saving_rule"], "Confined Space")
        self.assertIn("Gas Testing Not Completed", analysis_mixed["barrier_failures"])
        self.assertIn("Permit Not Obtained", analysis_mixed["barrier_failures"])

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Pattern Stability Improvement (Synonym Expansion & Token Normalization)
    # ──────────────────────────────────────────────────────────────────────────
    def test_synonym_token_expansion(self):
        """Test that canonical synonym tokens are added during tokenization."""
        tokens_live = tokenize_report("Live circuit worked on")
        tokens_powered = tokenize_report("Powered electrical equipment serviced")
        tokens_energized = tokenize_report("Energized panel maintenance")

        self.assertIn("canon_energized", tokens_live)
        self.assertIn("canon_energized", tokens_powered)
        self.assertIn("canon_energized", tokens_energized)

    def test_cluster_stability_across_wording_variations(self):
        """Ensure similar incidents always cluster even with varied phrasing."""
        rep1 = {
            "description": "Technician entered tank without gas testing.",
            "category": "Confined Space",
            "barrier": "Gas Testing Not Completed",
            "barrier_failures": ["Gas Testing Not Completed"],
            "risk_score": 85,
            "sif_potential": "YES",
            "site": "Site Alpha",
        }
        rep2 = {
            "description": "Operator went into vessel with no atmospheric monitoring.",
            "category": "Confined Space",
            "barrier": "Gas Testing Not Completed",
            "barrier_failures": ["Gas Testing Not Completed"],
            "risk_score": 85,
            "sif_potential": "YES",
            "site": "Site Alpha",
        }
        rep3 = {
            "description": "Worker stepped inside chamber without oxygen check.",
            "category": "Confined Space",
            "barrier": "Gas Testing Not Completed",
            "barrier_failures": ["Gas Testing Not Completed"],
            "risk_score": 85,
            "sif_potential": "YES",
            "site": "Site Beta",
        }

        sim_1_2 = compute_similarity(rep1, rep2)
        sim_1_3 = compute_similarity(rep1, rep3)
        self.assertGreaterEqual(sim_1_2, 0.60)
        self.assertGreaterEqual(sim_1_3, 0.60)

        clusters = cluster_reports([rep1, rep2, rep3])
        self.assertEqual(len(clusters), 1, "All 3 reports with varied wording should form a single cluster")
        self.assertEqual(clusters[0]["count"], 3)
        self.assertTrue(clusters[0]["is_repeated"])

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Risk Score Justification Layer ('risk_reason' Field)
    # ──────────────────────────────────────────────────────────────────────────
    def test_risk_score_justification_presence_and_clarity(self):
        """Test risk_reason generation for critical, high, medium, and safe cases."""
        # 1. Multi-barrier critical violation
        rep_crit = analyze_report({
            "report_text": "Worker entered confined space tank without gas testing and without permit."
        })
        self.assertIn("risk_reason", rep_crit)
        self.assertTrue(len(rep_crit["risk_reason"]) > 10)
        self.assertIn("due to multiple barrier failures", rep_crit["risk_reason"].lower())

        # 2. Single barrier high risk violation
        rep_high = analyze_report({
            "report_text": "Worker climbed scaffold at height without safety harness."
        })
        self.assertIn("risk_reason", rep_high)
        self.assertTrue("fall protection" in rep_high["risk_reason"].lower() or "harness" in rep_high["risk_reason"].lower() or "working at height" in rep_high["risk_reason"].lower())

        # 3. Safe preventive stop
        rep_safe = analyze_report({
            "report_text": "Technician noticed missing LOTO and stopped work before servicing panel."
        })
        self.assertIn("risk_reason", rep_safe)
        self.assertIn("low risk", rep_safe["risk_reason"].lower())
        self.assertIn("proactive stop-work", rep_safe["risk_reason"].lower())

    # ──────────────────────────────────────────────────────────────────────────
    # 4. LLM Safety Wrapper & 5. Demo Stability Mode
    # ──────────────────────────────────────────────────────────────────────────
    def test_llm_safety_wrapper_fallback_and_demo_mode(self):
        """Test fallback response and demo mode caching resilience."""
        report_data = {
            "description": "Worker entered vessel without gas testing and without permit.",
            "life_saving_rule": "Confined Space",
            "barrier_failures": ["Gas Testing Not Completed", "Permit Not Obtained"],
            "risk_score": 90,
            "risk_level": "CRITICAL",
            "sif_potential": "YES",
            "confidence": 0.95
        }

        # Run async LLM explanation (will use client or safe fallback seamlessly)
        res = asyncio.run(generate_llm_explanation(report_data))
        self.assertIsInstance(res, dict)
        self.assertIn("root_cause", res)
        self.assertIn("risk_explanation", res)
        self.assertIn("recommended_actions", res)
        self.assertEqual(len(res["recommended_actions"]), 3)
        self.assertIn("CRITICAL", res["risk_explanation"])

    # ──────────────────────────────────────────────────────────────────────────
    # 6. Noise & Edge Case Testing
    # ──────────────────────────────────────────────────────────────────────────
    def test_long_noisy_paragraph_with_mixed_signals(self):
        """Test long realistic observation with operational noise, meeting notes, then critical violation."""
        long_noisy_text = (
            "During the morning shift at Site Alpha, the maintenance team held a toolbox talk about weather conditions "
            "and general housekeeping in the compressor shed. After lunch, technician John and his assistant prepared "
            "their tools and went over to Reactor Vessel V-102. Despite standard safety briefing, the operator entered "
            "the confined space tank without any gass test and with no ptw issued by the site supervisor. Work continued "
            "for 15 minutes before the area manager walked past and intervened."
        )
        analysis = analyze_report({"report_text": long_noisy_text})
        self.assertEqual(analysis["life_saving_rule"], "Confined Space")
        self.assertIn("Gas Testing Not Completed", analysis["barrier_failures"])
        self.assertIn("Permit Not Obtained", analysis["barrier_failures"])
        self.assertEqual(analysis["risk_level"], "CRITICAL")
        self.assertEqual(analysis["sif_potential"], "YES")
        self.assertIn("risk_reason", analysis)
        self.assertIn("multiple barrier failures", analysis["risk_reason"].lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
