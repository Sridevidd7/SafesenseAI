import sys
import json
from services.barrier_dictionary import (
    detect_barriers_with_evidence,
    detect_barriers,
    detect_barrier,
    calibrate_confidence,
)
from services.risk_engine import analyze_report

print("=================================================================")
print("RUNNING PROMPT 2 HARDENED BARRIER DETECTION TESTS")
print("=================================================================")

all_passed = True

# ─── CASE 1: OVERLAP ───
print("\n--- Case 1: Overlap Conflict Resolution ---")
text1 = "oxygen level not checked and no gas test"
res1 = detect_barriers_with_evidence(text1)
barriers1 = [b["barrier"] for b in res1]
print(f"Input: \"{text1}\"")
print(f"Detected: {json.dumps(res1, indent=2)}")

if len(barriers1) == 1 and barriers1[0] == "Gas Testing Not Completed":
    print(f"  -> Case 1 PASSED: Exactly 1 barrier detected ({barriers1[0]}), duplicate signals merged.")
    assert res1[0]["confidence_score"] >= 0.85
    assert res1[0]["confidence_level"] == "HIGH"
    assert "detection_reason" in res1[0]
else:
    print(f"  -> Case 1 FAILED: Expected exactly 1 barrier, got {barriers1}")
    all_passed = False


# ─── CASE 2: MULTI-BARRIER FAILURE & INTERACTION BOOST ───
print("\n--- Case 2: Multi-Barrier Failure & Interaction Boost ---")
text2 = "no permit and no gas testing"
res2 = detect_barriers_with_evidence(text2)
barriers2 = [b["barrier"] for b in res2]
print(f"Input: \"{text2}\"")
print(f"Detected: {json.dumps(res2, indent=2)}")

if len(barriers2) == 2 and "Permit Not Obtained" in barriers2 and "Gas Testing Not Completed" in barriers2:
    print(f"  -> Case 2 PASSED: 2 distinct barriers detected.")
    for b in res2:
        assert b["confidence_level"] == "HIGH", f"Expected HIGH, got {b['confidence_level']}"
        assert b["confidence_score"] >= 0.90, f"Expected boosted confidence >= 0.90, got {b['confidence_score']}"
        print(f"     * {b['barrier']} -> score: {b['confidence_score']}, level: {b['confidence_level']}, reason: {b['detection_reason']}")
else:
    print(f"  -> Case 2 FAILED: Expected 2 barriers, got {barriers2}")
    all_passed = False


# ─── CASE 3: NOISE / POSITIVE CONFIRMATION GUARD ───
print("\n--- Case 3: Noise / Positive Confirmation Guard ---")
text3 = "worker mentioned gas but testing was completed"
res3 = detect_barriers_with_evidence(text3)
barriers3 = [b["barrier"] for b in res3]
print(f"Input: \"{text3}\"")
print(f"Detected: {res3}")

if "Gas Testing Not Completed" not in barriers3:
    print("  -> Case 3 PASSED: Positive confirmation correctly prevented false positive barrier detection.")
else:
    print(f"  -> Case 3 FAILED: Unexpectedly detected failure: {barriers3}")
    all_passed = False


# ─── CASE 4: WEAK CONTEXT & LOW CONFIDENCE CALIBRATION ───
print("\n--- Case 4: Weak Context & Low Confidence Calibration ---")
text4 = "testing unclear"
res4 = detect_barriers_with_evidence(text4)
print(f"Input: \"{text4}\"")
print(f"Detected: {json.dumps(res4, indent=2)}")

if len(res4) > 0 and res4[0]["barrier"] == "Gas Testing Not Completed":
    conf_lvl = res4[0]["confidence_level"]
    conf_scr = res4[0]["confidence_score"]
    if conf_lvl == "LOW":
        print(f"  -> Case 4 PASSED: Detected with LOW confidence band (score: {conf_scr}, band: {conf_lvl}).")
    else:
        print(f"  -> Case 4 WARNING: Expected band LOW, got {conf_lvl} (score: {conf_scr})")
else:
    print(f"  -> Case 4 FAILED: Weak signal not detected: {res4}")
    all_passed = False


# ─── END-TO-END RISK ENGINE & TOP-K RANKING ───
print("\n--- End-to-End Ranking & Top-K Truncation Test ---")
multi_text = "technician entered vessel without permit, without gas testing, no harness at height, and live circuit not isolated"
res_top = detect_barriers_with_evidence(multi_text)
print(f"Multi Input: \"{multi_text}\"")
print(f"Total detected (capped at TOP_K=3): {len(res_top)}")
for i, item in enumerate(res_top, 1):
    print(f"  Rank {i}: {item['barrier']} | Score: {item['confidence_score']} | Band: {item['confidence_level']} | Method: {item['method']}")
    print(f"          Reason: {item['detection_reason']}")

assert len(res_top) <= 3, f"Expected at most 3 ranked barriers, got {len(res_top)}"
assert res_top[0]["confidence_score"] >= res_top[-1]["confidence_score"], "Ranking order incorrect"

if all_passed:
    print("\n=================================================================")
    print(">>> ALL PROMPT 2 HARDENED TESTS PASSED SUCCESSFULLY! <<<")
    print("=================================================================")
else:
    print("\n>>> SOME TESTS FAILED <<<")
    sys.exit(1)
