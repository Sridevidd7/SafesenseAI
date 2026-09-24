"""
services/copilot_service.py — Backend Safety Copilot intelligence service.

Phase 3 — Grounded Safety Copilot. Orchestrates:

1. PII sanitization of user input.
2. Intent/filter extraction (deterministic — services/copilot_retrieval.py).
3. Deterministic SafeSense retrieval: scoped aggregates, trends and report
   evidence pulled from the database (never LLM-generated).
4. Pattern intelligence via the Phase 2 adapter (services/pattern_adapter.py).
5. Structured evidence-first prompt for the Groq LLM with strict grounding
   guardrails.
6. Response returned with deterministic grounding metadata so the UI can show
   exactly which database evidence backs each answer.

The LLM synthesizes retrieved evidence; it is never the source of truth. Risk
scoring, SIF classification and concept extraction logic are consumed read-only.
"""
from __future__ import annotations

import os
from typing import List, Optional

from fastapi import HTTPException, status
from groq import Groq
from sqlalchemy.orm import Session

import models
from schemas import (
    CopilotAggregate,
    CopilotChatResponse,
    CopilotGrounding,
    CopilotHistoryMessage,
    CopilotPatternInfo,
)
from services import copilot_retrieval as retrieval
from services.pattern_adapter import (
    format_pattern_context,
    get_pattern_context,
)
from services.pii_service import redact_pii

# Default Groq model
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


# ─── Legacy single-report helpers (kept for backward compatibility) ──────────

def get_baseline_summary(db: Session) -> str:
    """
    Backward-compatible macro summary of the whole database.
    Now delegates to the deterministic retrieval layer so baseline facts and the
    grounded pipeline always come from the same queries.
    """
    filters = retrieval.CopilotFilters()
    packet = retrieval.collect_evidence(db, filters)
    if not packet.has_data:
        return "Database Status: Empty. No safety reports currently recorded in the database."
    return retrieval.format_evidence_context(packet)


def format_context(baseline_summary: str, reports: List[models.Report]) -> tuple:
    """
    Backward-compatible context formatter for raw Report objects.
    Kept so existing tests and integrations that format report lists directly
    continue to work; the grounded pipeline uses format_evidence_context instead.
    PII sanitization of descriptions is preserved.
    """
    from services.copilot_retrieval import format_evidence_context, EvidencePacket

    report_lines = []
    source_ids: List[str] = []

    for r in reports:
        source_ids.append(r.report_id)
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


def _build_grounded_system_prompt(
    evidence_context: str,
    pattern_context: str,
    scope_note: str,
) -> str:
    """Compose the evidence-first system prompt with strict grounding guardrails."""
    return (
        "You are the SafeSense AI Safety Intelligence Copilot, an industrial HSE "
        "(Health, Safety & Environment) assistant grounded strictly on the organization's "
        "verified safety database.\n\n"
        "=== DETERMINISTIC SAFESENSE EVIDENCE (retrieved from the database for this question) ===\n"
        f"{evidence_context}\n"
        "=== END DETERMINISTIC EVIDENCE ===\n\n"
        f"{pattern_context}\n\n"
        "CRITICAL INSTRUCTIONS & GUARDRAILS:\n"
        "1. STRICT GROUNDING: Answer questions using ONLY the deterministic evidence, "
        "aggregates, trends and report evidence provided above. NEVER invent, extrapolate, "
        "or fabricate reports, statistics, incident counts, site names, barrier names, "
        "dates, trends, pattern names or pattern confidence values. The evidence block is "
        "your single source of truth for every number and name you state.\n"
        "2. MISSING INFORMATION: If the evidence block shows 0 reports for the requested "
        "scope, or does not contain the requested information, state explicitly that the "
        "available SafeSense data is insufficient and briefly explain what was examined. "
        "Do not invent details or fall back to general knowledge.\n"
        "3. CITATION: Whenever referring to specific incidents, observations, barrier "
        "failures or patterns, cite their Report ID or Pattern ID in square brackets "
        "(e.g., [Report SAF-2024-001], [Pattern CL-003]).\n"
        "4. FACTS VS SUGGESTIONS: Clearly separate verified database facts (EVIDENCE) from "
        "your own HSE analysis. Label generated investigation suggestions as "
        "'Copilot suggestion' — never present them as observed facts.\n"
        "5. TRENDS: Only describe a trend if the evidence block contains an assessable "
        "trend assessment. If the trend is marked NOT ASSESSABLE, say the available data "
        "is insufficient to establish a trend.\n"
        "6. PRIVACY: The evidence is PII-sanitized. Never reveal, guess or attempt to "
        "reconstruct any personal identifiers (names, employee IDs, phone numbers, "
        "emails, personal addresses). If asked for personal information, explain that "
        "personal data is not available and provide the safe aggregate information instead.\n"
        "7. SCOPE: Respect the applied filters. The filters-applied / filters-NOT-applied "
        "lines tell you exactly which scope was used; acknowledge any filter that could "
        "not be applied instead of ignoring it.\n"
        "8. RESPONSE STRUCTURE: For factual questions, answer concisely in this structure:\n"
        "Answer — the direct response, citing exact figures from the evidence.\n"
        "Evidence — bullet list of the counts, filters, date range, report IDs and/or "
        "pattern IDs that support it.\n"
        "Interpretation — one or two sentences of HSE interpretation based strictly on the "
        "evidence (and, only if relevant and clearly labeled, a Copilot suggestion).\n"
        "If evidence is insufficient, say so explicitly instead of the structure above.\n"
        "9. HSE DISCLAIMER: Maintain safety professionalism. Final safety-critical decisions, "
        "operational approvals and risk controls remain the sole responsibility of qualified "
        "site HSE personnel and management. You summarize existing analysis; you never "
        "re-classify a report's SIF potential or alter any risk score.\n\n"
        f"{scope_note}"
    )


def chat_with_copilot(
    db: Session,
    message: str,
    history: Optional[List[CopilotHistoryMessage]] = None
) -> CopilotChatResponse:
    """
    Executes the grounded SafeSense AI Copilot workflow (Phase 3):

        Question → PII sanitize → filter extraction → deterministic retrieval
        → structured evidence → (pattern adapter) → LLM synthesis → grounded response
    """
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key or not groq_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Groq API key is not configured. Please set GROQ_API_KEY in the backend environment."
        )

    model_name = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)

    # 1. PII sanitization of the user message
    sanitized_user_msg = redact_pii(message).redacted_text

    # 2. Deterministic filter extraction (validated against the database)
    filters = retrieval.extract_filters(db, message)

    # 3. Deterministic retrieval: scoped aggregates + report evidence
    try:
        packet = retrieval.collect_evidence(db, filters)
    except Exception as exc:
        # Retrieval errors must surface, never be swallowed into a hallucinated answer
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Safety Copilot database retrieval error: {str(exc)}"
        )

    evidence_context = retrieval.format_evidence_context(packet)

    # 4. Pattern intelligence via the Phase 2 adapter (never a hard dependency)
    pattern_ctx = get_pattern_context(db, sanitized_user_msg)
    pattern_context_text = format_pattern_context(
        pattern_ctx["patterns"], pattern_ctx["provider"]
    )

    scope_note = (
        f"SCOPE NOTE: This question was evaluated over {packet.total_reports} reports "
        f"matching the extracted scope. "
        + (
            f"Date range: {filters.date_label} ({filters.date_from} to {filters.date_to}). "
            if filters.date_label else ""
        )
        + (
            f"Filters that could not be applied (acknowledge this if relevant): "
            f"{'; '.join(filters.unapplied)}."
            if filters.unapplied else ""
        )
    )

    # 5. Evidence-first system prompt
    system_prompt = _build_grounded_system_prompt(
        evidence_context=evidence_context,
        pattern_context=pattern_context_text,
        scope_note=scope_note,
    )

    # 6. Conversation messages (history PII-sanitized as before)
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for h in history[-6:]:
            if h.role == "user":
                clean_content = redact_pii(h.content).redacted_text
            else:
                clean_content = h.content
            messages.append({"role": h.role, "content": clean_content})
    messages.append({"role": "user", "content": sanitized_user_msg})

    # 7. LLM synthesis
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

    # 8. Deterministic grounding metadata (computed here, not by the LLM)
    aggregates: List[CopilotAggregate] = [
        CopilotAggregate(
            metric="reports_examined",
            value=packet.total_reports,
            scope=filters.date_label or "database",
        ),
        CopilotAggregate(
            metric="sif_count",
            value=packet.sif_count,
            scope=filters.date_label or "database",
        ),
    ]
    for b in packet.barrier_frequency[:5]:
        aggregates.append(
            CopilotAggregate(
                metric=f"barrier_frequency:{b['barrier']}",
                value=b["count"],
                scope=filters.date_label or "database",
            )
        )

    grounding = CopilotGrounding(
        reports_examined=packet.total_reports,
        sif_count=packet.sif_count,
        date_range=(
            f"{filters.date_label} ({filters.date_from} to {filters.date_to})"
            if filters.date_label else None
        ),
        filters_applied=filters.applied(),
        filters_unapplied=list(filters.unapplied),
        aggregates=aggregates,
        source_reports=[ev["report_id"] for ev in packet.evidence_reports],
        patterns=[
            CopilotPatternInfo(
                pattern_id=p.pattern_id,
                pattern_type=p.pattern_type,
                description=p.description,
                frequency=p.frequency,
                trend=p.trend,
                sites=p.sites,
                activities=p.activities,
                barriers=p.barriers,
                evidence_report_ids=p.evidence_report_ids,
                confidence=p.confidence,
            )
            for p in pattern_ctx["patterns"]
        ],
        pattern_source=pattern_ctx["provider"],
    )

    return CopilotChatResponse(
        answer=answer,
        source_reports=[ev["report_id"] for ev in packet.evidence_reports],
        data_source="SQLite",
        model=model_name,
        grounding=grounding,
    )
