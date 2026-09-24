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


def test_required_validation_cases_1_to_7():
    print("=================================================================")
    print("RUNNING TEST 7: REQUIRED CONCEPTUAL CASES 1 TO 7")
    print("=================================================================")

    # Case 1: Trivial observation
    c1 = analyze_report({"report_text": "An employee noticed a small piece of paper on the floor near the office entrance and picked it up immediately. No one was exposed to harm."})
    assert c1["risk_level"] == "LOW", f"Case 1 expected LOW, got {c1['risk_level']} (score {c1['risk_score']})"
    assert c1["risk_score"] <= 30, f"Case 1 score should be <= 30, got {c1['risk_score']}"
    assert c1["sif_potential"] == "NO", f"Case 1 SIF should be NO, got {c1['sif_potential']}"
    assert len(c1["barrier_failures"]) == 0, f"Case 1 should have no false barrier failures, got {c1['barrier_failures']}"

    # Case 2: Low-risk near miss
    c2 = analyze_report({"report_text": "An employee noticed an extension cord across a walkway and moved it before anyone tripped."})
    assert c2["risk_level"] == "LOW", f"Case 2 expected LOW, got {c2['risk_level']} (score {c2['risk_score']})"
    assert c2["risk_score"] <= 30, f"Case 2 score should be <= 30, got {c2['risk_score']}"
    assert c2["sif_potential"] == "NO", f"Case 2 SIF should be NO, got {c2['sif_potential']}"
    assert len(c2["barrier_failures"]) == 0, f"Case 2 should have no false barrier failures, got {c2['barrier_failures']}"

    # Case 3: Unsafe PPE act
    c3 = analyze_report({"report_text": "Technician was grinding a metal bracket without approved safety glasses."})
    assert c3["risk_level"] in ("HIGH", "CRITICAL"), f"Case 3 expected HIGH/CRITICAL, got {c3['risk_level']}"
    assert c3["life_saving_rule"] == "Hot Work", f"Case 3 expected Hot Work, got {c3['life_saving_rule']}"
    assert any("PPE" in b for b in c3["barrier_failures"]), f"Case 3 expected PPE barrier failure, got {c3['barrier_failures']}"

    # Case 4: Serious event without intervention
    c4 = analyze_report({"report_text": "Worker entered a confined space without gas testing and without a permit. Work continued."})
    assert c4["risk_level"] in ("HIGH", "CRITICAL"), f"Case 4 expected HIGH/CRITICAL, got {c4['risk_level']}"
    assert c4["sif_potential"] == "YES", f"Case 4 expected SIF YES, got {c4['sif_potential']}"
    assert any("Gas Testing" in b for b in c4["barrier_failures"]), f"Case 4 expected Gas Testing barrier, got {c4['barrier_failures']}"
    assert c4["temporal_sequence"] == "PURE_UNSAFE"

    # Case 5: Serious event with intervention AFTER exposure
    c5 = analyze_report({"report_text": "Worker entered a confined space without gas testing and without a permit. Supervisor immediately stopped the work."})
    assert c5["risk_level"] in ("HIGH", "CRITICAL"), f"Case 5 expected HIGH/CRITICAL, got {c5['risk_level']} (score {c5['risk_score']})"
    assert c5["sif_potential"] == "YES", f"Case 5 expected SIF YES, got {c5['sif_potential']}"
    assert any("Gas Testing" in b for b in c5["barrier_failures"]), f"Case 5 expected Gas Testing barrier preserved, got {c5['barrier_failures']}"
    assert c5["temporal_sequence"] == "UNSAFE_WITH_INTERVENTION", f"Case 5 expected UNSAFE_WITH_INTERVENTION, got {c5['temporal_sequence']}"
    assert "INHERENT RISK DETECTED WITH SUBSEQUENT INTERVENTION" in c5["explanation"]
    assert c5["risk_score"] >= 70, f"Case 5 score should remain >= 70, got {c5['risk_score']}"

    # Case 6: Prevention BEFORE exposure
    c6 = analyze_report({"report_text": "Supervisor noticed a worker preparing to enter a confined space without gas testing and stopped the worker before entry."})
    assert c6["risk_level"] == "LOW", f"Case 6 expected LOW, got {c6['risk_level']} (score {c6['risk_score']})"
    assert c6["sif_potential"] == "NO", f"Case 6 expected SIF NO, got {c6['sif_potential']}"
    assert c6["temporal_sequence"] in ("PREVENTIVE_BEFORE_EXPOSURE", "PURE_SAFE")
    assert c6["barrier_failures"] == ["Prevented: Gas Testing Not Completed"], f"Expected prevented barrier, got {c6['barrier_failures']}"
    assert c6["barrier_failure"] == "Prevented: Gas Testing Not Completed"
    assert "Gas Testing Not Completed" in c6["risk_reason"]
    assert any("without gas testing" in ep for ep in c6["evidence_phrases"])

    # Case 7: Existing high-risk regression
    c7 = analyze_report({"report_text": "Two contract workers entered a crude oil storage tank for sludge removal without atmospheric gas testing and without confined space entry permit. No standby person present at the manhole."})
    assert c7["risk_level"] == "CRITICAL", f"Case 7 expected CRITICAL, got {c7['risk_level']}"
    assert c7["sif_potential"] == "YES", f"Case 7 expected SIF YES, got {c7['sif_potential']}"
    assert len(c7["barrier_failures"]) >= 3, f"Case 7 expected 3 barrier failures, got {c7['barrier_failures']}"

    print(">>> TEST 7 PASSED: All 7 Required Conceptual Cases verified! <<<\n")


def test_temporal_generalization_unseen_paraphrases():
    print("=================================================================")
    print("RUNNING TEST 8: UNSEEN GENERALIZATION PARAPHRASES")
    print("=================================================================")

    # Para 1: Management intervened and halted the operation
    p1 = analyze_report({"report_text": "Worker entered the vessel without gas testing. Management intervened and halted the operation."})
    assert p1["temporal_sequence"] == "UNSAFE_WITH_INTERVENTION"
    assert p1["risk_level"] in ("HIGH", "CRITICAL")
    assert p1["sif_potential"] == "YES"
    assert any("Gas Testing" in b for b in p1["barrier_failures"])

    # Para 2: Work was suspended after unsafe condition occurred
    p2 = analyze_report({"report_text": "Technician operated live circuit without lockout. Work was suspended after the unsafe condition had already occurred."})
    assert p2["temporal_sequence"] == "UNSAFE_WITH_INTERVENTION"
    assert p2["risk_level"] in ("HIGH", "CRITICAL")
    assert p2["sif_potential"] == "YES"
    assert any("Lockout" in b for b in p2["barrier_failures"])

    # Para 3: Prevented from entering
    p3 = analyze_report({"report_text": "The operator was prevented from entering the vessel without gas testing."})
    assert p3["temporal_sequence"] == "PREVENTIVE_BEFORE_EXPOSURE"
    assert p3["risk_level"] == "LOW"
    assert p3["sif_potential"] == "NO"

    # Para 4: Stopped before anyone entered
    p4 = analyze_report({"report_text": "The activity was stopped before anyone entered the tank without a permit."})
    assert p4["temporal_sequence"] == "PREVENTIVE_BEFORE_EXPOSURE"
    assert p4["risk_level"] == "LOW"
    assert p4["sif_potential"] == "NO"

    # Para 5: Workers had already entered when supervisor intervened
    p5 = analyze_report({"report_text": "Workers had already entered the confined space without gas testing when the supervisor intervened."})
    assert p5["temporal_sequence"] == "UNSAFE_WITH_INTERVENTION"
    assert p5["risk_level"] in ("HIGH", "CRITICAL")
    assert p5["sif_potential"] == "YES"

    # Para 6: Preparing to enter but stopped before entry
    p6 = analyze_report({"report_text": "Personnel were preparing to enter the vessel without gas testing but were stopped before entry."})
    assert p6["temporal_sequence"] == "PREVENTIVE_BEFORE_EXPOSURE"
    assert p6["risk_level"] == "LOW"
    assert p6["sif_potential"] == "NO"

    print(">>> TEST 8 PASSED: Unseen temporal paraphrases generalized accurately! <<<\n")


def test_adversarial_generalization_scenarios():
    print("=================================================================")
    print("RUNNING TEST 9: ADVERSARIAL GENERALIZATION SCENARIOS")
    print("=================================================================")

    # Adv 1: Minor housekeeping hazard immediately corrected
    adv1 = analyze_report({"report_text": "An employee noticed some loose dust and sweeping debris in the hallway and swept it up immediately."})
    assert adv1["risk_level"] == "LOW"
    assert adv1["sif_potential"] == "NO"
    assert adv1["barrier_failures"] == []

    # Adv 2: Minor hazard where exposure actually occurred
    adv2 = analyze_report({"report_text": "An employee stumbled over an uneven floor tile in the hallway but sustained no injury."})
    assert adv2["risk_level"] == "LOW"
    assert adv2["sif_potential"] == "NO"
    assert adv2["barrier_failures"] == []

    # Adv 3: Unsafe act stopped before exposure
    adv3 = analyze_report({"report_text": "Electrician was preparing to service an energized electrical panel without lockout tagout, but the supervisor intervened before any work began."})
    assert adv3["risk_level"] == "LOW"
    assert adv3["sif_potential"] == "NO"
    assert adv3["temporal_sequence"] in ("PREVENTIVE_BEFORE_EXPOSURE", "PURE_SAFE")

    # Adv 4: Unsafe act stopped after exposure
    adv4 = analyze_report({"report_text": "Electrician began working on a 415V distribution board without lockout tagout. Supervisor intervened and halted the job."})
    assert adv4["risk_level"] in ("HIGH", "CRITICAL")
    assert adv4["sif_potential"] == "YES"
    assert adv4["temporal_sequence"] == "UNSAFE_WITH_INTERVENTION"

    # Adv 5: Severe barrier failure followed by intervention
    adv5 = analyze_report({"report_text": "Two technicians entered a chemical storage tank without atmospheric gas testing and without safety harnesses. Safety officer immediately ordered a stop-work."})
    assert adv5["risk_level"] in ("HIGH", "CRITICAL")
    assert adv5["sif_potential"] == "YES"
    assert adv5["temporal_sequence"] == "UNSAFE_WITH_INTERVENTION"
    assert len(adv5["barrier_failures"]) >= 2

    print(">>> TEST 9 PASSED: All 5 Adversarial Generalization scenarios verified! <<<\n")


if __name__ == "__main__":
    test_temporal_contradiction()
    test_temporal_safe_resolution()
    test_long_paragraph_noise_reduction()
    test_adversarial_and_unclear_inputs()
    test_pattern_engine_clustering()
    test_risk_normalization_and_validation()
    test_required_validation_cases_1_to_7()
    test_temporal_generalization_unseen_paraphrases()
    test_adversarial_generalization_scenarios()
    print("=================================================================")
    print(">>> ALL 9 ROBUSTNESS, TEMPORAL & GENERALIZATION TESTS PASSED! <<<")
    print("=================================================================")
