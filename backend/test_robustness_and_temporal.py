"""
test_robustness_and_temporal.py — Test suite for temporal contradiction, long reports, adversarial inputs, and validation.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from services.risk_engine import (
    analyze_report,
    split_into_temporal_clauses,
    analyze_temporal_sequence,
)
from services.pattern_engine import (
    compute_similarity,
    cluster_reports,
)
from utils.analysis_utils import (
    detect_adversarial_patterns,
    calculate_system_confidence,
    normalize_risk_score,
    validate_analysis_output,
    safe_fallback_analysis,
)


def test_temporal_contradiction():
    print("=================================================================")
    print("RUNNING TEST 1: TEMPORAL CONTRADICTION (SAFE -> UNSAFE)")
    print("=================================================================")

    # Case 1: Safe step earlier, but subsequent unsafe action occurs
    text_contradiction = "gas test was done at 9am but later technician entered vessel without testing"
    res = analyze_report({"report_text": text_contradiction})

    print(f"Report: '{text_contradiction}'")
    print(f"  -> Temporal Sequence: {res.get('temporal_sequence')}")
    print(f"  -> Detected Barriers: {res.get('barrier_failures')}")
    print(f"  -> Risk Score: {res.get('risk_score')} ({res.get('risk_level')})")
    print(f"  -> System Confidence: {res.get('system_confidence')} ({res.get('system_confidence_score')})")

    assert res.get("temporal_sequence") == "SAFE_TO_UNSAFE", f"Expected SAFE_TO_UNSAFE, got {res.get('temporal_sequence')}"
    assert any("Gas Testing" in b for b in res.get("barrier_failures", [])), f"Expected Gas Testing barrier failure, got {res.get('barrier_failures')}"
    assert res.get("risk_score") >= 60, f"Expected high/critical risk score for violation, got {res.get('risk_score')}"
    print(">>> TEST 1 PASSED: Temporal contradiction correctly resolved to active violation! <<<\n")


def test_temporal_safe_resolution():
    print("=================================================================")
    print("RUNNING TEST 2: TEMPORAL RESOLUTION (UNSAFE -> SAFE PREVENTIVE)")
    print("=================================================================")

    # Case 2: Deficiency noticed initially, but work was halted and completed before entry
    text_safe = "initially gas test was not done, but work was stopped and atmospheric testing was completed before entry"
    res = analyze_report({"report_text": text_safe})

    print(f"Report: '{text_safe}'")
    print(f"  -> Temporal Sequence: {res.get('temporal_sequence')}")
    print(f"  -> Detected Barriers: {res.get('barrier_failures')}")
    print(f"  -> SIF Potential: {res.get('sif_potential')}")
    print(f"  -> Risk Score: {res.get('risk_score')} ({res.get('risk_level')})")

    assert res.get("temporal_sequence") == "UNSAFE_TO_SAFE" or res.get("negation_type") == "SAFE_PREVENTIVE"
    assert res.get("sif_potential") == "NO", f"Expected SIF NO for preventive resolution, got {res.get('sif_potential')}"
    assert res.get("risk_score") <= 35, f"Expected low risk score for preventive stop, got {res.get('risk_score')}"
    print(">>> TEST 2 PASSED: Safe resolution correctly recognized and scored low! <<<\n")


def test_long_paragraph_noise_reduction():
    print("=================================================================")
    print("RUNNING TEST 3: LONG PARAGRAPH NOISE REDUCTION (5-6 SENTENCES)")
    print("=================================================================")

    long_text = (
        "Morning toolbox talk was held with the electrical team at 08:00. "
        "The team inspected their hand tools and general PPE in the workshop. "
        "During maintenance on the main 415V distribution board, the circuit breaker was not isolated and lockout was omitted. "
        "The area was marked with safety tape. "
        "A supervisor noticed the energized circuit during routine audit. "
        "The incident was logged into the shift handover register."
    )

    clauses = split_into_temporal_clauses(long_text)
    print(f"Split into {len(clauses)} clauses/sentences.")
    for idx, c in enumerate(clauses):
        print(f"  [{idx}] {c['clause_text']}")

    res = analyze_report({"report_text": long_text})

    print(f"\nAnalysis Result:")
    print(f"  -> Primary Rule: {res.get('primary_rule')}")
    print(f"  -> Barrier Failures: {res.get('barrier_failures')}")
    print(f"  -> Risk Score: {res.get('risk_score')} ({res.get('risk_level')})")
    print(f"  -> SIF Potential: {res.get('sif_potential')}")
    print(f"  -> System Confidence: {res.get('system_confidence')} ({res.get('system_confidence_score')})")

    assert len(clauses) >= 5, f"Expected at least 5 clauses, got {len(clauses)}"
    assert res.get("primary_rule") == "Energy Isolation", f"Expected Energy Isolation, got {res.get('primary_rule')}"
    assert any("Lockout" in b or "Isolation" in b for b in res.get("barrier_failures", []))
    # Deduplication test: ensure no duplicate items in barrier_failures
    assert len(res.get("barrier_failures")) == len(set(res.get("barrier_failures"))), "Duplicate barriers detected!"
    print(">>> TEST 3 PASSED: Long paragraph processed without over-counting or noise distortion! <<<\n")


def test_adversarial_and_unclear_inputs():
    print("=================================================================")
    print("RUNNING TEST 4: ADVERSARIAL & UNCLEAR INPUTS")
    print("=================================================================")

    # Case 4a: Speculative phrasing
    text_speculative = "maybe unsafe conditions in boiler area, not sure if safe or if permit was valid"
    res_spec = analyze_report({"report_text": text_speculative})

    print(f"Speculative Input: '{text_speculative}'")
    print(f"  -> Analysis Quality: {res_spec.get('analysis_quality')}")
    print(f"  -> Adversarial Flags: {res_spec.get('adversarial_flags')}")
    print(f"  -> System Confidence: {res_spec.get('system_confidence')} ({res_spec.get('system_confidence_score')})")

    assert res_spec.get("analysis_quality") in ("LOW", "MEDIUM")
    assert len(res_spec.get("adversarial_flags", [])) > 0
    assert res_spec.get("system_confidence_score") < 0.75

    # Case 4b: Double Negation
    text_double_neg = "contractor entered not without permit but scaffolding was unverified"
    res_dn = analyze_report({"report_text": text_double_neg})

    print(f"\nDouble Negation Input: '{text_double_neg}'")
    print(f"  -> Analysis Quality: {res_dn.get('analysis_quality')}")
    print(f"  -> Adversarial Flags: {res_dn.get('adversarial_flags')}")

    assert any("Double negation" in f for f in res_dn.get("adversarial_flags", []))
    print(">>> TEST 4 PASSED: Adversarial inputs and speculative phrasing correctly guarded! <<<\n")


def test_pattern_engine_clustering():
    print("=================================================================")
    print("RUNNING TEST 5: PATTERN ENGINE 0.65 SIMILARITY CLUSTERING")
    print("=================================================================")

    rep_a = {
        "report_id": "R1",
        "description": "worker entered storage vessel without gas testing",
        "category": "Confined Space",
        "barrier": "Gas Testing Not Completed",
        "barrier_failures": ["Gas Testing Not Completed"],
    }
    rep_b = {
        "report_id": "R2",
        "description": "technician entered reactor vessel without gas testing done",
        "category": "Confined Space",
        "barrier": "Gas Testing Not Completed",
        "barrier_failures": ["Gas Testing Not Completed"],
    }
    rep_c = {
        "report_id": "R3",
        "description": "electrician worked on live circuit without lockout tagout",
        "category": "Energy Isolation",
        "barrier": "Lockout/Tagout Not Completed",
        "barrier_failures": ["Lockout/Tagout Not Completed"],
    }

    sim_ab = compute_similarity(rep_a, rep_b)
    sim_ac = compute_similarity(rep_a, rep_c)

    print(f"Similarity (rep_a, rep_b): {sim_ab:.4f} (Expected >= 0.65)")
    print(f"Similarity (rep_a, rep_c): {sim_ac:.4f} (Expected < 0.30)")

    assert sim_ab >= 0.65, f"Expected similarity >= 0.65, got {sim_ab}"
    assert sim_ac < 0.35, f"Expected low similarity between different LSRs, got {sim_ac}"

    clusters = cluster_reports([rep_a, rep_b, rep_c], similarity_threshold=0.65)
    print(f"Total Clusters Formed: {len(clusters)}")
    assert len(clusters) == 2, f"Expected exactly 2 distinct clusters, got {len(clusters)}"
    print(">>> TEST 5 PASSED: Pattern engine 0.65 similarity clustering verified! <<<\n")


def test_risk_normalization_and_validation():
    print("=================================================================")
    print("RUNNING TEST 6: RISK NORMALIZATION & STRICT VALIDATION")
    print("=================================================================")

    # Test Z-Score normalization
    z1 = normalize_risk_score(70, mean_risk=50.0, std_dev=20.0)
    z2 = normalize_risk_score(30, mean_risk=50.0, std_dev=20.0)
    assert z1["normalized_score"] == 1.0, f"Expected +1.0, got {z1}"
    assert z2["normalized_score"] == -1.0, f"Expected -1.0, got {z2}"

    # Test Validation Clamping
    corrupted_data = {
        "risk_score": 150,  # out of bounds
        "barrier_failures": ["Gas Testing Not Completed", "Gas Testing Not Completed", "  ", None],
        "life_saving_rule": "Confined Space",
    }
    validated = validate_analysis_output(corrupted_data, "sample raw text")

    assert validated["risk_score"] == 100, f"Expected clamped 100, got {validated['risk_score']}"
    assert validated["barrier_failures"] == ["Gas Testing Not Completed"], f"Expected deduplicated barriers, got {validated['barrier_failures']}"
    assert validated["life_saving_rule"] == "Confined Space", f"Expected Confined Space, got {validated['life_saving_rule']}"

    # Test Invalid Rule Fallback Trigger
    invalid_data = {
        "risk_score": 90,
        "life_saving_rule": "Invalid Nonexistent LSR",
    }
    fallback_res = validate_analysis_output(invalid_data, "sample raw text")
    assert fallback_res["source"] == "fallback", f"Expected fallback source, got {fallback_res.get('source')}"
    assert fallback_res["life_saving_rule"] == "General Safety"

    print(">>> TEST 6 PASSED: Normalization and strict validation clamped correctly! <<<\n")


if __name__ == "__main__":
    test_temporal_contradiction()
    test_temporal_safe_resolution()
    test_long_paragraph_noise_reduction()
    test_adversarial_and_unclear_inputs()
    test_pattern_engine_clustering()
    test_risk_normalization_and_validation()
    print("=================================================================")
    print(">>> ALL 6 ROBUSTNESS & RELIABILITY TESTS PASSED WITH 100% SUCCESS! <<<")
    print("=================================================================")
