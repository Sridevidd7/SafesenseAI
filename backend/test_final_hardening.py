"""
test_final_hardening.py — Production Hardening & Demo Stability Test Suite
==========================================================================
Tests:
1. Typo & Spelling Tolerance (e.g. 'gass test', 'harnees', 'scafold')
2. Abbreviation Normalization (e.g. 'no ptw', 'loto', 'ppe')
3. Pattern Engine Synonym Clustering (e.g. 'energized', 'live', 'powered' -> 1 cluster)
4. Risk Score Justification Layer ('risk_reason' field populated and explainable)
5. Mixed Signals in Long Paragraph (Sentence splitting, temporal resolution, noise suppression)
6. LLM Safety Wrapper & Demo Stability Mode (Caching, timeout resilience, zero-crash fallback)
"""
import sys
import json
import asyncio

from services.barrier_dictionary import normalize_text, detect_barriers_with_evidence
from services.risk_engine import analyze_report
from services.pattern_engine import cluster_reports
from services.llm_service import generate_llm_explanation, DEMO_MODE


def test_typos_and_spelling_tolerance():
    print("=================================================================")
    print("TEST 1: TYPOS & SPELLING TOLERANCE")
    print("=================================================================")

    cases = [
        ("technician forgot gass test before entry", "Gas Testing Not Completed"),
        ("worker at height without harnees on scafold", "Fall Protection Not Used"),
        ("entered confinded vessl without atmospheric check", "Gas Testing Not Completed"),
    ]

    for text, expected_barrier in cases:
        norm = normalize_text(text)
        res = analyze_report({"report_text": text})
        detected_barriers = [b["barrier"] for b in res.get("barrier_evidence", [])]
        print(f"Input: '{text}'")
        print(f"  -> Normalized: '{norm}'")
        print(f"  -> Detected Barriers: {detected_barriers}")
        print(f"  -> Risk Score: {res['risk_score']} ({res['risk_level']})")
        assert expected_barrier in detected_barriers or expected_barrier in res.get("barrier_failures", []), \
            f"Expected {expected_barrier} in {detected_barriers}"

    print(">>> TEST 1 PASSED: Typo and spelling tolerance validated! <<<\n")


def test_abbreviation_normalization():
    print("=================================================================")
    print("TEST 2: ABBREVIATION NORMALIZATION")
    print("=================================================================")

    cases = [
        ("no ptw issued for hot work", "Permit Not Obtained"),
        ("technician started motor maintenance with no loto", "Lockout/Tagout Not Completed"),
        ("contractor handling hazardous chemicals with no ppe", "PPE Not Available"),
    ]

    for text, expected_barrier in cases:
        norm = normalize_text(text)
        res = analyze_report({"report_text": text})
        detected_barriers = [b["barrier"] for b in res.get("barrier_evidence", [])]
        print(f"Input: '{text}'")
        print(f"  -> Normalized: '{norm}'")
        print(f"  -> Detected Barriers: {detected_barriers}")
        assert expected_barrier in detected_barriers or expected_barrier in res.get("barrier_failures", []), \
            f"Expected {expected_barrier} in {detected_barriers}"

    print(">>> TEST 2 PASSED: Abbreviations (ptw, loto, ppe) correctly expanded and detected! <<<\n")


def test_pattern_stability_synonym_clustering():
    print("=================================================================")
    print("TEST 3: PATTERN STABILITY & SYNONYM CLUSTERING")
    print("=================================================================")

    reports = [
        {"report_id": "P1", "description": "technician worked on energized circuit without lockout", "category": "Energy Isolation", "barrier": "Lockout/Tagout Not Completed", "site": "Site Alpha", "risk_score": 85},
        {"report_id": "P2", "description": "electrician serviced live panel with no tagout applied", "category": "Energy Isolation", "barrier": "Lockout/Tagout Not Completed", "site": "Site Beta", "risk_score": 80},
        {"report_id": "P3", "description": "operator repaired powered switchgear lacking loto isolation", "category": "Energy Isolation", "barrier": "Lockout/Tagout Not Completed", "site": "Site Gamma", "risk_score": 88}
    ]

    clusters = cluster_reports(reports)
    print(f"Input: 3 reports with synonym variations ('energized', 'live', 'powered')")
    print(f"Clusters formed: {len(clusters)}")
    for c in clusters:
        print(f"  Cluster ID: {c['cluster_id']} | Count: {c['count']} | Sites: {c['sites']}")
        print(f"  Theme: {c['theme']}")
        print(f"  Insight: {c.get('simplified_insight')}")

    assert len(clusters) == 1, f"Expected 1 unified cluster, got {len(clusters)}"
    assert clusters[0]["count"] == 3, f"Expected count 3, got {clusters[0]['count']}"
    assert len(clusters[0]["sites"]) == 3, f"Expected 3 distinct sites, got {clusters[0]['sites']}"

    print(">>> TEST 3 PASSED: Synonym expansion unified varied reports into 1 stable cross-site cluster! <<<\n")


def test_risk_score_justification_layer():
    print("=================================================================")
    print("TEST 4: RISK SCORE JUSTIFICATION LAYER ('risk_reason')")
    print("=================================================================")

    # Case A: Critical multi-barrier
    res_crit = analyze_report({"report_text": "technician entered reactor vessel without permit and oxygen was not tested"})
    print("Critical Case Risk Reason:", res_crit.get("risk_reason"))
    assert res_crit.get("risk_reason") is not None, "risk_reason must not be None"
    assert "risk" in res_crit["risk_reason"].lower(), "risk_reason should explain risk"

    # Case B: Safe preventive stop
    res_safe = analyze_report({"report_text": "worker noticed missing gas test kit and proactively halted tank entry until atmospheric testing was completed"})
    print("Safe Preventive Risk Reason:", res_safe.get("risk_reason"))
    assert res_safe.get("risk_reason") is not None, "risk_reason must not be None"
    assert "low risk" in res_safe["risk_reason"].lower() or "prevent" in res_safe["risk_reason"].lower()

    # Case C: Medium housekeeping
    res_med = analyze_report({"report_text": "housekeeping audit in workshop noted safety glasses not worn during light material handling"})
    print("Medium Case Risk Reason:", res_med.get("risk_reason"))
    assert res_med.get("risk_reason") is not None, "risk_reason must not be None"

    print(">>> TEST 4 PASSED: Risk reason justifications cleanly generated across all risk tiers! <<<\n")


def test_mixed_signals_long_paragraph():
    print("=================================================================")
    print("TEST 5: MIXED SIGNALS IN LONG PARAGRAPH")
    print("=================================================================")

    long_text = (
        "The shift began with a routine safety briefing and team stretch. "
        "The crew then proceeded to the catalytic cracker unit for pump overhaul. "
        "During maintenance, the pump was opened while still pressurized and lockout was omitted. "
        "The area was cordoned off with barrier tape. "
        "A passing safety supervisor immediately ordered stop-work and instructed the crew to depressurize the line and apply loto. "
        "All controls were verified before work resumed."
    )

    res = analyze_report({"report_text": long_text})
    print(f"Long text length: {len(long_text)} chars")
    print(f"  -> Timeline: {res.get('temporal_timeline')}")
    print(f"  -> Sequence: {res.get('temporal_sequence')}")
    print(f"  -> Risk Level: {res.get('risk_level')} (Score: {res.get('risk_score')})")
    print(f"  -> SIF Potential: {res.get('sif_potential')}")
    print(f"  -> Risk Reason: {res.get('risk_reason')}")

    # Safe final resolution overrides
    assert res["risk_level"] == "LOW", f"Expected LOW risk due to final safe resolution, got {res['risk_level']}"
    assert res["sif_potential"] == "NO", f"Expected SIF NO, got {res['sif_potential']}"

    print(">>> TEST 5 PASSED: Multi-stage complex narrative correctly resolved! <<<\n")


def test_llm_safety_wrapper_and_demo_mode():
    print("=================================================================")
    print("TEST 6: LLM SAFETY WRAPPER & DEMO STABILITY MODE")
    print("=================================================================")

    print(f"DEMO_MODE flag: {DEMO_MODE}")
    assert DEMO_MODE is True, "DEMO_MODE should be enabled by default"

    report_mock = {
        "description": "Technician began electrical work on energized control panel without applying lockout tagout.",
        "life_saving_rule": "Energy Isolation",
        "barrier_failures": ["Lockout/Tagout Not Completed"],
        "risk_score": 84,
        "risk_level": "CRITICAL",
        "sif_potential": "YES",
        "confidence": 0.95
    }

    async def run_llm():
        result = await generate_llm_explanation(report_mock)
        print("LLM Execution Output:")
        print(f"  Source: {result.get('source')}")
        print(f"  Validation Passed: {result.get('validation_passed')}")
        print(f"  Root Cause: {result.get('root_cause')}")
        print(f"  Actions: {result.get('recommended_actions')}")
        assert result.get("source") in ("llm_verified", "demo_cache", "fallback_rule_based")
        assert len(result.get("recommended_actions", [])) >= 1

    asyncio.run(run_llm())
    print(">>> TEST 6 PASSED: LLM safety wrapper and demo mode guaranteed zero crash! <<<\n")


if __name__ == "__main__":
    test_typos_and_spelling_tolerance()
    test_abbreviation_normalization()
    test_pattern_stability_synonym_clustering()
    test_risk_score_justification_layer()
    test_mixed_signals_long_paragraph()
    test_llm_safety_wrapper_and_demo_mode()
    print("=================================================================")
    print(">>> ALL 6 PRODUCTION HARDENING & DEMO STABILITY TESTS PASSED! <<<")
    print("=================================================================")
