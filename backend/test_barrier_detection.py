import sys
from services.barrier_dictionary import detect_barriers, detect_barriers_with_evidence, detect_barrier
from services.risk_engine import analyze_report, calculate_risk_score

synonym_test_cases = [
    ("worker entered tank without gas testing", "Gas Testing Not Completed"),
    ("technician entered vessel no atmospheric test done", "Gas Testing Not Completed"),
    ("no permit was issued before entry", "Permit Not Obtained"),
    ("worker not tied off at height", "Fall Protection Not Used"),
]

keyword_test_cases = [
    ("operator went into chamber, oxygen sampling omitted by crew", "Gas Testing Not Completed", "keyword"),
    ("contractor mounted tower, missing lanyard anchor protection", "Fall Protection Not Used", "keyword"),
]

print("=== RUNNING BARRIER DETECTION SYNONYM TESTS ===")
all_passed = True
for text, expected in synonym_test_cases:
    barriers = detect_barriers(text)
    evidence = detect_barriers_with_evidence(text)
    primary = detect_barrier(text)
    print(f"\nReport Text: \"{text}\"")
    print(f"  Expected Barrier: {expected}")
    print(f"  Detected Barriers: {barriers}")
    print(f"  Primary Barrier: {primary}")
    print(f"  Structured Evidence: {evidence}")
    if expected not in barriers:
        print(f"  -> RESULT: FAILED (Expected '{expected}' not in {barriers})")
        all_passed = False
    else:
        print("  -> RESULT: PASSED")

print("\n=== RUNNING BARRIER DETECTION KEYWORD FALLBACK TESTS ===")
for text, expected, expected_method in keyword_test_cases:
    evidence = detect_barriers_with_evidence(text)
    barriers = [e["barrier"] for e in evidence]
    matched_methods = {e["barrier"]: e["method"] for e in evidence}
    print(f"\nReport Text: \"{text}\"")
    print(f"  Expected Barrier: {expected} (via {expected_method})")
    print(f"  Detected Barriers: {barriers}")
    print(f"  Evidence: {evidence}")
    if expected not in barriers:
        print(f"  -> RESULT: FAILED (Expected '{expected}')")
        all_passed = False
    else:
        print(f"  -> RESULT: PASSED (Method: {matched_methods.get(expected)})")

print("\n=== RUNNING RISK ENGINE INTEGRATION TEST ===")
sample_report = {
    "report_id": "TEST-001",
    "report_text": "Technician entered vessel no atmospheric test done and no permit was issued before entry.",
    "site": "Site Alpha",
    "severity": "High",
    "report_type": "Near Miss",
}

analysis = analyze_report(sample_report)
print(f"Risk Score: {analysis['risk_score']}")
print(f"Risk Level: {analysis['risk_level']}")
print(f"Life Saving Rule: {analysis['life_saving_rule']}")
print(f"Detected Barriers: {analysis['barrier_failures']}")
print(f"Barrier Evidence: {analysis['barrier_evidence']}")
print(f"SIF Potential: {analysis['sif_potential']}")
print(f"Confidence: {analysis['confidence']} ({analysis['confidence_level']})")

if not all_passed:
    sys.exit(1)
print("\n>>> ALL TESTS COMPLETED SUCCESSFULLY! <<<")
