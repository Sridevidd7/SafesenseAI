"""
test_semantic_service.py — Phase 5 tests for the ML-assisted semantic layer.

Coverage map (per Phase 5 requirements):
1.  Semantic paraphrases deterministic matching may miss   -> TestParaphraseRecall
2.  Correct semantic matches                               -> TestParaphraseRecall
3.  Incorrect/ambiguous semantic matches                   -> TestAmbiguityAndThresholds
4.  Confidence thresholds                                  -> TestAmbiguityAndThresholds
5.  Deterministic validation rejecting unsafe ML candidates -> TestDeterministicValidation
6.  ML unavailable / model failure fallback                -> TestFallbackBehavior
7.  Existing deterministic behavior unchanged              -> TestDeterministicProtection
8.  Existing risk/SIF regression cases                     -> TestDeterministicProtection
9.  Repeated execution stable results                      -> TestDeterminismAndStability
10. Benchmark on representative safety examples             -> test_semantic_benchmark.py
"""
import unittest
from unittest.mock import patch

from services import semantic_service as S
from services.rule_classifier import classify_life_saving_rule
from services.barrier_dictionary import detect_barriers
from services.risk_engine import analyze_report


def _top(result):
    return result["candidates"][0] if result["candidates"] else None


class SemanticTestBase(unittest.TestCase):
    def setUp(self):
        S.reset_model_state()

    def tearDown(self):
        S.reset_model_state()


class TestParaphraseRecall(SemanticTestBase):
    """Requirements 1 & 2: paraphrase recall and correct matches."""

    PARAPHRASE_CASES = [
        # (paraphrase, expected canonical LSR concept)
        ("employee climbed up the storage rack with no fall protection gear", "Working at Height"),
        ("he descended into the vessel prior to atmosphere clearance", "Confined Space"),
        ("load was hoisted right over the assembled crew", "Line of Fire"),
        ("acid transferred without face shield or gloves", "Chemical Handling"),
        ("truck backed up with nobody directing traffic", "Vehicle Movement"),
    ]

    def test_paraphrase_recovers_expected_concept(self):
        """Semantic recall: the expected concept must appear in the top-k candidates."""
        for text, expected in self.PARAPHRASE_CASES:
            with self.subTest(text=text):
                result = S.suggest_and_validate(text, top_k=3)
                self.assertTrue(result["available"])
                self.assertTrue(result["candidates"], f"no candidates for: {text}")
                ranked_names = [c["canonical_concept"] for c in result["candidates"]]
                self.assertIn(
                    expected,
                    ranked_names,
                    f"expected concept not in top-k for: {text} -> {ranked_names}",
                )
                for c in result["candidates"]:
                    self.assertGreaterEqual(c["confidence"], S.CONFIDENCE_THRESHOLD)

    def test_correct_direct_matches(self):
        result = S.suggest_and_validate("worker entered tank without gas test", top_k=2)
        top = _top(result)
        self.assertIsNotNone(top)
        self.assertEqual(top["canonical_concept"], "Confined Space")

    def test_barrier_concept_bank_uses_exact_dictionary_names(self):
        """All barrier_failure concepts must exist in the deterministic dictionary."""
        from services.barrier_dictionary import (
            BARRIER_KEYWORDS, BARRIER_REGEX_PATTERNS, BARRIER_SYNONYMS,
        )
        known = set(BARRIER_KEYWORDS) | set(BARRIER_REGEX_PATTERNS) | set(BARRIER_SYNONYMS)
        for spec in S.CANONICAL_CONCEPTS:
            if spec.concept_type == "barrier_failure":
                self.assertIn(spec.name, known, f"concept bank drift: {spec.name}")

    def test_candidate_structure_is_explainable(self):
        result = S.suggest_and_validate("harness was not tied off on the scaffold", top_k=1)
        top = _top(result)
        self.assertIsNotNone(top)
        for key in ("canonical_concept", "confidence", "source_text", "status", "validation"):
            self.assertIn(key, top)
        self.assertEqual(top["source_text"][:50], "harness was not tied off on the scaffold"[:50])
        self.assertIn("validator", top["validation"])
        self.assertIn("evidence", top["validation"])


class TestAmbiguityAndThresholds(SemanticTestBase):
    """Requirements 3 & 4: ambiguous matches and confidence thresholds."""

    def test_below_threshold_produces_no_candidates(self):
        result = S.get_semantic_candidates("lorem ipsum dolor sit amet", top_k=3)
        self.assertTrue(result["available"])
        self.assertEqual(result["candidates"], [])

    def test_empty_text_produces_no_candidates(self):
        for text in ("", "   ", None):
            result = S.get_semantic_candidates(text, top_k=3)
            self.assertEqual(result["candidates"], [])

    def test_ambiguity_flagged_when_margin_narrow(self):
        # Crafted text lexically close to two domains -> top-2 confidences near each other
        result = S.get_semantic_candidates(
            "grinding and welding sparks near flammable chemical drums", top_k=3
        )
        self.assertTrue(result["candidates"])
        if len(result["candidates"]) >= 2:
            top, second = result["candidates"][0], result["candidates"][1]
            if abs(top.confidence - second.confidence) < S.AMBIGUITY_MARGIN:
                self.assertTrue(top.ambiguous)

    def test_threshold_respected_in_ranking(self):
        result = S.get_semantic_candidates("operator completed the routine inspection paperwork", top_k=3)
        for c in result["candidates"]:
            self.assertGreaterEqual(c.confidence, S.CONFIDENCE_THRESHOLD)

    def test_top_k_limits_candidate_count(self):
        result = S.get_semantic_candidates(
            "worker climbed the ladder entered the vessel and started grinding without permit",
            top_k=2,
        )
        self.assertLessEqual(len(result["candidates"]), 2)
        # Raw candidates are SemanticCandidate objects; suggest_and_validate returns dicts
        validated = S.suggest_and_validate(
            "worker climbed the ladder entered the vessel and started grinding without permit",
            top_k=2,
        )
        self.assertTrue(all(isinstance(c, dict) for c in validated["candidates"]))


class TestDeterministicValidation(SemanticTestBase):
    """Requirement 5: deterministic validation overrides/rejects ML candidates."""

    def test_ml_suggestion_without_deterministic_support_is_rejected(self):
        # ML lexically suggests a standby barrier; the deterministic dictionary
        # finds no barrier evidence in this phrasing -> must be rejected.
        text = "truck backed up with nobody directing traffic"
        result = S.suggest_and_validate(text, top_k=1)
        top = _top(result)
        self.assertIsNotNone(top)
        self.assertEqual(top["status"], "rejected")
        self.assertFalse(top["validation"]["accepted"])
        self.assertEqual(top["validation"]["validator"], "barrier_dictionary.detect_barriers")
        self.assertIn("deterministic_barriers_detected", top["validation"]["evidence"])

    def test_accepted_candidate_has_deterministic_support(self):
        text = "no lockout applied during pump repair"
        result = S.suggest_and_validate(text, top_k=1)
        top = _top(result)
        self.assertEqual(top["status"], "accepted")
        self.assertTrue(top["validation"]["accepted"])

    def test_validation_acceptance_rule_for_lsr(self):
        # Deterministic classifier must agree (primary match or score >= 3)
        text = "he descended into the vessel prior to atmosphere clearance"
        result = S.suggest_and_validate(text, top_k=1)
        top = _top(result)
        det = classify_life_saving_rule(text)
        agrees = (
            det["primary_rule"] == top["canonical_concept"]
            or det["scores"].get(top["canonical_concept"], 0) >= 3
        )
        self.assertEqual(top["status"], "accepted" if agrees else "rejected")

    def test_ml_cannot_invent_concept_type(self):
        from services.semantic_service import SemanticCandidate
        weird = SemanticCandidate(
            canonical_concept="Made Up Hazard", concept_type="unknown_type",
            confidence=0.99, source_text="x",
        )
        validated = S.validate_candidate(weird, "some text")
        self.assertEqual(validated.status, "rejected")

    def test_validation_is_independent_of_confidence_value(self):
        # Even a very high confidence candidate must be rejected without support
        from services.semantic_service import SemanticCandidate
        fake = SemanticCandidate(
            canonical_concept="Permit Not Obtained", concept_type="barrier_failure",
            confidence=0.99, source_text="x",
        )
        validated = S.validate_candidate(fake, "routine paperwork filing in the office")
        self.assertEqual(validated.status, "rejected")


class TestFallbackBehavior(SemanticTestBase):
    """Requirement 6: ML unavailable / model failure fallback."""

    def test_feature_flag_off_disables_ml(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"SAFESENSE_SEMANTIC_ML": "off"}):
            result = S.get_semantic_candidates("no lockout applied during pump repair")
            self.assertFalse(result["available"])
            self.assertEqual(result["candidates"], [])
            self.assertIn("SAFESENSE_SEMANTIC_ML", result["degraded_reason"])
            info = S.get_model_info()
            self.assertFalse(info["available"])

    def test_model_build_failure_degrades_gracefully(self):
        from unittest.mock import patch
        with patch("services.semantic_service._build_model", return_value=False):
            result = S.get_semantic_candidates("no lockout applied during pump repair")
            self.assertFalse(result["available"])
            self.assertEqual(result["candidates"], [])
            self.assertIsNotNone(result["degraded_reason"])

    def test_similarity_returns_none_when_unavailable(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"SAFESENSE_SEMANTIC_ML": "off"}):
            self.assertIsNone(S.semantic_text_similarity("a", "b"))

    def test_hybrid_similarity_falls_back_to_deterministic(self):
        rep1 = {"description": "worker entered tank without gas test"}
        rep2 = {"description": "entered the vessel with no gas testing"}
        with patch("services.semantic_service.semantic_text_similarity", return_value=None):
            res = S.hybrid_report_similarity(rep1, rep2)
        self.assertEqual(res["model"], "deterministic_fallback")
        self.assertIsNone(res["semantic_component"])
        self.assertGreater(res["similarity"], 0)

    def test_hybrid_similarity_combines_when_available(self):
        rep1 = {"description": "worker entered tank without gas test"}
        rep2 = {"description": "entered the vessel with no gas testing"}
        res = S.hybrid_report_similarity(rep1, rep2)
        self.assertEqual(res["model"], S.MODEL_ID)
        self.assertIsNotNone(res["semantic_component"])
        # Sanity: hybrid sits between its two components
        lex, sem, comb = res["lexical_component"], res["semantic_component"], res["similarity"]
        self.assertGreaterEqual(comb + 1e-9, min(lex, sem))
        self.assertLessEqual(comb - 1e-9, max(lex, sem))

    def test_semantic_signal_summary_has_safety_disclaimer(self):
        sig = S.summarize_semantic_signal(["worker entered tank without gas test"])
        self.assertIn("advisory", sig["note"].lower())
        self.assertIn("available", sig)


class TestDeterministicProtection(SemanticTestBase):
    """Requirements 7 & 8: deterministic behavior and risk/SIF regression."""

    def test_semantic_layer_never_changes_risk_or_sif(self):
        cases = [
            "worker entered tank without gas test",
            "no lockout applied during pump repair",
            "scaffold harness not tied off",
            "routine housekeeping inspection completed safely",
        ]
        for text in cases:
            before = analyze_report({"report_text": text})
            # Run the ML layer between two deterministic runs
            S.suggest_and_validate(text)
            S.hybrid_report_similarity(
                {"description": text}, {"description": text + " again"}
            )
            after = analyze_report({"report_text": text})
            self.assertEqual(before["risk_score"], after["risk_score"], text)
            self.assertEqual(before["sif_potential"], after["sif_potential"], text)
            self.assertEqual(before["life_saving_rule"], after["life_saving_rule"], text)

    def test_rule_classifier_baseline_unchanged(self):
        self.assertEqual(
            classify_life_saving_rule("worker entered tank without gas test")["primary_rule"],
            "Confined Space",
        )
        self.assertEqual(
            classify_life_saving_rule("no lockout applied during pump repair")["primary_rule"],
            "Energy Isolation",
        )
        self.assertEqual(
            classify_life_saving_rule("scaffold harness not tied off")["primary_rule"],
            "Working at Height",
        )

    def test_barrier_dictionary_baseline_unchanged(self):
        self.assertEqual(
            detect_barriers("worker entered tank without gas test"),
            ["Gas Testing Not Completed"],
        )
        self.assertEqual(
            detect_barriers("no lockout applied during pump repair"),
            ["Lockout/Tagout Not Completed"],
        )
        self.assertEqual(
            detect_barriers("scaffold harness not tied off"),
            ["Fall Protection Not Used"],
        )

    def test_sif_positive_case_still_classified(self):
        analysis = analyze_report(
            {"report_text": "Technician entered reactor vessel without permit and oxygen levels were not tested before entry."}
        )
        self.assertEqual(analysis["sif_potential"], "YES")

    def test_protected_modules_not_modified_by_semantic_layer(self):
        # The semantic service must not monkey-patch or wrap the safety engines.
        import services.rule_classifier as rc
        import services.barrier_dictionary as bd
        import services.risk_engine as re_mod
        for mod in (rc, bd, re_mod):
            self.assertNotIn("semantic_service", str(getattr(mod, "__dict__", {})))


class TestDeterminismAndStability(SemanticTestBase):
    """Requirement 9: repeated execution produces stable results."""

    def test_repeated_candidates_are_identical(self):
        text = "employee climbed up the storage rack with no fall protection gear"
        first = S.suggest_and_validate(text, top_k=3)
        for _ in range(3):
            again = S.suggest_and_validate(text, top_k=3)
            self.assertEqual(first, again)

    def test_similarity_is_symmetric_and_stable(self):
        a = "worker entered tank without gas test"
        b = "vessel entry performed before atmosphere was checked"
        s1 = S.semantic_text_similarity(a, b)
        s2 = S.semantic_text_similarity(b, a)
        s3 = S.semantic_text_similarity(a, b)
        self.assertIsNotNone(s1)
        self.assertAlmostEqual(s1, s2, places=6)
        self.assertEqual(s1, s3)

    def test_input_clipping_is_stable_for_long_text(self):
        text = "entered tank without gas test " * 500
        r1 = S.get_semantic_candidates(text, top_k=1)
        r2 = S.get_semantic_candidates(text, top_k=1)
        self.assertEqual(
            [c.to_dict() if hasattr(c, "to_dict") else c for c in r1["candidates"]],
            [c.to_dict() if hasattr(c, "to_dict") else c for c in r2["candidates"]],
        )


if __name__ == "__main__":
    unittest.main()
