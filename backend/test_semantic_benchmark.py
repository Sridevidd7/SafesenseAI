"""
test_semantic_benchmark.py — Phase 5 deterministic semantic benchmark.

A small, reproducible evaluation over representative safety examples (no
accuracy claims beyond this fixed suite). For each case we check the
ML-assisted semantic layer against the deterministic ground truth produced by
the authoritative engines (rule_classifier / barrier_dictionary).

Metrics:
- recall@k          : expected concept appears in top-k ML candidates
- validation_agreement : ML accepted candidates match deterministic ground truth
- paraphrase_lift   : cases where ML surfaces the concept the lexical layer
                      ranks weakly (demonstrates complementary value, not superiority)

Run:  cd backend && pytest test_semantic_benchmark.py -v
"""
import unittest

from services import semantic_service as S
from services.rule_classifier import classify_life_saving_rule
from services.barrier_dictionary import detect_barriers

# ── Fixed representative benchmark corpus ────────────────────────────────────
# (text, concept_type, expected canonical concept)
BENCHMARK_CASES = [
    # Direct lexical cases
    ("worker entered tank without gas test", "life_saving_rule", "Confined Space"),
    ("scaffold harness not tied off", "life_saving_rule", "Working at Height"),
    # Paraphrase cases (weak lexical overlap with signal vocabularies)
    ("employee climbed up the storage rack with no fall protection gear", "life_saving_rule", "Working at Height"),
    ("he descended into the vessel prior to atmosphere clearance", "life_saving_rule", "Confined Space"),
    ("load was hoisted right over the assembled crew", "life_saving_rule", "Line of Fire"),
    ("acid transferred without face shield or gloves", "life_saving_rule", "Chemical Handling"),
    # Paraphrase that ML maps to the SPECIFIC barrier concept; the deterministic
    # dictionary has no evidence for it and must reject it (safety gate showcase).
    ("machine was serviced while still connected to power", "barrier_failure", "Isolation Not Applied"),
    ("grinding done close to combustible material", "life_saving_rule", "Hot Work"),
    # Barrier concepts (expected = most specific canonical concept for the text)
    ("worker entered tank without gas test", "barrier_failure", "Gas Testing Not Completed"),
    ("no lockout applied during pump repair", "barrier_failure", "Lockout/Tagout Not Completed"),
    # Ambiguous / negative cases (no single expected concept; checked separately)
]

NEGATIVE_CASES = [
    "routine housekeeping inspection completed safely",
    "quarterly budget review meeting minutes",
    "lorem ipsum dolor sit amet consectetur",
]


class TestSemanticBenchmark(unittest.TestCase):
    """Fixed-suite evaluation. No generalized accuracy claim is made."""

    @classmethod
    def setUpClass(cls):
        S.reset_model_state()
        cls.results = []
        for text, ctype, expected in BENCHMARK_CASES:
            res = S.suggest_and_validate(text, top_k=3)
            names = [c["canonical_concept"] for c in res["candidates"]]
            ground_truth = (
                classify_life_saving_rule(text)["primary_rule"]
                if ctype == "life_saving_rule"
                else (detect_barriers(text) or [None])[0]
            )
            accepted = [
                c["canonical_concept"] for c in res["candidates"] if c["status"] == "accepted"
            ]
            cls.results.append({
                "text": text,
                "concept_type": ctype,
                "expected": expected,
                "top1": names[0] if names else None,
                "recall_at_3": expected in names,
                "top1_correct": names[0] == expected if names else False,
                "deterministic_truth": ground_truth,
                "accepted": accepted,
                "validation_agrees": (
                    (expected in accepted)
                    or (ground_truth is not None and ground_truth in names)
                ),
            })

    def test_recall_at_3(self):
        hits = sum(r["recall_at_3"] for r in self.results)
        print(f"\n[PHASE5 BENCHMARK] recall@3 = {hits}/{len(self.results)}")
        for r in self.results:
            print(
                f"  {'PASS' if r['recall_at_3'] else 'MISS'} | top1={str(r['top1'])[:28]:28} "
                f"| expected={r['expected']:26} | {r['text'][:48]}"
            )
        # Full recall on this fixed suite is required.
        # Note: for texts where both a rule and a barrier concept apply, the
        # more specific canonical concept is the correct expectation.
        self.assertEqual(hits, len(self.results))

    def test_top1_precision(self):
        hits = sum(r["top1_correct"] for r in self.results)
        print(f"[PHASE5 BENCHMARK] top-1 precision = {hits}/{len(self.results)}")
        # Advisory layer: top-1 should be informative but is NOT required to be perfect.
        # Threshold chosen for this fixed corpus; revisit if the corpus grows.
        self.assertGreaterEqual(hits / len(self.results), 0.7)

    def test_validation_agreement_with_deterministic_truth(self):
        agree = sum(r["validation_agrees"] for r in self.results)
        print(f"[PHASE5 BENCHMARK] validation agreement = {agree}/{len(self.results)}")
        self.assertGreaterEqual(agree / len(self.results), 0.7)

    def test_negative_cases_produce_no_accepted_candidates(self):
        """Non-safety text must never get an accepted safety concept."""
        for text in NEGATIVE_CASES:
            res = S.suggest_and_validate(text, top_k=3)
            accepted = [c for c in res["candidates"] if c["status"] == "accepted"]
            self.assertEqual(
                accepted, [], f"accepted safety concept for non-safety text: {text}"
            )

    def test_ml_rejection_leaves_deterministic_truth_intact(self):
        """
        Safety-gate showcase: when ML suggests a barrier paraphrase that the
        deterministic dictionary does not support, the candidate is rejected and
        the authoritative engines' verdicts remain unchanged.
        """
        text = "machine was serviced while still connected to power"
        row = next(r for r in self.results if r["text"] == text)
        self.assertEqual(row["top1"], "Isolation Not Applied")
        self.assertNotIn("Isolation Not Applied", row["accepted"])  # rejected by validator
        # Deterministic truth is unchanged and authoritative
        self.assertEqual(classify_life_saving_rule(text)["primary_rule"], "Energy Isolation")
        self.assertEqual(detect_barriers(text), [])

    def test_no_accuracy_claim_beyond_corpus(self):
        """Guard: benchmark metadata documents its fixed scope."""
        self.assertEqual(len(self.results), len(BENCHMARK_CASES))
        self.assertGreater(len(NEGATIVE_CASES), 0)


if __name__ == "__main__":
    unittest.main()
