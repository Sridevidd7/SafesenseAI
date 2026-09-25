"""
SafeSense AI — Pattern Intelligence & Insight Engine
=====================================================
Features:
1. Incident Similarity Clustering (Jaccard token similarity + domain weighting)
2. Repeated Incident Detection (Threshold: >= 3 incidents per cluster)
3. Temporal Trend Intelligence (Direction classification & slope reasoning)
4. Anomaly Detection (Statistical spike detection > 1.5x baseline)
5. Explainable Insight Generation (RECURRING_PATTERN, ANOMALY, CROSS_SITE_RISK, TREND)
"""
from typing import Dict, List, Set, Any, Optional, Tuple
from collections import Counter
import math
import re
import logging

logger = logging.getLogger("safesense.pattern_engine")


from services.barrier_dictionary import normalize_text

STOPWORDS: Set[str] = {
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "is", "was", "were", "are", "been", "be", "have", "has", "had",
    "this", "that", "it", "they", "we", "he", "she", "i", "you", "during", "while",
    "before", "after", "then", "into", "onto", "out", "over", "under", "about"
}

# ─── SYNONYM CANONICAL TOKEN EXPANSION MAP ──────────────────────────────────
SYNONYM_TOKEN_MAP: Dict[str, str] = {
    # Actors
    "worker": "canon_actor",
    "technician": "canon_actor",
    "operator": "canon_actor",
    "contractor": "canon_actor",
    "personnel": "canon_actor",
    "electrician": "canon_actor",
    "welder": "canon_actor",
    "crew": "canon_actor",
    "team": "canon_actor",

    # Actions
    "entered": "canon_action_entry",
    "entering": "canon_action_entry",
    "entry": "canon_action_entry",
    "went": "canon_action_entry",
    "stepped": "canon_action_entry",
    "climbed": "canon_action_height",
    "climbing": "canon_action_height",
    "servicing": "canon_action_service",
    "serviced": "canon_action_service",
    "operating": "canon_action_operate",
    "operated": "canon_action_operate",

    # Negations & Failure Indicators
    "without": "canon_negation",
    "missing": "canon_negation",
    "lacked": "canon_negation",
    "absence": "canon_negation",
    "omitted": "canon_negation",
    "skipped": "canon_negation",
    "failed": "canon_negation",

    # Energy Isolation / Live Electrical
    "energized": "canon_energized",
    "live": "canon_energized",
    "powered": "canon_energized",
    "electrical": "canon_energized",
    "electric": "canon_energized",
    "voltage": "canon_energized",
    "power": "canon_energized",
    "circuit": "canon_circuit",
    "breaker": "canon_circuit",
    "switchgear": "canon_circuit",
    "isolated": "canon_isolated",
    "isolation": "canon_isolated",
    "deenergized": "canon_isolated",
    "de-energized": "canon_isolated",
    "disconnected": "canon_isolated",
    "lockout": "canon_loto",
    "tagout": "canon_loto",
    "loto": "canon_loto",
    "padlock": "canon_loto",
    
    # Confined Space
    "vessel": "canon_confined_space",
    "tank": "canon_confined_space",
    "chamber": "canon_confined_space",
    "sump": "canon_confined_space",
    "pit": "canon_confined_space",
    "manhole": "canon_confined_space",
    "confined": "canon_confined_space",
    "reactor": "canon_confined_space",
    "column": "canon_confined_space",
    
    # Gas Testing & Atmosphere
    "gas": "canon_gas_test",
    "atmospheric": "canon_gas_test",
    "atmosphere": "canon_gas_test",
    "oxygen": "canon_gas_test",
    "h2s": "canon_gas_test",
    "sampling": "canon_gas_test",
    "monitoring": "canon_gas_test",
    "test": "canon_gas_test",
    "testing": "canon_gas_test",
    "tested": "canon_gas_test",
    "check": "canon_gas_test",
    "checked": "canon_gas_test",
    
    # Permits
    "permit": "canon_permit",
    "ptw": "canon_permit",
    "clearance": "canon_permit",
    "authorization": "canon_permit",
    "approval": "canon_permit",
    
    # Working at Height & Fall Protection
    "height": "canon_height",
    "scaffold": "canon_height",
    "ladder": "canon_height",
    "roof": "canon_height",
    "elevated": "canon_height",
    "platform": "canon_height",
    "harness": "canon_fall_protection",
    "lanyard": "canon_fall_protection",
    "lifeline": "canon_fall_protection",
    "tied": "canon_fall_protection",
    "guardrail": "canon_fall_protection",
    
    # Line of Fire / Lifting
    "crane": "canon_lifting",
    "rigging": "canon_lifting",
    "hoist": "canon_lifting",
    "suspended": "canon_lifting",
    "load": "canon_lifting",
    "sling": "canon_lifting",
    
    # Vehicle Movement
    "forklift": "canon_vehicle",
    "truck": "canon_vehicle",
    "vehicle": "canon_vehicle",
    "excavator": "canon_vehicle",
    "reversing": "canon_vehicle",
    
    # Hot Work
    "welding": "canon_hot_work",
    "torch": "canon_hot_work",
    "grinding": "canon_hot_work",
    "brazing": "canon_hot_work",
    "sparks": "canon_hot_work",
    "flame": "canon_hot_work",
    
    # Chemical Handling
    "chemical": "canon_chemical",
    "acid": "canon_chemical",
    "caustic": "canon_chemical",
    "toxic": "canon_chemical",
    "spill": "canon_chemical",
    "leak": "canon_chemical",
    
    # PPE
    "ppe": "canon_ppe",
    "gloves": "canon_ppe",
    "goggles": "canon_ppe",
    "glasses": "canon_ppe",
    "respirator": "canon_ppe",
    "helmet": "canon_ppe",
    "mask": "canon_ppe",
}


def tokenize_report(text: str) -> Set[str]:
    """
    Tokenize with text normalization and synonym expansion:
    1. Runs robust normalization (abbreviations & typo tolerance)
    2. Filters standard stopwords
    3. Expands concepts with canonical synonym group tokens for stable clustering
    """
    if not text:
        return set()
    norm = normalize_text(text)
    cleaned = re.sub(r"[^\w\s]", " ", norm.lower())
    raw_words = cleaned.split()
    
    expanded_tokens: Set[str] = set()
    for w in raw_words:
        if w not in STOPWORDS and len(w) > 2:
            expanded_tokens.add(w)
            if w in SYNONYM_TOKEN_MAP:
                expanded_tokens.add(SYNONYM_TOKEN_MAP[w])
                
    return expanded_tokens


def get_report_tokens(rep: Dict[str, Any]) -> Set[str]:
    """Extract and tokenize report description or text."""
    text = rep.get("description") or rep.get("report_text") or ""
    return tokenize_report(text)


def compute_similarity(
    rep1: Dict[str, Any],
    rep2: Dict[str, Any],
    tokens1: Optional[Set[str]] = None,
    tokens2: Optional[Set[str]] = None,
) -> float:
    """
    Computes hybrid similarity between two safety reports:
      similarity_score = 0.5 * token_similarity + 0.3 * barrier_overlap + 0.2 * rule_match

    Accepts pre-computed tokens1 / tokens2 to avoid repeated tokenization of identical reports.
    """
    if tokens1 is None:
        tokens1 = get_report_tokens(rep1)
    if tokens2 is None:
        tokens2 = get_report_tokens(rep2)

    if not tokens1 or not tokens2:
        token_similarity = 0.0
    else:
        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)
        token_similarity = intersection / union if union > 0 else 0.0

    # Barrier Overlap Score
    b1_raw = rep1.get("barrier_failures") or ([rep1.get("barrier")] if rep1.get("barrier") and rep1.get("barrier") != "Unknown Barrier Failure" else [])
    b2_raw = rep2.get("barrier_failures") or ([rep2.get("barrier")] if rep2.get("barrier") and rep2.get("barrier") != "Unknown Barrier Failure" else [])
    s1 = {b for b in b1_raw if b and b != "Unknown Barrier Failure"}
    s2 = {b for b in b2_raw if b and b != "Unknown Barrier Failure"}

    if s1 and s2:
        barrier_overlap = len(s1 & s2) / len(s1 | s2)
    elif not s1 and not s2:
        barrier_overlap = 0.5
    else:
        barrier_overlap = 0.0

    # Rule Match Score
    r1 = rep1.get("category") or rep1.get("life_saving_rule") or rep1.get("primary_rule")
    r2 = rep2.get("category") or rep2.get("life_saving_rule") or rep2.get("primary_rule")
    if r1 and r2 and r1 == r2 and r1 != "General Safety":
        rule_match = 1.0
    elif r1 and r2 and r1 == r2:
        rule_match = 0.5
    else:
        rule_match = 0.0

    similarity_score = (0.5 * token_similarity) + (0.3 * barrier_overlap) + (0.2 * rule_match)
    return round(similarity_score, 4)


def compute_adaptive_threshold(
    reports: List[Dict[str, Any]],
    precomputed_tokens: Optional[List[Set[str]]] = None,
) -> float:
    """
    Computes dataset-adaptive clustering threshold:
      threshold = mean_pairwise_similarity + 0.1
    Clamped strictly within [0.5, 0.8].
    """
    if len(reports) < 2:
        return 0.65

    if precomputed_tokens is None:
        precomputed_tokens = [get_report_tokens(r) for r in reports]

    pair_scores: List[float] = []
    n = len(reports)
    step = max(1, (n * (n - 1) // 2) // 150)
    counter = 0

    for i in range(n):
        for j in range(i + 1, n):
            counter += 1
            if counter % step == 0:
                sim = compute_similarity(
                    reports[i],
                    reports[j],
                    tokens1=precomputed_tokens[i],
                    tokens2=precomputed_tokens[j],
                )
                pair_scores.append(sim)

    if not pair_scores:
        mean_sim = 0.50
    else:
        mean_sim = sum(pair_scores) / len(pair_scores)

    raw_thresh = mean_sim + 0.10 if mean_sim < 0.50 else 0.55
    adaptive_thresh = round(max(0.50, min(0.80, raw_thresh)), 3)
    logger.info(f"[SIMILARITY_THRESHOLD] computed_threshold={adaptive_thresh} mean_similarity={mean_sim:.3f}")
    return adaptive_thresh


def cluster_reports(
    reports: List[Dict[str, Any]],
    similarity_threshold: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Similarity-based single-pass clustering of safety reports.
    Uses adaptive dataset threshold if similarity_threshold is not explicitly provided.
    Pre-tokenizes each report exactly once to avoid redundant O(N^2) tokenization.
    """
    if not reports:
        return []

    # Pre-tokenize all reports exactly once
    precomputed_tokens = [get_report_tokens(r) for r in reports]

    if similarity_threshold is None:
        effective_threshold = compute_adaptive_threshold(reports, precomputed_tokens=precomputed_tokens)
    else:
        effective_threshold = similarity_threshold
        logger.info(f"[SIMILARITY_THRESHOLD] explicit_threshold={effective_threshold}")

    raw_clusters: List[List[Dict[str, Any]]] = []
    cluster_centroid_tokens: List[Set[str]] = []

    for idx, report in enumerate(reports):
        rep_tokens = precomputed_tokens[idx]
        matched = False
        for c_idx, cluster in enumerate(raw_clusters):
            # Compare with representative centroid (first report in cluster)
            sim = compute_similarity(
                report,
                cluster[0],
                tokens1=rep_tokens,
                tokens2=cluster_centroid_tokens[c_idx],
            )
            if sim >= effective_threshold:
                cluster.append(report)
                matched = True
                break
        if not matched:
            raw_clusters.append([report])
            cluster_centroid_tokens.append(rep_tokens)


    formatted_clusters: List[Dict[str, Any]] = []

    for idx, cluster in enumerate(raw_clusters, 1):
        count = len(cluster)
        categories = [r.get("category") for r in cluster if r.get("category")]
        barriers = [r.get("barrier") for r in cluster if r.get("barrier")]
        sites = list({r.get("site") for r in cluster if r.get("site")})
        risk_scores = [float(r.get("risk_score", 50)) for r in cluster if r.get("risk_score") is not None]
        sif_count = sum(1 for r in cluster if str(r.get("sif_potential", "")).upper() == "YES")

        top_cat = Counter(categories).most_common(1)[0][0] if categories else "General Safety"
        top_bar = Counter(barriers).most_common(1)[0][0] if barriers else "Control Verification"
        avg_risk = round(sum(risk_scores) / len(risk_scores), 1) if risk_scores else 50.0

        if avg_risk >= 75 or sif_count > 0:
            risk_level = "CRITICAL"
        elif avg_risk >= 50:
            risk_level = "HIGH"
        else:
            risk_level = "MEDIUM"

        # Construct human-readable theme
        if top_bar and top_bar != "Unknown Barrier Failure":
            theme = f"Repeated {top_bar} in {top_cat}"
        else:
            theme = f"Recurring Hazards in {top_cat}"

        sample_descs = [
            (r.get("description") or r.get("report_text") or "")
            for r in cluster[:3]
            if (r.get("description") or r.get("report_text"))
        ]

        if count >= 3:
            simplified_insight = f"Repeated safety issue ({top_bar}) observed across {len(sites)} site(s) and {count} reports."
        elif len(sites) > 1:
            simplified_insight = f"Cross-site safety concern ({top_bar}) observed across {', '.join(sites[:2])}."
        else:
            simplified_insight = f"Safety observation pattern ({top_bar}) identified in {top_cat} with {count} recorded report(s)."

        formatted_clusters.append({
            "cluster_id": f"CL-{idx:03d}",
            "theme": theme,
            "category": top_cat,
            "barrier": top_bar,
            "count": count,
            "frequency": count,
            "sites": sites if sites else ["Site Alpha"],
            "avg_risk": avg_risk,
            "risk_score": int(avg_risk),
            "risk_level": risk_level,
            "sif_count": sif_count,
            "is_repeated": count >= 3,
            "sample_descriptions": sample_descs,
            "simplified_insight": simplified_insight,
            "human_insight": simplified_insight,
            "name": theme,
            "description": simplified_insight,
            "trend": "increasing" if count >= 3 and sif_count > 0 else "stable"
        })

    # Sort clusters deterministically by frequency desc, avg_risk desc, cluster_id asc
    formatted_clusters.sort(key=lambda c: (-c["count"], -c["avg_risk"], str(c.get("cluster_id", ""))))
    return formatted_clusters


def detect_repeated_failures(clusters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filters clusters that meet the threshold for recurring safety failure patterns (>= 3 reports)."""
    return [c for c in clusters if c.get("count", 0) >= 3]


def classify_trend(series_values: List[int], labels: Optional[List[str]] = None, total_reports: Optional[int] = None) -> Dict[str, str]:
    """
    Computes temporal trend direction and generates an explainable summary.
    If total dataset size < 10 reports or sum(series_values) < 10, disables deceptive trend interpretation.
    """
    total = total_reports if total_reports is not None else (sum(series_values) if series_values else 0)
    if not series_values or len(series_values) < 2 or total < 10:
        return {
            "trend": "STABLE",
            "reason": "Insufficient data for reliable trend analysis",
            "trend_note": "Insufficient data for reliable trend analysis"
        }

    first_val = series_values[0]
    last_val = series_values[-1]
    n_points = len(series_values)

    # Average of earlier half vs later half
    mid = max(1, len(series_values) // 2)
    first_half_avg = sum(series_values[:mid]) / mid
    second_half_avg = sum(series_values[mid:]) / (len(series_values) - mid)

    delta_pct = ((second_half_avg - first_half_avg) / first_half_avg * 100) if first_half_avg > 0 else 0.0

    if delta_pct >= 20.0 or (last_val > first_val and last_val >= 2 * first_val):
        trend_label = "RISING RISK"
        if labels and len(labels) >= n_points:
            reason = f"Critical incidents increased from {first_val} ({labels[0]}) → {last_val} ({labels[-1]}) over last {n_points} periods (+{int(delta_pct)}%)."
        else:
            reason = f"Incident volume increased from {first_val} → {last_val} over recent periods (+{int(delta_pct)}%)."
    elif delta_pct <= -20.0:
        trend_label = "IMPROVING"
        if labels and len(labels) >= n_points:
            reason = f"Incident frequency decreased from {first_val} ({labels[0]}) → {last_val} ({labels[-1]}) (-{abs(int(delta_pct))}%). Safety controls effective."
        else:
            reason = f"Incident volume decreased from {first_val} → {last_val} over recent observation periods."
    else:
        trend_label = "STABLE"
        reason = f"Incident rate has remained stable across observation periods (average {round(second_half_avg, 1)}/period)."

    return {
        "trend": trend_label,
        "reason": reason
    }


def detect_anomalies(monthly_series: List[Dict[str, Any]], site_stats: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """
    Detects sudden statistical spikes (>= 1.5x baseline average) in temporal and site data.
    """
    anomalies: List[Dict[str, Any]] = []

    # 1. Temporal Month-over-Month Anomaly Spike
    if len(monthly_series) >= 3:
        counts = [int(m.get("total", 0) or m.get("count", 0)) for m in monthly_series]
        current_count = counts[-1]
        prev_counts = counts[:-1]
        avg_prev = sum(prev_counts) / len(prev_counts) if prev_counts else 1.0

        if avg_prev > 0 and current_count >= 1.5 * avg_prev and current_count >= 3:
            ratio = round(current_count / avg_prev, 1)
            last_label = monthly_series[-1].get("month") or monthly_series[-1].get("period") or "Current Month"
            anomalies.append({
                "type": "TEMPORAL_SPIKE",
                "site": "Global Operations",
                "anomaly": True,
                "ratio": ratio,
                "reason": f"Incident count spiked {ratio}x in {last_label} compared to prior baseline ({current_count} vs avg {round(avg_prev, 1)})."
            })

    # 2. Site-Specific Anomaly Spike
    if site_stats and len(site_stats) >= 2:
        totals = [s.get("total", 0) for s in site_stats]
        avg_site_total = sum(totals) / len(totals) if totals else 1.0
        for s in site_stats:
            site_tot = s.get("total", 0)
            site_crit = s.get("critical", 0)
            if site_tot >= 1.8 * avg_site_total and site_tot >= 4:
                ratio = round(site_tot / avg_site_total, 1)
                anomalies.append({
                    "type": "SITE_CONCENTRATION_SPIKE",
                    "site": s.get("site", "Unknown Site"),
                    "anomaly": True,
                    "ratio": ratio,
                    "reason": f"Incident count at {s.get('site')} spiked {ratio}x higher than organization-wide site average ({site_tot} vs avg {round(avg_site_total, 1)})."
                })

    return anomalies


def generate_insights(
    reports: List[Dict[str, Any]],
    clusters: List[Dict[str, Any]],
    monthly_series: List[Dict[str, Any]],
    site_stats: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Insight Generation Layer:
    Synthesizes similarity clusters, trend direction, and anomalies into structured AI insights.
    """
    insights: List[Dict[str, Any]] = []

    # 1. Recurring Cluster Insights
    repeated = detect_repeated_failures(clusters)
    for c in repeated[:3]:
        sites = c.get("sites", [])
        site_str = f"across {len(sites)} sites ({', '.join(sites[:2])})" if len(sites) > 1 else f"at {sites[0]}" if sites else "across operations"
        insights.append({
            "type": "RECURRING_PATTERN",
            "title": c.get("theme", "Recurring Hazard Pattern"),
            "message": f"{c.get('theme')} identified with {c.get('count')} correlated incidents {site_str}.",
            "severity": c.get("risk_level", "HIGH"),
            "sites": sites,
            "metric": f"{c.get('count')} incidents",
            "cluster_id": c.get("cluster_id")
        })

    # 2. Anomaly Insights
    anomalies = detect_anomalies(monthly_series, site_stats)
    for a in anomalies:
        insights.append({
            "type": "ANOMALY",
            "title": f"Incident Volume Spike: {a.get('site', 'Operations')}",
            "message": a.get("reason"),
            "severity": "CRITICAL" if a.get("ratio", 1.0) >= 2.0 else "HIGH",
            "site": a.get("site"),
            "metric": f"{a.get('ratio', 1.0)}x spike"
        })

    # 3. Cross-Site Systemic Risk Insight
    cross_site_clusters = [c for c in clusters if len(c.get("sites", [])) >= 2 and c.get("count", 0) >= 2]
    if cross_site_clusters:
        top_cross = cross_site_clusters[0]
        insights.append({
            "type": "CROSS_SITE_RISK",
            "title": "Cross-Site Systemic Control Precursor",
            "message": f"Precursor pattern '{top_cross.get('theme')}' observed across {len(top_cross.get('sites', []))} independent facilities ({', '.join(top_cross.get('sites', []))}).",
            "severity": "HIGH",
            "sites": top_cross.get("sites"),
            "metric": f"{len(top_cross.get('sites', []))} sites affected"
        })

    # 4. Temporal Trend Insight
    if monthly_series and len(monthly_series) >= 2:
        counts = [m.get("total", 0) or m.get("count", 0) for m in monthly_series]
        labels = [m.get("month", "") or m.get("period", "") for m in monthly_series]
        total_reps = len(reports) if reports else sum(counts)
        trend_info = classify_trend(counts, labels, total_reports=total_reps)
        if trend_info["trend"] != "STABLE" and trend_info.get("trend_note") != "Insufficient data for reliable trend analysis":
            insights.append({
                "type": "TREND",
                "title": f"Operational Trajectory: {trend_info['trend']}",
                "message": trend_info["reason"],
                "severity": "CRITICAL" if trend_info["trend"] == "RISING RISK" else "MEDIUM",
                "metric": trend_info["trend"]
            })

    return insights
