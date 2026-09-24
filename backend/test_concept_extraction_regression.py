"""
SafeSense AI — Safety Concept Extraction Regression Test Suite
===============================================================
Comprehensive regression tests verifying that semantically equivalent safety
reports are interpreted consistently across the NLP concept extraction layer,
rule classifier, barrier detector, and deterministic risk engine.

Covers:
1. Canonical & extended paraphrases
2. Positive completion and prevented cases
3. Active violations
4. Post-exposure interventions
5. Pre-exposure prevention
6. Ordinary low-risk observations
7. Unrelated non-industrial text
8. Direct concept extractor unit tests
"""
import pytest
from services.risk_engine import analyze_report, calculate_risk_score
from services.concept_extractor import extract_safety_concepts, normalize_safety_text
from services.barrier_dictionary import detect_barriers, detect_barriers_with_evidence
from services.rule_classifier import classify_life_saving_rule


# ─── 1. CANONICAL CONFINED SPACE PARAPHRASES ──────────────────────────────────

CANONICAL_CONFINED_SPACE_CASES = [
    "Worker entered vessel without gas testing.",
    "Worker went inside before atmospheric testing.",
    "Confined-space entry occurred without atmospheric monitoring.",
    "Technician entered the vessel without checking the atmosphere.",
]

def test_canonical_confined_space_paraphrases_consistency():
    """
    Verifies that the 4 canonical paraphrases from the specification
    all map to the exact same safety concepts, LSR, barrier, SIF potential,
    negation status, and risk score.
    """
    results = [analyze_report({"report_text": text}) for text in CANONICAL_CONFINED_SPACE_CASES]
    first = results[0]

    # Expected baseline
    assert first["life_saving_rule"] == "Confined Space"
    assert "Gas Testing Not Completed" in first["barrier_failures"]
    assert first["sif_potential"] == "YES"
    assert first["negation_type"] == "UNSAFE_VIOLATION"
    assert first["risk_level"] == "CRITICAL"
    assert first["risk_score"] == 89

    # Check concepts
    concepts = first.get("safety_concepts", [])
    assert "confined_space" in concepts
    assert "entry_exposure" in concepts
    assert "gas_testing_missing" in concepts

    # Every paraphrase must match the canonical interpretation
    for idx, res in enumerate(results[1:], start=2):
        text = CANONICAL_CONFINED_SPACE_CASES[idx - 1]
        assert res["life_saving_rule"] == "Confined Space", f"Failed LSR for: '{text}'"
        assert "Gas Testing Not Completed" in res["barrier_failures"], f"Failed barrier for: '{text}'"
        assert res["sif_potential"] == "YES", f"Failed SIF for: '{text}'"
        assert res["negation_type"] == "UNSAFE_VIOLATION", f"Failed negation for: '{text}'"
        assert res["risk_level"] == "CRITICAL", f"Failed risk level for: '{text}'"
        assert res["risk_score"] == first["risk_score"], f"Score mismatch ({res['risk_score']} != {first['risk_score']}) for: '{text}'"

        c_set = set(res.get("safety_concepts", []))
        assert "confined_space" in c_set, f"Missing 'confined_space' concept in: '{text}'"
        assert "entry_exposure" in c_set, f"Missing 'entry_exposure' concept in: '{text}'"
        assert "gas_testing_missing" in c_set, f"Missing 'gas_testing_missing' concept in: '{text}'"


# ─── 2. EXTENDED DOMAIN PARAPHRASES ───────────────────────────────────────────

def test_extended_confined_space_paraphrases():
    extended_cases = [
        "Operator accessed the drum without gas measurement.",
        "Contractor stepped into chamber prior to gas detection.",
    ]
    for text in extended_cases:
        res = analyze_report({"report_text": text})
        assert res["life_saving_rule"] == "Confined Space"
        assert "Gas Testing Not Completed" in res["barrier_failures"]
        assert res["sif_potential"] == "YES"
        assert res["negation_type"] == "UNSAFE_VIOLATION"
        assert res["risk_level"] == "CRITICAL"
        assert res["risk_score"] >= 85


def test_working_at_height_paraphrases():
    height_cases = [
        "Worker climbed scaffold without safety harness.",
        "Operator mounted tower before securing lanyard.",
        "Technician climbed ladder without being tied off.",
    ]
    for text in height_cases:
        res = analyze_report({"report_text": text})
        assert res["life_saving_rule"] == "Working at Height"
        assert "Fall Protection Not Used" in res["barrier_failures"]
        assert res["sif_potential"] == "YES"
        assert res["negation_type"] == "UNSAFE_VIOLATION"
        assert res["risk_level"] in ["HIGH", "CRITICAL"]
        assert res["risk_score"] >= 80

        concepts = set(res.get("safety_concepts", []))
        assert "working_at_height" in concepts
        assert "height_exposure" in concepts
        assert "fall_protection_missing" in concepts


def test_energy_isolation_paraphrases():
    energy_cases = [
        "Worker serviced pump without locking out the breaker.",
        "Operator worked on motor before electrical isolation.",
        "Technician opened panel without de-energizing the circuit.",
    ]
    for text in energy_cases:
        res = analyze_report({"report_text": text})
        assert res["life_saving_rule"] == "Energy Isolation"
        assert any(b in res["barrier_failures"] for b in ["Lockout/Tagout Not Completed", "Isolation Not Applied"])
        assert res["sif_potential"] == "YES"
        assert res["negation_type"] == "UNSAFE_VIOLATION"
        assert res["risk_level"] in ["HIGH", "CRITICAL"]
        assert res["risk_score"] >= 80

        concepts = set(res.get("safety_concepts", []))
        assert "energy_isolation" in concepts
        assert "energy_exposure" in concepts


def test_line_of_fire_paraphrases():
    lof_cases = [
        "Rigger walked beneath crane load before area was barricaded.",
        "Worker stood under suspended load without exclusion zone.",
    ]
    for text in lof_cases:
        res = analyze_report({"report_text": text})
        assert res["life_saving_rule"] == "Line of Fire"
        assert "Exclusion Zone Not Established" in res["barrier_failures"]
        assert res["sif_potential"] == "YES"
        assert res["negation_type"] == "UNSAFE_VIOLATION"
        assert res["risk_level"] in ["HIGH", "CRITICAL"]

        concepts = set(res.get("safety_concepts", []))
        assert "line_of_fire" in concepts
        assert "line_of_fire_exposure" in concepts
        assert "exclusion_zone_missing" in concepts


def test_permit_authorization_paraphrases():
    permit_cases = [
        "Crew started maintenance without obtaining authorization.",
        "Operator opened vessel prior to permit issuance.",
    ]
    for text in permit_cases:
        res = analyze_report({"report_text": text})
        assert "Permit Not Obtained" in res["barrier_failures"]
        assert res["sif_potential"] == "YES"
        assert res["negation_type"] == "UNSAFE_VIOLATION"

        concepts = set(res.get("safety_concepts", []))
        assert "permit_missing" in concepts


# ─── 3. POSITIVE COMPLETION AND PREVENTED CASES ───────────────────────────────

def test_positive_completion_cases():
    """
    Ensure positive safety barrier confirmations do NOT trigger false barrier failure detections.
    """
    safe_cases = [
        "Worker entered vessel after gas testing was completed and verified safe.",
        "Technician mounted scaffold after harness was inspected and securely tied off.",
        "Maintenance was performed on the pump after lockout tagout was verified and completed.",
    ]
    for text in safe_cases:
        res = analyze_report({"report_text": text})
        # Gas testing, fall protection, and lockout should not be flagged as failed barriers
        assert "Gas Testing Not Completed" not in res["barrier_failures"]
        assert "Fall Protection Not Used" not in res["barrier_failures"]
        assert "Lockout/Tagout Not Completed" not in res["barrier_failures"]
        assert res["negation_type"] != "UNSAFE_VIOLATION"


# ─── 4. ACTIVE VIOLATIONS ─────────────────────────────────────────────────────

def test_active_violations_flagged_correctly():
    """
    Verifies that active barrier violations result in UNSAFE_VIOLATION, SIF YES, and high risk.
    """
    violations = [
        "Worker entered vessel without gas testing.",
        "Technician serviced energized circuit without isolation.",
        "Contractor climbed 8 meters on scaffold without harness.",
    ]
    for text in violations:
        res = analyze_report({"report_text": text})
        assert res["negation_type"] == "UNSAFE_VIOLATION"
        assert res["sif_potential"] == "YES"
        assert res["risk_level"] in ["HIGH", "CRITICAL"]
        assert res["risk_score"] >= 80


# ─── 5. POST-EXPOSURE INTERVENTIONS ───────────────────────────────────────────

def test_post_exposure_interventions():
    """
    When intervention occurs after active exposure, the report must be classified
    as UNSAFE_WITH_INTERVENTION, preserving SIF potential and elevated risk.
    """
    post_cases = [
        "Worker entered vessel without gas testing. Supervisor intervened and stopped the work.",
        "Technician climbed scaffold without harness. Work was suspended after the unsafe condition occurred.",
    ]
    for text in post_cases:
        res = analyze_report({"report_text": text})
        assert res["negation_type"] == "UNSAFE_WITH_INTERVENTION"
        assert res["sif_potential"] == "YES"
        assert res["risk_level"] in ["HIGH", "CRITICAL"]
        assert res["risk_score"] >= 70


# ─── 6. PRE-EXPOSURE PREVENTION ───────────────────────────────────────────────

def test_pre_exposure_prevention():
    """
    When work or entry is stopped prior to exposure, the event is preventative:
    no exposure occurs, SIF is NO, and risk score is suppressed.
    """
    pre_cases = [
        "Supervisor stopped the worker before entry because gas testing was not done.",
        "Work was halted prior to climbing the tower due to missing harness.",
        "Personnel were preparing to enter vessel without gas testing but were stopped before entry.",
    ]
    for text in pre_cases:
        res = analyze_report({"report_text": text})
        assert res["negation_type"] in ["SAFE_PREVENTIVE", "UNSAFE_AVOIDED"]
        assert res["sif_potential"] == "NO"
        assert res["risk_score"] < 50
        assert res["risk_level"] in ["LOW", "MEDIUM"]


# ─── 7. ORDINARY LOW-RISK OBSERVATIONS ────────────────────────────────────────

def test_ordinary_low_risk_observations():
    """
    Observations with no critical hazards or barrier violations should score LOW risk with SIF NO.
    """
    low_risk_cases = [
        "An employee noticed an empty cardboard box on the walkway and picked it up immediately. No one was exposed to harm.",
        "Routine housekeeping checklist completed for the tool storage area.",
        "Minor scratch noted on walkway handrail during routine inspection.",
    ]
    for text in low_risk_cases:
        res = analyze_report({"report_text": text})
        assert res["risk_level"] == "LOW"
        assert res["sif_potential"] == "NO"
        assert res["life_saving_rule"] == "General Safety"
        assert len(res["barrier_failures"]) == 0
        assert res["risk_score"] <= 25


# ─── 8. UNRELATED NON-INDUSTRIAL TEXT ─────────────────────────────────────────

def test_unrelated_non_industrial_text():
    """
    Corporate, office, or unrelated text must not trigger false safety concepts or barriers.
    """
    unrelated_cases = [
        "The team met in the 3rd floor conference room to discuss Q3 marketing budget.",
        "Office worker updated spreadsheet on the laptop at the front desk.",
        "HR sent an email to all staff regarding holiday schedule.",
    ]
    for text in unrelated_cases:
        res = analyze_report({"report_text": text})
        assert res.get("safety_concepts") == []
        assert res["barrier_failures"] == []
        assert res["life_saving_rule"] == "General Safety"
        assert res["risk_level"] == "LOW"
        assert res["sif_potential"] == "NO"


# ─── 9. DIRECT CONCEPT EXTRACTOR UNIT TESTS ───────────────────────────────────

def test_concept_extractor_normalization():
    norm = normalize_safety_text("Confined-space entry, lock-out-tag-out omitted, air-monitoring missing.")
    assert "confined space" in norm
    assert "lockout tagout" in norm
    assert "air monitoring" in norm


def test_concept_extractor_empty_input():
    empty_res = extract_safety_concepts("")
    assert empty_res["concepts"] == []
    assert empty_res["barrier_omissions"] == []
    assert empty_res["exposure_detected"] is False
    assert empty_res["primary_domain"] == "General Safety"


if __name__ == "__main__":
    pytest.main(["-v", __file__])
