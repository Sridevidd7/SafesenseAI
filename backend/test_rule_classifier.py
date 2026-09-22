import sys
import json
from services.rule_classifier import classify_life_saving_rule, detect_lsr
from services.risk_engine import analyze_report

print("=================================================================")
print("RUNNING PROMPT 3 CONTEXT-AWARE RULE CLASSIFIER TESTS")
print("=================================================================")

all_passed = True

# ─── CASE 1: CONFINED SPACE DOMINANCE ───
print("\n--- Case 1: Confined Space Dominance ---")
text1 = "entered vessel without gas testing"
res1 = classify_life_saving_rule(text1)
print(f"Input: \"{text1}\"")
print(f"Classification: {json.dumps(res1, indent=2)}")

if res1["primary_rule"] == "Confined Space" and res1["primary_rule"] != "Energy Isolation":
    print("  -> Case 1 PASSED: Primary is 'Confined Space' (NOT Energy Isolation).")
else:
    print(f"  -> Case 1 FAILED: Expected primary 'Confined Space', got '{res1['primary_rule']}'")
    all_passed = False


# ─── CASE 2: HEIGHT ───
print("\n--- Case 2: Working at Height ---")
text2 = "worker climbed 10 meters without harness"
res2 = classify_life_saving_rule(text2)
print(f"Input: \"{text2}\"")
print(f"Classification: {json.dumps(res2, indent=2)}")

if res2["primary_rule"] == "Working at Height":
    print("  -> Case 2 PASSED: Primary is 'Working at Height'.")
else:
    print(f"  -> Case 2 FAILED: Expected primary 'Working at Height', got '{res2['primary_rule']}'")
    all_passed = False


# ─── CASE 3: MULTI-RULE ───
print("\n--- Case 3: Multi-Rule (Primary + Secondary) ---")
text3 = "entered tank with energized valve open"
res3 = classify_life_saving_rule(text3)
print(f"Input: \"{text3}\"")
print(f"Classification: {json.dumps(res3, indent=2)}")

if res3["primary_rule"] == "Confined Space" and res3["secondary_rule"] == "Energy Isolation":
    print("  -> Case 3 PASSED: Primary is 'Confined Space' and Secondary is 'Energy Isolation'.")
else:
    print(f"  -> Case 3 FAILED: Expected primary 'Confined Space' & secondary 'Energy Isolation', got primary='{res3['primary_rule']}', secondary='{res3['secondary_rule']}'")
    all_passed = False


# ─── CASE 4: FALSE CONTEXT ───
print("\n--- Case 4: False Context (Office Corridor) ---")
text4 = "electrical wire in office corridor"
res4 = classify_life_saving_rule(text4)
print(f"Input: \"{text4}\"")
print(f"Classification: {json.dumps(res4, indent=2)}")

if res4["primary_rule"] == "General Safety" or res4.get("scores", {}).get("Energy Isolation", 0) == 0:
    print("  -> Case 4 PASSED: Non-industrial office context correctly prevented false Energy Isolation classification.")
else:
    print(f"  -> Case 4 FAILED: Unexpected rule classification: {res4}")
    all_passed = False


# ─── END-TO-END RISK ENGINE INTEGRATION ───
print("\n--- End-to-End analyze_report Integration ---")
report = {
    "report_id": "REP-LSR-001",
    "report_text": "Technician entered tank with energized valve open and no permit issued.",
    "site": "Site Alpha",
    "severity": "Critical",
    "report_type": "Incident"
}
analysis = analyze_report(report)
print(f"Report Text: \"{report['report_text']}\"")
print(f"Primary Rule: {analysis['primary_rule']}")
print(f"Secondary Rule: {analysis['secondary_rule']}")
print(f"Rule Scores: {analysis['rule_scores']}")
print(f"Risk Score: {analysis['risk_score']} ({analysis['risk_level']})")
print(f"Barriers: {analysis['barrier_failures']}")

assert analysis['primary_rule'] == "Confined Space"
assert analysis['secondary_rule'] == "Energy Isolation"
assert "primary_rule" in analysis
assert "secondary_rule" in analysis
assert "rule_scores" in analysis

if all_passed:
    print("\n=================================================================")
    print(">>> ALL PROMPT 3 RULE CLASSIFICATION TESTS PASSED! <<<")
    print("=================================================================")
else:
    print("\n>>> SOME TESTS FAILED <<<")
    sys.exit(1)
