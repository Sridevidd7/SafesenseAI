import sys
import json
from services.barrier_dictionary import (
    normalize_text,
    detect_barriers_with_evidence,
    detect_barriers,
    detect_barrier
)
from services.risk_engine import analyze_report

print("=================================================================")
print("RUNNING MANDATORY PRODUCTION-READY BARRIER DETECTION TESTS")
print("=================================================================")

all_passed = True

# ─── LAYER 1: Normalization Tests ───
print("\n--- Layer 1: Normalization Tests ---")
norm1 = normalize_text("Worker didn't test gas, wasn't wearing harness!")
print(f"Original: 'Worker didn't test gas, wasn't wearing harness!' -> Normalized: '{norm1}'")
assert "did not" in norm1 and "was not" in norm1, "Contractions expansion failed"
assert "!" not in norm1 and "," not in norm1, "Punctuation stripping failed"
print("  -> Layer 1: PASSED")


# ─── MANDATORY TEST CASES ───
print("\n--- Mandatory Prompt Test Cases ---")

# Case 1 — Variation
text1 = "oxygen levels were not checked before entry"
res1 = detect_barriers_with_evidence(text1)
barriers1 = [r["barrier"] for r in res1]
print(f"\nCase 1: \"{text1}\"")
print(f"  Detected: {res1}")
if "Gas Testing Not Completed" in barriers1:
    print(f"  -> Case 1 PASSED (Confidence: {res1[0]['confidence']}, Method: {res1[0]['method']}, Evidence: {res1[0]['evidence']})")
else:
    print("  -> Case 1 FAILED: 'Gas Testing Not Completed' not detected")
    all_passed = False

# Case 2 — Mixed phrasing
text2 = "entered vessel without any clearance or permit"
res2 = detect_barriers_with_evidence(text2)
barriers2 = [r["barrier"] for r in res2]
print(f"\nCase 2: \"{text2}\"")
print(f"  Detected: {res2}")
if "Permit Not Obtained" in barriers2:
    print(f"  -> Case 2 PASSED (Confidence: {res2[0]['confidence']}, Method: {res2[0]['method']}, Evidence: {res2[0]['evidence']})")
else:
    print("  -> Case 2 FAILED: 'Permit Not Obtained' not detected")
    all_passed = False

# Case 3 — False positive guard
text3 = "electrical wire on office floor"
res3 = detect_barriers_with_evidence(text3)
barriers3 = [r["barrier"] for r in res3]
print(f"\nCase 3: \"{text3}\"")
print(f"  Detected: {res3}")
if "Energy Isolation" not in barriers3 and "Lockout/Tagout Not Completed" not in barriers3:
    print("  -> Case 3 PASSED: False positive industrial barriers correctly rejected in non-industrial context")
else:
    print(f"  -> Case 3 FAILED: Unexpected barrier detected: {barriers3}")
    all_passed = False

# Case 4 — Weak signal
text4 = "crew skipped testing procedure"
res4 = detect_barriers_with_evidence(text4)
barriers4 = [r["barrier"] for r in res4]
print(f"\nCase 4: \"{text4}\"")
print(f"  Detected: {res4}")
if "Gas Testing Not Completed" in barriers4:
    conf = res4[0]['confidence']
    print(f"  -> Case 4 PASSED (Detected with lower/medium confidence: {conf}, Method: {res4[0]['method']})")
    assert 0.45 <= conf <= 0.85, f"Expected lower/medium confidence, got {conf}"
else:
    print("  -> Case 4 FAILED: 'Gas Testing Not Completed' not detected")
    all_passed = False


# ─── INTEGRATION WITH RISK ENGINE ───
print("\n--- Risk Engine End-to-End Analysis ---")
report = {
    "report_id": "REP-PROD-001",
    "report_text": "Technician entered vessel without any clearance or permit and oxygen levels were not checked before entry.",
    "site": "Plant 1",
    "severity": "High",
    "report_type": "Near Miss"
}

analysis = analyze_report(report)
print(f"Report Text: {report['report_text']}")
print(f"Risk Score: {analysis['risk_score']} ({analysis['risk_level']})")
print(f"Barriers: {analysis['barrier_failures']}")
print(f"Barrier Evidence JSON:\n{json.dumps(analysis['barrier_evidence'], indent=2)}")

assert "Permit Not Obtained" in analysis['barrier_failures']
assert "Gas Testing Not Completed" in analysis['barrier_failures']
assert len(analysis['barrier_evidence']) >= 2

if all_passed:
    print("\n=================================================================")
    print(">>> ALL PRODUCTION-READY BARRIER DETECTION TESTS PASSED! <<<")
    print("=================================================================")
else:
    print("\n>>> SOME TESTS FAILED <<<")
    sys.exit(1)
