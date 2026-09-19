"""
routes/actions.py — Database-backed /api/actions endpoints.

Endpoints
---------
POST  /api/actions             → Create a new corrective action
GET   /api/actions             → Fetch all actions (ordered newest first)
GET   /api/actions/{report_id} → Fetch actions for a specific safety report
PATCH /api/actions/{id}        → Update status or fields of an existing action
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import logging

from database import get_db
from models import Action, Report
from schemas import ActionCreate, ActionUpdate, ActionResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/actions",
    tags=["Actions"],
)

VALID_STATUSES = {"OPEN", "IN_PROGRESS", "COMPLETED", "OVERDUE"}


def _normalize_status(status_str: str) -> str:
    """Normalize status string to uppercase with underscores."""
    s = status_str.strip().upper().replace(" ", "_")
    return s if s in VALID_STATUSES else status_str.strip()


@router.post(
    "",
    response_model=ActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new corrective action",
    description="Validates input, checks report_id if provided, and saves the action to the database.",
)
def create_action(
    payload: ActionCreate,
    db: Session = Depends(get_db),
) -> ActionResponse:
    # ── 1. Validate report_id if specified ───────────────────────────────────
    if payload.report_id is not None:
        report = db.query(Report).filter(Report.id == payload.report_id).first()
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with id={payload.report_id} not found.",
            )

    # ── 2. Normalize status ───────────────────────────────────────────────────
    norm_status = _normalize_status(payload.status)

    # ── 3. Insert and persist ─────────────────────────────────────────────────
    try:
        action = Action(
            report_id   = payload.report_id,
            description = payload.description.strip(),
            owner       = payload.owner.strip(),
            status      = norm_status,
            deadline    = payload.deadline.strip() if payload.deadline else None,
        )
        db.add(action)
        db.commit()
        db.refresh(action)
        return action
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error(f"Failed to create action: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while saving corrective action.",
        ) from exc


@router.get(
    "",
    response_model=list[ActionResponse],
    summary="Fetch all corrective actions",
    description="Returns all stored actions ordered by newest created first.",
)
def get_all_actions(
    db: Session = Depends(get_db),
) -> list[ActionResponse]:
    try:
        return db.query(Action).order_by(Action.created_at.desc()).all()
    except SQLAlchemyError as exc:
        logger.error(f"Failed to fetch actions: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while fetching corrective actions.",
        ) from exc


@router.get(
    "/{report_id}",
    response_model=list[ActionResponse],
    summary="Fetch actions for a specific report",
    description="Returns all actions linked to the given report_id.",
)
def get_actions_by_report(
    report_id: int,
    db: Session = Depends(get_db),
) -> list[ActionResponse]:
    try:
        actions = db.query(Action).filter(Action.report_id == report_id).order_by(Action.created_at.desc()).all()
        return actions
    except SQLAlchemyError as exc:
        logger.error(f"Failed to fetch actions for report_id={report_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while querying actions.",
        ) from exc


@router.patch(
    "/{id}",
    response_model=ActionResponse,
    summary="Update an existing corrective action",
    description="Updates action status or fields.",
)
def update_action(
    id: int,
    payload: ActionUpdate,
    db: Session = Depends(get_db),
) -> ActionResponse:
    action = db.query(Action).filter(Action.id == id).first()
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action with id={id} not found.",
        )

    # If updating report_id, check it exists
    if payload.report_id is not None:
        report = db.query(Report).filter(Report.id == payload.report_id).first()
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with id={payload.report_id} not found.",
            )
        action.report_id = payload.report_id

    if payload.description is not None:
        action.description = payload.description.strip()

    if payload.owner is not None:
        action.owner = payload.owner.strip()

    if payload.status is not None:
        action.status = _normalize_status(payload.status)

    if payload.deadline is not None:
        action.deadline = payload.deadline.strip()

    try:
        db.commit()
        db.refresh(action)
        return action
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error(f"Failed to update action id={id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while updating action.",
        ) from exc
