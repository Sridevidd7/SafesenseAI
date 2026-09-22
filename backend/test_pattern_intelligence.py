import sys
import json
from services.pattern_engine import (
    compute_similarity,
    cluster_reports,
    detect_repeated_failures,
    classify_trend,
    detect_anomalies,
    generate_insights
)

print("=================================================================")
print("RUNNING PROMPT 4 PATTERN INTELLIGENCE & INSIGHT ENGINE TESTS")
print("=================================================================")

all_passed = True

# ─── CASE 1: REPEATED ISSUE CLUSTERING ───
print("\n--- Case 1: Similarity Clustering & Repeated Issue Detection ---")
sample_repeated_reports = [
    {"report_id": "R1", "description": "technician entered tank without gas testing", "category": "Confined Space", "barrier": "Gas Testing Not Completed", "site": "Site Alpha", "risk_score": 85, "sif_potential": "YES"},
    {"report_id": "R2", "description": "operator entered vessel without gas test conducted", "category": "Confined Space", "barrier": "Gas Testing Not Completed", "site": "Site Alpha", "risk_score": 80, "sif_potential": "YES"},
    {"report_id": "R3", "description": "worker went into tank no atmospheric testing performed", "category": "Confined Space", "barrier": "Gas Testing Not Completed", "site": "Site Alpha", "risk_score": 90, "sif_potential": "YES"},
    {"report_id": "R4", "description": "crew entered chamber without prior gas test", "category": "Confined Space", "barrier": "Gas Testing Not Completed", "site": "Site Alpha", "risk_score": 85, "sif_potential": "YES"},
    {"report_id": "R5", "description": "contractor entered vessel no gas monitoring done", "category": "Confined Space", "barrier": "Gas Testing Not Completed", "site": "Site Alpha", "risk_score": 88, "sif_potential": "YES"},
]

clusters = cluster_reports(sample_repeated_reports)
print(f"Input: 5 similar reports")
print(f"Clusters produced: {len(clusters)}")
print(f"Cluster 1: {json.dumps(clusters[0], indent=2)}")

repeated = detect_repeated_failures(clusters)
print(f"Repeated failures (count >= 3): {len(repeated)}")

if len(clusters) == 1 and clusters[0]["count"] == 5 and len(repeated) == 1:
    print("  -> Case 1 PASSED: All 5 reports clustered together into a verified recurring failure pattern.")
else:
    print(f"  -> Case 1 FAILED: Expected 1 cluster of 5 items, got {len(clusters)} clusters with counts {[c['count'] for c in clusters]}")
    all_passed = False


# ─── CASE 2: MULTI-SITE CROSS-FACILITY PATTERN ───
print("\n--- Case 2: Multi-Site Cross-Facility Pattern ---")
multi_site_reports = [
    {"report_id": "M1", "description": "worker at height without harness", "category": "Working at Height", "barrier": "Fall Protection Not Used", "site": "Site Alpha", "risk_score": 75, "sif_potential": "NO"},
    {"report_id": "M2", "description": "contractor climbing scaffold without safety harness", "category": "Working at Height", "barrier": "Fall Protection Not Used", "site": "Site Beta", "risk_score": 80, "sif_potential": "NO"},
]

ms_clusters = cluster_reports(multi_site_reports)
print(f"Multi-site clusters: {json.dumps(ms_clusters, indent=2)}")

insights_ms = generate_insights(multi_site_reports, ms_clusters, [], [])
print(f"Generated Insights for Multi-Site: {json.dumps(insights_ms, indent=2)}")

has_cross_site = any(i["type"] == "CROSS_SITE_RISK" or len(i.get("sites", [])) >= 2 for i in insights_ms)
if len(ms_clusters) == 1 and len(ms_clusters[0]["sites"]) == 2 and has_cross_site:
    print("  -> Case 2 PASSED: Cross-site pattern across Site Alpha and Site Beta correctly identified.")
else:
    print("  -> Case 2 FAILED: Cross-site insight not generated.")
    all_passed = False


# ─── CASE 3: TEMPORAL SPIKE & ANOMALY DETECTION ───
print("\n--- Case 3: Month-over-Month Incident Spike Anomaly ---")
monthly_data = [
    {"month": "2026-01", "total": 3, "critical": 1, "sif": 1},
    {"month": "2026-02", "total": 4, "critical": 1, "sif": 1},
    {"month": "2026-03", "total": 10, "critical": 4, "sif": 3},
]

trend_result = classify_trend([m["total"] for m in monthly_data], [m["month"] for m in monthly_data])
print(f"Trend Result: {json.dumps(trend_result, indent=2)}")

anomalies = detect_anomalies(monthly_data)
print(f"Anomalies Detected: {json.dumps(anomalies, indent=2)}")

if trend_result["trend"] == "RISING RISK" and len(anomalies) > 0 and anomalies[0]["anomaly"] is True:
    print(f"  -> Case 3 PASSED: Trend is '{trend_result['trend']}' and spike anomaly detected (ratio: {anomalies[0]['ratio']}x).")
else:
    print("  -> Case 3 FAILED: Anomaly spike or rising trend not detected.")
    all_passed = False

if all_passed:
    print("\n=================================================================")
    print(">>> ALL PROMPT 4 PATTERN INTELLIGENCE TESTS PASSED! <<<")
    print("=================================================================")
else:
    print("\n>>> SOME TESTS FAILED <<<")
    sys.exit(1)
