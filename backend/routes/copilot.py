"""
routes/copilot.py — SafeSense AI Safety Copilot endpoints.

Endpoints
---------
POST /api/copilot/chat         → Blocking grounded answer (backward compatible).
POST /api/copilot/chat/stream  → Server-Sent Events stream with REAL workflow
                                 stages and TRUE token streaming from the LLM.

Streaming protocol (SSE, one JSON object per `data:` line):

  {"type": "stage",    "stage": "RETRIEVE", "label": "...", "status": "active"}
  {"type": "stage_done", "stage": "RETRIEVE", "duration_ms": 42}
  {"type": "token",    "content": "partial answer text"}
  {"type": "complete", "answer": "...", "model": "...", "data_source": "...",
                        "grounding": {...}, "source_reports": [...]}
  {"type": "error",    "message": "sanitized error"}

Every stage corresponds to an actual backend operation — progress is never
simulated. The LLM is a synthesis layer only; grounding metadata is computed
deterministically and sent in the final event.
"""
import json
import logging
import os
import time
from typing import Optional

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db, IS_SQLITE
from schemas import (
    CopilotAggregate,
    CopilotChatRequest,
    CopilotChatResponse,
    CopilotGrounding,
    CopilotPatternInfo,
)
from services import copilot_retrieval as retrieval
from services.auth import require_authenticated
from services.copilot_service import (
    DEFAULT_GROQ_MODEL,
    _build_grounded_system_prompt,
)
from services.pattern_adapter import (
    format_pattern_context,
    get_pattern_context,
)
from services.pii_service import redact_pii

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/copilot",
    tags=["Copilot"],
    dependencies=[Depends(require_authenticated)],
)


@router.post(
    "/chat",
    response_model=CopilotChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with SafeSense AI Safety Copilot",
    description="Analyzes the natural language question, sanitizes PII, retrieves verified safety context, and synthesizes a grounded answer via the configured LLM.",
)
def copilot_chat_endpoint(
    payload: CopilotChatRequest,
    db: Session = Depends(get_db),
):
    from services.copilot_service import chat_with_copilot

    return chat_with_copilot(
        db=db,
        message=payload.message,
        history=payload.history,
    )


# ─── SSE helpers ──────────────────────────────────────────────────────────────

def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


# ─── Streaming endpoint ───────────────────────────────────────────────────────

@router.post(
    "/chat/stream",
    summary="Stream a grounded Copilot answer with real workflow progress (SSE)",
    description=(
        "Server-Sent Events stream. Emits real workflow stages (sanitize, "
        "understand, retrieve, SIF/barrier/pattern analysis, evidence), then "
        "streams the LLM answer token-by-token, then a final complete event "
        "with deterministic grounding metadata."
    ),
)
def copilot_chat_stream(
    payload: CopilotChatRequest,
    db: Session = Depends(get_db),
):
    def event_stream():
        stage_t0 = time.perf_counter()

        def stage(name: str, label: str):
            return _sse({"type": "stage", "stage": name, "label": label, "status": "active"})

        def stage_done(name: str):
            nonlocal stage_t0
            now = time.perf_counter()
            dur = int((now - stage_t0) * 1000)
            stage_t0 = now
            return _sse({"type": "stage_done", "stage": name, "duration_ms": dur})

        try:
            # ── 1. SANITIZE — PII protection of the user input ────────────────
            yield stage("SANITIZE", "Protecting sensitive information")
            pii_res = redact_pii(payload.message)
            sanitized_user_msg = pii_res.redacted_text
            pii_found = pii_res.pii_detected
            yield stage_done("SANITIZE")

            # ── 2. UNDERSTAND — deterministic filter/scope extraction ─────────
            yield stage("UNDERSTAND", "Understanding your question")
            filters = retrieval.extract_filters(db, payload.message)
            yield stage_done("UNDERSTAND")

            # ── 3. RETRIEVE — deterministic evidence collection from the DB ───
            yield stage("RETRIEVE", "Searching verified safety reports")
            try:
                packet = retrieval.collect_evidence(db, filters)
            except Exception as exc:
                logger.error("Copilot retrieval error: %s", exc)
                yield _sse({"type": "error", "message": "Safety Copilot database retrieval error."})
                return
            yield stage_done("RETRIEVE")

            # ── 4. SIF ANALYSIS — read deterministic SIF evidence ─────────────
            yield stage("SIF_ANALYSIS", "Checking SIF precursor evidence")
            sif_count = packet.sif_count
            yield stage_done("SIF_ANALYSIS")

            # ── 5. BARRIER ANALYSIS — read deterministic barrier evidence ─────
            yield stage("BARRIER_ANALYSIS", "Checking failed safety barriers")
            top_barriers = packet.barrier_frequency[:5]
            yield stage_done("BARRIER_ANALYSIS")

            # ── 6. PATTERN ANALYSIS — Phase 2 adapter (cached) ────────────────
            yield stage("PATTERN_ANALYSIS", "Checking recurring safety patterns")
            pattern_ctx = get_pattern_context(db, sanitized_user_msg)
            pattern_context_text = format_pattern_context(
                pattern_ctx["patterns"], pattern_ctx["provider"]
            )
            yield stage_done("PATTERN_ANALYSIS")

            # ── 7. EVIDENCE — build the grounded evidence prompt ──────────────
            yield stage("EVIDENCE", "Building grounded evidence")
            evidence_context = retrieval.format_evidence_context(packet)
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
            system_prompt = _build_grounded_system_prompt(
                evidence_context=evidence_context,
                pattern_context=pattern_context_text,
                scope_note=scope_note,
            )

            messages = [{"role": "system", "content": system_prompt}]
            if payload.history:
                for h in payload.history[-6:]:
                    if h.role == "user":
                        clean_content = redact_pii(h.content).redacted_text
                    else:
                        clean_content = h.content
                    messages.append({"role": h.role, "content": clean_content})
            messages.append({"role": "user", "content": sanitized_user_msg})
            yield stage_done("EVIDENCE")

            # ── 8. GENERATION — true token streaming from the configured LLM ──
            yield stage("GENERATION", "Generating grounded response")

            groq_api_key = os.getenv("GROQ_API_KEY")
            if not groq_api_key or not groq_api_key.strip():
                yield _sse({
                    "type": "error",
                    "message": "Groq API key is not configured. Safety Copilot requires GROQ_API_KEY.",
                })
                return

            model_name = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
            answer_parts = []
            try:
                from groq import Groq
                client = Groq(api_key=groq_api_key)
                stream = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=1024,
                    stream=True,
                )
                for chunk in stream:
                    try:
                        delta = chunk.choices[0].delta.content
                    except (AttributeError, IndexError):
                        delta = None
                    if delta:
                        answer_parts.append(delta)
                        yield _sse({"type": "token", "content": delta})
                try:
                    stream.close()
                except Exception:
                    pass
            except Exception as exc:
                logger.error("Copilot LLM streaming error: %s", exc)
                yield _sse({"type": "error", "message": "Safety Copilot LLM service error."})
                return

            answer = "".join(answer_parts)
            yield stage_done("GENERATION")

            # ── 9. COMPLETE — deterministic grounding metadata ────────────────
            aggregates = [
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

            yield _sse({
                "type": "complete",
                "answer": answer,
                "source_reports": [ev["report_id"] for ev in packet.evidence_reports],
                "data_source": "SQLite (local)" if IS_SQLITE else "PostgreSQL",
                "model": model_name,
                "grounding": json.loads(grounding.model_dump_json()),
                "pii_detected_in_question": bool(pii_found),
            })

        except Exception as exc:  # never leak internals to the client
            logger.exception("Copilot stream failed")
            yield _sse({"type": "error", "message": "Safety Copilot encountered an unexpected error."})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
