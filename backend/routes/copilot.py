"""
routes/copilot.py — Endpoints for SafeSense AI Safety Copilot.

Endpoints
---------
POST /api/copilot/chat → Submit a natural language question and receive a grounded HSE answer with citations.
"""
import logging
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from database import get_db
from schemas import CopilotChatRequest, CopilotChatResponse
from services.copilot_service import chat_with_copilot

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/copilot",
    tags=["Copilot"],
)


@router.post(
    "/chat",
    response_model=CopilotChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with SafeSense AI Safety Copilot",
    description="Analyzes the natural language question, sanitizes PII, retrieves relevant SQLite safety context, and queries Groq LLM."
)
def copilot_chat_endpoint(
    payload: CopilotChatRequest,
    db: Session = Depends(get_db)
):
    """
    Handles user chat interaction with Safety Copilot.
    """
    return chat_with_copilot(
        db=db,
        message=payload.message,
        history=payload.history
    )
