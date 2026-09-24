"""
SafeSense AI — Phase 2 Explainability & Evidence Hardening Regression Suite
=============================================================================
Validates:
1. Structured Evidence Model (Section 2)
2. Factor-Level Explainability (Section 3)
3. Explanation Consistency Rules (Section 4)
4. Unseen Report Robustness Across 4 Hazard Groups (Section 5)
5. Positive / Safe Counterexamples (Section 6)
6. Adversarial Negation Tests (Section 7)
"""
import pytest
from services.risk_engine import analyze_report, calculate_risk_score
from services.concept_extractor import build_structured_evidence, extract_safety_concepts


# ─── SECTION 2: STRUCTURED EVIDENCE MODEL ─────────────────────────────────────

def test_structured_evidence_model_active_violation():
    report = {"report_text": "Worker entered vessel without gas testing."}
    result = analyze_report(report)

    assert "structured_evidence" in result
    evidence_items = result["structured_evidence"]
    assert len(evidence_items) >= 2

    # Verify expected fields on every evidence item
    for item in evidence_items:
        assert "concept" in item
        assert "source_phrase" in item
        assert "evidence_type" in item
        assert "state" in item
        assert "related_barrier" in item
        assert "related_rule" in item
        # Ensure no fake probabilistic confidence numbers are fabricated
        assert "confidence" not in item or not isinstance(item["confidence"], float)

    # Check active entry exposure item
    exp_item = next((i for i in evidence_items if i["evidence_type"] == "ENTRY_EXPOSURE"), None)
    assert exp_item is not None
    assert exp_item["state"] == "ACTIVE_VIOLATION"
    assert "entered vessel" in exp_item["source_phrase"].lower()
    assert exp_item["related_rule"] == "Confined Space"

    # Check barrier omission item
    barrier_item = next((i for i in evidence_items if i["evidence_type"] == "BARRIER_OMISSION"), None)
    assert barrier_item is not None
    assert barrier_item["state"] == "ACTIVE_VIOLATION"
    assert barrier_item["related_barrier"] == "Gas Testing Not Completed"


def test_structured_evidence_model_prevented_state():
    report = {"report_text": "Work was stopped before entering vessel without gas testing."}
    result = analyze_report(report)

    assert result["risk_level"] == "LOW"
    assert result["sif_potential"] == "NO"

    evidence_items = result["structured_evidence"]
    assert len(evidence_items) > 0

    for item in evidence_items:
        if item["evidence_type"] in ("ENTRY_EXPOSURE", "BARRIER_OMISSION"):
            assert item["state"] == "PREVENTED"


def test_structured_evidence_model_positive_control():
    report = {"report_text": "Worker connected fall protection before climbing."}
    result = analyze_report(report)

    assert result["risk_level"] == "LOW"
    assert result["sif_potential"] == "NO"

    pos_items = [i for i in result["structured_evidence"] if i["evidence_type"] == "POSITIVE_CONTROL"]
    assert len(pos_items) > 0
    assert pos_items[0]["state"] == "POSITIVE_CONTROL"
    assert pos_items[0]["related_rule"] == "Working at Height"


# ─── SECTION 3: FACTOR-LEVEL EXPLAINABILITY ───────────────────────────────────

def test_factor_level_explainability_structure():
    report = {"report_text": "Worker entered vessel without gas testing."}
    result = analyze_report(report)

    assert "risk_factors" in result
    assert "factor_breakdown" in result
    factors = result["risk_factors"]
    assert len(factors) == 5

    factor_names = [f["name"] for f in factors]
    assert factor_names == [
        "Hazard Severity",
        "Barrier Failure",
        "Exposure",
        "Activity Criticality",
        "Recurrence Weight",
    ]

    for f in factors:
        assert "score" in f
        assert "max_score" in f
        assert "reason" in f
        assert "evidence" in f
        assert isinstance(f["score"], (int, float))
        assert isinstance(f["max_score"], int)
        assert isinstance(f["reason"], str) and len(f["reason"]) > 5
        assert isinstance(f["evidence"], list)

    # Specific factor assertions
    breakdown = result["factor_breakdown"]
    assert breakdown["Hazard Severity"]["score"] == 28
    assert breakdown["Hazard Severity"]["max_score"] == 30
    assert "Confined Space" in breakdown["Hazard Severity"]["reason"]

    assert breakdown["Barrier Failure"]["score"] == 25
    assert breakdown["Barrier Failure"]["max_score"] == 25
    assert "Gas Testing Not Completed" in breakdown["Barrier Failure"]["reason"]

    assert breakdown["Exposure"]["score"] == 16
    assert breakdown["Exposure"]["max_score"] == 20
    assert "Active operational exposure" in breakdown["Exposure"]["reason"]


# ─── SECTION 4: EXPLANATION CONSISTENCY RULES ─────────────────────────────────

def test_explanation_consistency_preventive_before_exposure():
    report = {"report_text": "Work was stopped before entry without gas testing."}
    result = analyze_report(report)

    explanation = result["explanation"]
    # Rule: explanation must NEVER claim worker was exposed to a serious hazard
    assert "active worker exposure" not in explanation.lower() or "no active worker exposure" in explanation.lower()
    assert "was exposed to a serious hazard" not in explanation.lower()
    # Rule: must explicitly state prevention of barrier omission
    assert "prevented" in explanation.lower()
    assert result["risk_level"] == "LOW"
    assert result["sif_potential"] == "NO"


def test_explanation_consistency_unsafe_with_intervention():
    report = {"report_text": "Worker had already entered vessel without gas testing when supervisor intervened."}
    result = analyze_report(report)

    explanation = result["explanation"]
    # Rule: must distinguish initial unsafe exposure from subsequent curtailment
    assert "exposure occurred" in explanation.lower() or "violation occurred" in explanation.lower()
    assert "intervention" in explanation.lower()
    assert "curtailed" in explanation.lower() or "stopped" in explanation.lower()
    # The intervention must NOT erase the underlying finding
    assert result["sif_potential"] == "YES"
    assert result["temporal_sequence"] == "UNSAFE_WITH_INTERVENTION"


def test_explanation_consistency_routine_low():
    report = {"report_text": "Routine inspection of the storage area was completed cleanly."}
    result = analyze_report(report)

    assert result["risk_level"] == "LOW"
    assert result["sif_potential"] == "NO"
    assert "routine observation" in result["explanation"].lower()


# ─── SECTION 5: UNSEEN REPORT ROBUSTNESS MATRIX ───────────────────────────────

def test_unseen_confined_space_matrix():
    cases = [
        "entered vessel without checking atmosphere",
        "went inside tank before air monitoring",
        "chamber entry occurred before atmospheric verification",
    ]
    for text in cases:
        res = analyze_report({"report_text": text})
        assert res["life_saving_rule"] == "Confined Space"
        assert "Gas Testing Not Completed" in res["barrier_failures"]
        assert res["temporal_sequence"] == "PURE_UNSAFE"
        assert res["risk_level"] == "CRITICAL"
        assert res["risk_score"] == 89
        assert res["sif_potential"] == "YES"


def test_unseen_working_at_height_matrix():
    cases = [
        "climbed structure without being tied off",
        "accessed elevated platform before securing fall protection",
        "worked from scaffold without harness connection",
    ]
    for text in cases:
        res = analyze_report({"report_text": text})
        assert res["life_saving_rule"] == "Working at Height"
        assert "Fall Protection Not Used" in res["barrier_failures"]
        assert res["temporal_sequence"] == "PURE_UNSAFE"
        assert res["risk_level"] == "CRITICAL"
        assert res["risk_score"] == 89
        assert res["sif_potential"] == "YES"


def test_unseen_energy_isolation_matrix():
    cases = [
        ("worked on energized equipment without lockout", "Lockout/Tagout Not Completed"),
        ("opened electrical panel before isolation", "Isolation Not Applied"),
        ("maintenance began while the circuit remained live", "Isolation Not Applied"),
    ]
    for text, expected_barrier in cases:
        res = analyze_report({"report_text": text})
        assert res["life_saving_rule"] == "Energy Isolation"
        assert expected_barrier in res["barrier_failures"]
        assert res["temporal_sequence"] == "PURE_UNSAFE"
        assert res["risk_level"] == "CRITICAL"
        assert res["risk_score"] == 89
        assert res["sif_potential"] == "YES"


def test_unseen_line_of_fire_matrix():
    cases = [
        "worker positioned beneath suspended load",
        "person entered the drop zone while load was lifted",
        "employee stood in the path of moving equipment",
    ]
    for text in cases:
        res = analyze_report({"report_text": text})
        assert res["life_saving_rule"] == "Line of Fire"
        assert "Exclusion Zone Not Established" in res["barrier_failures"]
        assert res["temporal_sequence"] == "PURE_UNSAFE"
        assert res["risk_level"] == "HIGH"
        assert res["risk_score"] == 79
        assert res["sif_potential"] == "YES"


# ─── SECTION 6: POSITIVE / SAFE COUNTEREXAMPLES ───────────────────────────────

@pytest.mark.parametrize("sentence,expected_rule", [
    ("Gas testing was completed before entry and atmosphere was verified safe.", "Confined Space"),
    ("Worker connected fall protection before climbing.", "Working at Height"),
    ("Breaker was locked out and verified de-energized before maintenance.", "Energy Isolation"),
    ("Area was barricaded and worker remained outside the drop zone.", "Line of Fire"),
])
def test_positive_safe_counterexamples(sentence, expected_rule):
    res = analyze_report({"report_text": sentence})

    assert res["life_saving_rule"] == expected_rule
    # No false barrier failure
    assert not any(b != "Safely Controlled" and not b.startswith("Prevented:") for b in res["barrier_failures"])
    # No false SIF
    assert res["sif_potential"] == "NO"
    # Sensible LOW risk
    assert res["risk_level"] == "LOW"
    assert res["risk_score"] <= 20
    # Correct temporal state
    assert res["temporal_sequence"] in ("PREVENTIVE_BEFORE_EXPOSURE", "PURE_SAFE")


# ─── SECTION 7: ADVERSARIAL NEGATION TESTS ────────────────────────────────────

@pytest.mark.parametrize("sentence,expected_rule", [
    ("no exposure occurred", "General Safety"),
    ("worker did not enter the vessel", "Confined Space"),
    ("entry was prevented", "General Safety"),
    ("work was stopped before exposure", "General Safety"),
    ("gas testing was not skipped", "Confined Space"),
    ("lockout was completed before work", "Energy Isolation"),
    ("fall protection was already secured", "Working at Height"),
])
def test_adversarial_negation_distinction(sentence, expected_rule):
    res = analyze_report({"report_text": sentence})

    assert res["life_saving_rule"] == expected_rule
    # None of these should result in an active violation or SIF YES
    assert res["sif_potential"] == "NO"
    assert res["risk_level"] == "LOW"
    assert res["risk_score"] <= 20
    assert not any(b != "Safely Controlled" and not b.startswith("Prevented:") for b in res["barrier_failures"])
