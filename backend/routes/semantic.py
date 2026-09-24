"""
routes/semantic.py — Phase 5 ML-assisted semantic layer endpoints.

Advisory-only API surface for semantic signals:

POST /api/semantic/analyze
    → confidence-scored, deterministically-validated semantic candidates for
      arbitrary report text (PII-sanitized before any processing).
GET  /api/semantic/model-info
    → model provenance, availability, thresholds and degraded reason.

SAFETY BOUNDARY: these endpoints expose ML semantic candidates and their
deterministic validation verdicts. They never return or influence risk scores,
SIF classification or any safety decision. ML similarity is explicitly labeled
advisory and is not proof of a safety violation.
"""
import logging
from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.pii_service import redact_pii
from services import semantic_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/semantic",
    tags=["Semantic Layer (Phase 5)"],
)


class SemanticAnalyzeRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Free safety-report text to analyze semantically",
    )
    top_k: int = Field(
        3,
        ge=1,
        le=5,
        description="Maximum number of semantic candidates to return",
    )


@router.post(
    "/analyze",
    summary="ML-assisted semantic candidates with deterministic validation",
    description=(
        "Returns confidence-scored semantic matches against the canonical safety "
        "concept bank. Every candidate carries its deterministic validation "
        "verdict (accepted/rejected) and evidence. Advisory only — never a "
        "safety classification."
    ),
)
def semantic_analyze_endpoint(payload: SemanticAnalyzeRequest) -> Dict[str, Any]:
    # PII protection: sanitize before any semantic processing
    sanitized = redact_pii(payload.text).redacted_text
    result = semantic_service.suggest_and_validate(sanitized, top_k=payload.top_k)
    result["advisory_only"] = True
    return result


@router.get(
    "/model-info",
    summary="Semantic layer model provenance and availability",
)
def semantic_model_info_endpoint() -> Dict[str, Any]:
    info = semantic_service.get_model_info()
    info["advisory_only"] = True
    info["safety_boundary"] = (
        "ML semantic similarity is advisory. Risk scoring, SIF classification, "
        "barrier determination and all safety decisions remain exclusively "
        "deterministic."
    )
    return info
