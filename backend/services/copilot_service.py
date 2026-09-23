"""
services/copilot_service.py — Backend Safety Copilot intelligence service.

Orchestrates:
1. PII sanitization of user input.
2. Grounded context retrieval from SQLite database (baseline summary + multi-field dynamic search).
3. PII sanitization of retrieved report text before sending to LLM.
4. Groq SDK inference (llama-3.3-70b-versatile) with strict HSE safety guardrails.
5. Extraction of cited source report IDs and structured response return.
"""
from __future__ import annotations

import os
import re
from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from groq import Groq
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

import models
from schemas import CopilotChatResponse, CopilotHistoryMessage
from services.pii_service import redact_pii

# Default Groq model
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

# Common words to filter out when tokenizing search queries
STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "if", "in", "on", "at", "to", "for",
    "with", "by", "about", "against", "between", "into", "through", "during",
    "before", "after", "above", "below", "from", "up", "down", "is", "are",
    "was", "were", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "can", "could", "shall", "should", "will", "would", "may", "might",
    "must", "what", "which", "who", "whom", "this", "that", "these", "those",
    "am", "how", "where", "when", "why", "there", "here", "all", "any", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not",
    "only", "own", "same", "so", "than", "too", "very", "s", "t", "just",
    "don", "now", "tell", "show", "give", "find", "list", "me", "our", "us",
    "we", "i", "you", "report", "reports", "safety", "database", "data", "incident",
    "incidents", "issue", "issues", "please", "help"
}


def get_baseline_summary(db: Session) -> str:
    """
    Computes a concise macro summary of the current safety database.
    Allows the LLM to accurately answer high-level questions without dumping all rows.
    """
    total_count = db.query(func.count(models.Report.report_id)).scalar() or 0
    if total_count == 0:
        return "Database Status: Empty. No safety reports currently recorded in the database."

    sif_count = db.query(func.count(models.Report.report_id)).filter(
        models.Report.sif_potential == "YES"
    ).scalar() or 0
    sif_pct = round((sif_count / total_count) * 100, 1) if total_count > 0 else 0.0

    # Risk level breakdown
    risk_counts = dict(
        db.query(models.Report.risk_level, func.count(models.Report.report_id))
        .group_by(models.Report.risk_level)
        .all()
    )

    # Top sites by total reports and SIF count
    top_sites_rows = (
        db.query(
            models.Report.site,
            func.count(models.Report.report_id).label("total"),
            func.sum(case((models.Report.sif_potential == "YES", 1), else_=0)).label("sifs")
        )
        .group_by(models.Report.site)
        .order_by(func.count(models.Report.report_id).desc())
        .limit(3)
        .all()
    )
    site_summaries = [
        f"{site} ({total} reports, {sifs or 0} SIF)"
        for site, total, sifs in top_sites_rows
    ]

    # Top categories / Life Saving Rules
    top_categories = (
        db.query(models.Report.category, func.count(models.Report.report_id))
        .group_by(models.Report.category)
        .order_by(func.count(models.Report.report_id).desc())
        .limit(3)
        .all()
    )
    cat_summaries = [f"{cat} ({cnt})" for cat, cnt in top_categories]

    # Top barrier failures
    top_barriers = (
        db.query(models.Report.barrier_failure, func.count(models.Report.report_id))
        .filter(models.Report.barrier_failure.isnot(None))
        .filter(~models.Report.barrier_failure.in_(["Unspecified", "Unknown", "Unknown Barrier Failure"]))
        .group_by(models.Report.barrier_failure)
        .order_by(func.count(models.Report.report_id).desc())
        .limit(3)
        .all()
    )
    barrier_summaries = [f"{bf} ({cnt})" for bf, cnt in top_barriers]

    # Date range
    min_date = db.query(func.min(models.Report.date)).scalar() or "N/A"
    max_date = db.query(func.max(models.Report.date)).scalar() or "N/A"

    summary_lines = [
        f"Database Overview: Total {total_count} safety reports recorded (Date range: {min_date} to {max_date}).",
        f"SIF Potential: {sif_count} reports ({sif_pct}% of total).",
        f"Risk Level Breakdown: Critical: {risk_counts.get('CRITICAL', 0)}, High: {risk_counts.get('HIGH', 0)}, Medium: {risk_counts.get('MEDIUM', 0)}, Low: {risk_counts.get('LOW', 0)}.",
        f"Top Operating Sites: {', '.join(site_summaries) if site_summaries else 'None'}.",
        f"Top Hazard Categories / LSR: {', '.join(cat_summaries) if cat_summaries else 'None'}.",
        f"Leading Barrier Failures: {', '.join(barrier_summaries) if barrier_summaries else 'None documented'}."
    ]
    return "\n".join(summary_lines)


def retrieve_relevant_reports(db: Session, sanitized_query: str, max_records: int = 8) -> List[models.Report]:
    """
    Retrieves the most relevant 5-10 safety reports based on the sanitized query.
    Uses multi-field token matching across operational fields, with risk-weighted ordering.
    Falls back to high-risk / SIF reports if no specific keywords match.
    """
    # Extract search tokens
    words = re.findall(r"[A-Za-z0-9_-]{2,}", sanitized_query.lower())
    tokens = [w for w in words if w not in STOP_WORDS]

    conditions = []
    for tok in tokens[:6]:  # Limit to top 6 meaningful tokens
        token_pattern = f"%{tok}%"
        conditions.append(
            or_(
                models.Report.description.ilike(token_pattern),
                models.Report.site.ilike(token_pattern),
                models.Report.unit.ilike(token_pattern),
                models.Report.area.ilike(token_pattern),
                models.Report.activity.ilike(token_pattern),
                models.Report.category.ilike(token_pattern),
                models.Report.barrier_failure.ilike(token_pattern),
                models.Report.report_id.ilike(token_pattern),
            )
        )

    # Base query ordered by SIF potential and risk score
    order_clause = (
        case((models.Report.sif_potential == "YES", 1), else_=0).desc(),
        models.Report.risk_score.desc(),
        models.Report.date.desc(),
    )

    if conditions:
        matched = (
            db.query(models.Report)
            .filter(or_(*conditions))
            .order_by(*order_clause)
            .limit(max_records)
            .all()
        )
        if matched:
            return matched

    # Fallback: return top highest-risk records if query is broad or no exact keyword matched
    return (
        db.query(models.Report)
        .order_by(*order_clause)
        .limit(max_records)
        .all()
    )


def format_context(baseline_summary: str, reports: List[models.Report]) -> Tuple[str, List[str]]:
    """
    Formats the baseline database metrics and retrieved reports into clean LLM context.
    Guarantees all report observation descriptions are PII-sanitized before inclusion.
    """
    report_lines = []
    source_ids = []

    for r in reports:
        source_ids.append(r.report_id)
        # Ensure description is sanitized for PII
        sanitized_desc = redact_pii(r.description or "").redacted_text.strip()
        report_block = (
            f"- [Report {r.report_id}]\n"
            f"  Date: {r.date or 'N/A'} | Site: {r.site} | Unit: {r.unit} | Area: {r.area}\n"
            f"  Activity: {r.activity} | Category: {r.category}\n"
            f"  Risk Level: {r.risk_level} (Score: {r.risk_score}) | SIF Potential: {r.sif_potential}\n"
            f"  Barrier Failure: {r.barrier_failure or 'Unspecified'}\n"
            f"  Observation: {sanitized_desc}"
        )
        report_lines.append(report_block)

    reports_section = "\n\n".join(report_lines) if report_lines else "No specific individual reports retrieved."

    full_context = (
        f"--- MACRO DATABASE METRICS ---\n"
        f"{baseline_summary}\n\n"
        f"--- RETRIEVED SAFETY REPORTS ({len(reports)} records) ---\n"
        f"{reports_section}"
    )
    return full_context, source_ids


def chat_with_copilot(
    db: Session,
    message: str,
    history: Optional[List[CopilotHistoryMessage]] = None
) -> CopilotChatResponse:
    """
    Executes the grounded SafeSense AI Copilot workflow:
    1. Check Groq API key configuration (raise 503 if missing).
    2. Sanitize user question for PII.
    3. Retrieve relevant database context from SQLite.
    4. Format context with PII-sanitized report details.
    5. Prompt Groq LLM with strict grounding and safety guardrails.
    6. Return response with source report citations.
    """
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key or not groq_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Groq API key is not configured. Please set GROQ_API_KEY in the backend environment."
        )

    model_name = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)

    # 1. PII sanitization of user message
    sanitized_user_msg = redact_pii(message).redacted_text

    # 2. Context retrieval from SQLite
    baseline_summary = get_baseline_summary(db)
    reports = retrieve_relevant_reports(db, sanitized_user_msg, max_records=8)
    context_text, source_report_ids = format_context(baseline_summary, reports)

    # 3. System prompt with strict safety instructions
    system_prompt = (
        "You are the SafeSense AI Safety Intelligence Copilot, an industrial HSE "
        "(Health, Safety & Environment) assistant grounded strictly on the organization's "
        "verified safety database.\n\n"
        "=== VERIFIED DATABASE CONTEXT ===\n"
        f"{context_text}\n"
        "=================================\n\n"
        "CRITICAL INSTRUCTIONS & GUARDRAILS:\n"
        "1. STRICT GROUNDING: Answer questions based ONLY on the verified database summary and "
        "retrieved safety reports provided above. NEVER invent, extrapolate, or fabricate reports, "
        "statistics, incident counts, site names, or dates not present in the context.\n"
        "2. MISSING INFORMATION: If the requested information or specific incident details are "
        "not present in the context or database, state explicitly: "
        "'Based on the safety database, this information is not available.' Do not invent details.\n"
        "3. CITATION: Whenever referring to specific incidents, observations, or barrier failures, "
        "cite their Report ID in square brackets (e.g., [Report SAF-2024-001]).\n"
        "4. DISTINGUISH FACTS VS INTERPRETATION: Clearly separate verified database facts from HSE "
        "recommendations or analysis.\n"
        "5. HSE DISCLAIMER: Always maintain safety professionalism. Final safety-critical decisions, "
        "operational approvals, and risk controls remain the sole responsibility of qualified site "
        "HSE personnel and management.\n"
        "6. PRIVACY: Never reveal or attempt to reconstruct any personal identifiers."
    )

    # 4. Construct messages payload
    messages = [{"role": "system", "content": system_prompt}]

    if history:
        # Take up to the last 6 messages for conversation context
        for h in history[-6:]:
            if h.role == "user":
                clean_content = redact_pii(h.content).redacted_text
            else:
                clean_content = h.content
            messages.append({"role": h.role, "content": clean_content})

    messages.append({"role": "user", "content": sanitized_user_msg})

    # 5. Call Groq client
    try:
        client = Groq(api_key=groq_api_key)
        completion = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.2,
            max_tokens=1024,
        )
        answer = completion.choices[0].message.content or ""
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Safety Copilot LLM service error: {str(exc)}"
        )

    return CopilotChatResponse(
        answer=answer,
        source_reports=source_report_ids,
        data_source="SQLite",
        model=model_name
    )
