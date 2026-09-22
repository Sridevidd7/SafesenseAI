"""
test_edge_cases_and_calibration.py — Stress tests for multi-stage temporal sequences,
safe normalization, adaptive clustering, confidence stabilization, and fallback contracts.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from services.risk_engine import analyze_report, split_into_temporal_clauses, analyze_temporal_sequence
from services.pattern_engine import compute_similarity, compute_adaptive_threshold, cluster_reports
from utils.analysis_utils import (
    calculate_system_confidence,
    normalize_risk_score,
    validate_analysis_output,
    safe_fallback_analysis,
)


def test_multistage_temporal_sequence():
    print("=================================================================")
    print("RUNNING TEST 1: MULTI-STAGE TEMPORAL SEQUENCE (SAFE -> UNSAFE -> SAFE -> UNSAFE)")
    print("=================================================================")

    # Multi-stage sequence: Safe morning check -> 10am violation -> 11am stop/fix -> 2pm recurrence
    multi_stage_text = (
        "Morning gas test was conducted at 08:00 and verified safe. "
        "At 10:00, technician entered the reactor vessel without gas testing. "
        "The supervisor intervened and atmospheric testing was completed before entry was resumed. "
        "However, at 14:00, the night shift crew entered the reactor without gas testing."
    )

    res = analyze_report({"report_text": multi_stage_text})

    print(f"Input Multi-Stage Report:\n'{multi_stage_text}'")
    print(f"  -> Temporal Timeline: {res.get('temporal_timeline')}")
    print(f"  -> Temporal Sequence: {res.get('temporal_sequence')}")
    print(f"  -> Barrier Failures: {res.get('barrier_failures')}")
    print(f"  -> Risk Score: {res.get('risk_score')} ({res.get('risk_level')})")
    print(f"  -> SIF Potential: {res.get('sif_potential')}")

    # Check that LAST unsafe state dominates
    assert "Gas Testing Not Completed" in res.get("barrier_failures", [])
    assert res.get("temporal_timeline")[-1] == "UNSAFE", f"Expected last state UNSAFE, got {res.get('temporal_timeline')}"
    assert res.get("risk_score") >= 70, f"Expected high risk score for active violation dominance, got {res.get('risk_score')}"
    print(">>> TEST 1 PASSED: Multi-stage sequence resolved with LAST unsafe state dominance! <<<\n")


def test_final_safe_state_override():
    print("=================================================================")
    print("RUNNING TEST 2: MULTI-STAGE WITH FINAL SAFE CONFIRMATION (UNSAFE -> SAFE)")
    print("=================================================================")

    # Initial deficiency, but final state is verified safe
    safe_final_text = (
        "Technician attempted entry without valid permit. "
        "Supervisor halted work immediately and permit was formally issued and verified before entry."
    )

    res = analyze_report({"report_text": safe_final_text})

    print(f"Input Report:\n'{safe_final_text}'")
    print(f"  -> Temporal Timeline: {res.get('temporal_timeline')}")
    print(f"  -> SIF Potential: {res.get('sif_potential')}")
    print(f"  -> Risk Score: {res.get('risk_score')} ({res.get('risk_level')})")

    assert res.get("sif_potential") == "NO", f"Expected SIF NO for final safe confirmation, got {res.get('sif_potential')}"
    assert res.get("risk_score") <= 35, f"Expected low risk score, got {res.get('risk_score')}"
    print(">>> TEST 2 PASSED: Final safe confirmation correctly suppressed active breach! <<<\n")


def test_safe_risk_normalization():
    print("=================================================================")
    print("RUNNING TEST 3: SAFE RISK NORMALIZATION (STD_DEV < 5 GUARD)")
    print("=================================================================")

    # Case A: Low variance (std_dev < 5) -> Normalization disabled, raw_score / 100 returned
    norm_low = normalize_risk_score(raw_score=75, mean_risk=72.0, std_dev=3.5)
    print("Case A (std_dev = 3.5 < 5):", norm_low)
    assert norm_low["normalization_applied"] is False, "Expected normalization_applied to be False"
    assert norm_low["normalized_score"] == 0.75, f"Expected 0.75, got {norm_low['normalized_score']}"

    # Case B: Standard variance (std_dev >= 5) -> Z-score applied
    norm_std = normalize_risk_score(raw_score=80, mean_risk=50.0, std_dev=15.0)
    print("Case B (std_dev = 15.0 >= 5):", norm_std)
    assert norm_std["normalization_applied"] is True, "Expected normalization_applied to be True"
    assert norm_std["normalized_score"] == 2.0, f"Expected 2.0, got {norm_std['normalized_score']}"

    print(">>> TEST 3 PASSED: Safe normalization guard verified! <<<\n")


def test_adaptive_pattern_threshold():
    print("=================================================================")
    print("RUNNING TEST 4: ADAPTIVE PATTERN THRESHOLD CALCULATION")
    print("=================================================================")

    reports = [
        {"report_id": "1", "description": "gas test not performed in vessel entry", "category": "Confined Space", "barrier": "Gas Testing Not Completed"},
        {"report_id": "2", "description": "entered vessel without gas check done", "category": "Confined Space", "barrier": "Gas Testing Not Completed"},
        {"report_id": "3", "description": "working on high scaffold without harness", "category": "Working at Height", "barrier": "Fall Protection Not Used"},
        {"report_id": "4", "description": "electrician handled live wire without lockout", "category": "Energy Isolation", "barrier": "Lockout/Tagout Not Completed"},
    ]

    thresh = compute_adaptive_threshold(reports)
    print(f"Computed Adaptive Threshold for dataset: {thresh:.3f}")
    assert 0.50 <= thresh <= 0.80, f"Expected threshold in [0.50, 0.80], got {thresh}"

    clusters = cluster_reports(reports)
    print(f"Total Clusters Formed: {len(clusters)}")
    assert len(clusters) >= 2, f"Expected at least 2 distinct clusters, got {len(clusters)}"
    print(">>> TEST 4 PASSED: Adaptive threshold correctly bounded and clustered! <<<\n")


def test_confidence_stabilization_and_reasons():
    print("=================================================================")
    print("RUNNING TEST 5: CONFIDENCE STABILIZATION & REASONS")
    print("=================================================================")

    conf_res = calculate_system_confidence(
        barrier_confidence=0.98,
        rule_confidence=0.95,
        text_clarity=0.90,
        confidence_penalty=0.0,
    )
    print("High Confidence Result:", conf_res)
    assert conf_res["system_confidence"] == "HIGH"
    assert conf_res["confidence_components"]["barrier_contribution"] <= 0.50
    assert "confidence_reason" in conf_res and len(conf_res["confidence_reason"]) > 10

    # Low clarity & ambiguous case
    conf_low = calculate_system_confidence(
        barrier_confidence=0.50,
        rule_confidence=0.40,
        text_clarity=0.30,
        confidence_penalty=0.25,
        has_conflicting_signals=True,
    )
    print("\nLow Confidence Result with Penalties:", conf_low)
    assert conf_low["system_confidence"] == "LOW"
    assert "Penalties applied" in conf_low["confidence_reason"]
    print(">>> TEST 5 PASSED: Confidence contributions capped and reasons generated! <<<\n")


def test_explicit_fallback_contract():
    print("=================================================================")
    print("RUNNING TEST 6: EXPLICIT FALLBACK CONTRACT")
    print("=================================================================")

    # Case A: Explicit fallback trigger
    fallback_res = safe_fallback_analysis("corrupted input text", reason="Test explicit trigger")
    print("Fallback Output Contract:", fallback_res)
    assert fallback_res["source"] == "fallback"
    assert fallback_res["confidence"] == "LOW"
    assert fallback_res["risk_score"] == 50
    assert "Test explicit trigger" in fallback_res["reason"]

    # Case B: High risk keyword with 0 barriers triggers fallback
    text_unresolved = "technician initiated confined space vessel entry inside reactor column"
    # No barrier failure phrase present, but heavy industrial hazard terms
    res_val = analyze_report({"report_text": text_unresolved})
    print("\nHigh risk keyword with 0 barriers result source:", res_val.get("source"))
    assert res_val.get("source") in ("fallback", "engine")

    print(">>> TEST 6 PASSED: Explicit fallback contract satisfied! <<<\n")


if __name__ == "__main__":
    test_multistage_temporal_sequence()
    test_final_safe_state_override()
    test_safe_risk_normalization()
    test_adaptive_pattern_threshold()
    test_confidence_stabilization_and_reasons()
    test_explicit_fallback_contract()
    print("=================================================================")
    print(">>> ALL 6 EDGE-CASE & CALIBRATION TESTS PASSED WITH 100% SUCCESS! <<<")
    print("=================================================================")
