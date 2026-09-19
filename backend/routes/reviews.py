"""
routes/reviews.py — Database-backed /api/reviews endpoints for Human-in-the-Loop (HITL) audit trail.

Endpoints
---------
POST /api/reviews             → Create a review decision for a safety report
GET  /api/reviews/{report_id} → Fetch all review audit history for a report
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import logging

from database import get_db
from models import Review, Report
from schemas import ReviewCreate, ReviewResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/reviews",
    tags=["Reviews"],
)

VALID_DECISIONS = {"CONFIRMED", "CORRECTED", "REJECTED"}


def _normalize_decision(decision_str: str) -> str:
    """Normalize and validate review decision."""
    d = decision_str.strip().upper()
    if d not in VALID_DECISIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid decision '{decision_str}'. Allowed values: {', '.join(sorted(VALID_DECISIONS))}.",
        )
    return d


@router.post(
    "",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a human review decision",
    description="Validates report_id and decision, records reviewer comment, and stores the audit trail in DB.",
)
def create_review(
    payload: ReviewCreate,
    db: Session = Depends(get_db),
) -> ReviewResponse:
    # ── 1. Validate report exists in DB ──────────────────────────────────────
    report = db.query(Report).filter(Report.id == payload.report_id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with id={payload.report_id} not found.",
        )

    # ── 2. Validate decision ──────────────────────────────────────────────────
    norm_decision = _normalize_decision(payload.decision)

    # ── 3. Insert into database ───────────────────────────────────────────────
    try:
        review = Review(
            report_id = payload.report_id,
            decision  = norm_decision,
            comment   = payload.comment.strip() if payload.comment else None,
            reviewer  = payload.reviewer.strip() if payload.reviewer else "HSE Officer",
        )
        db.add(review)
        db.commit()
        db.refresh(review)
        return review
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error(f"Failed to create review: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while saving review.",
        ) from exc


@router.get(
    "/{report_id}",
    response_model=list[ReviewResponse],
    summary="Fetch review history for a safety report",
    description="Returns all review decisions and comments linked to the given report_id, ordered newest first.",
)
def get_reviews_by_report(
    report_id: int,
    db: Session = Depends(get_db),
) -> list[ReviewResponse]:
    # Validate report exists
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with id={report_id} not found.",
        )

    try:
        reviews = (
            db.query(Review)
            .filter(Review.report_id == report_id)
            .order_by(Review.created_at.desc())
            .all()
        )
        return reviews
    except SQLAlchemyError as exc:
        logger.error(f"Failed to fetch reviews for report_id={report_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while fetching reviews.",
        ) from exc
