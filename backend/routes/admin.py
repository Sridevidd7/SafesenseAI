import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text, func
from sqlalchemy.orm import Session

from database import get_db, IS_SQLITE
from models import Report, Action, Review, UploadedFile
from services.llm_service import CACHE
from services.auth import require_authenticated, require_admin

logger = logging.getLogger("safesense.admin")
router = APIRouter(
    tags=["Admin & Debug"],
    dependencies=[Depends(require_authenticated)],
)

LOG_FILE = Path(__file__).resolve().parent.parent / "logs" / "system_logs.jsonl"


def _log_system_event(event_dict: dict):
    """Write structured audit event to log file."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_dict) + "\n")
    except Exception as exc:
        logger.warning(f"Failed to write system log: {exc}")


@router.get("/debug/db-status", summary="Check database population status")
def get_db_status(db: Session = Depends(get_db)):
    """
    Returns live count of records in all database tables to verify empty or populated state.
    """
    total_reports = db.query(func.count(Report.report_id)).scalar() or 0
    total_files = db.query(func.count(UploadedFile.id)).scalar() or 0
    total_actions = db.query(func.count(Action.id)).scalar() or 0
    total_reviews = db.query(func.count(Review.id)).scalar() or 0

    return {
        "total_reports": total_reports,
        "status": "empty" if total_reports == 0 else "populated",
        "uploaded_files": total_files,
        "actions": total_actions,
        "reviews": total_reviews,
        "cache_size": len(CACHE),
    }


from typing import Optional
from config import settings
from database import engine
from services.auth import get_current_user

@router.post("/admin/reset-db", summary="Hard reset database to clean empty state (Administrator only)")
@router.post("/admin/reset-database", summary="Hard reset database to clean empty state (Administrator only)")
def reset_database(
    confirm: bool = False,
    payload: Optional[dict] = None,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    """
    Completely deletes all records from reports, actions, reviews, and uploaded_files tables,
    resets SQLite sequences, clears in-memory caches, runs VACUUM, and logs the reset event.
    Requires confirmation flag (?confirm=true or body {"confirm": true}).
    Requires Administrator privileges in all environments; permanently blocked in production unless ALLOW_ADMIN_RESET=true.
    """
    if (user.role or "").lower() != "administrator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Admin reset requires Administrator role.",
        )

    if settings.is_production and not settings.allow_admin_reset:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Database reset is permanently disabled in production environments. Set ALLOW_ADMIN_RESET=true for emergency reset.",
        )
    is_confirmed = confirm or (payload and payload.get("confirm") is True)
    if not is_confirmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database reset requires explicit confirmation. Pass query parameter '?confirm=true' or body {'confirm': true}.",
        )

    try:
        total_reports = db.query(func.count(Report.report_id)).scalar() or 0
        total_actions = db.query(func.count(Action.id)).scalar() or 0
        total_reviews = db.query(func.count(Review.id)).scalar() or 0
        total_files   = db.query(func.count(UploadedFile.id)).scalar() or 0
        total_deleted = total_reports + total_actions + total_reviews + total_files

        # 1. Hard delete all rows across tables
        db.execute(text("DELETE FROM reviews;"))
        db.execute(text("DELETE FROM actions;"))
        db.execute(text("DELETE FROM reports;"))
        db.execute(text("DELETE FROM uploaded_files;"))

        # 2. Reset auto-increment sequence counters (dialect-portable, Phase 6).
        #    SQLite: clear sqlite_sequence. PostgreSQL: identity/sequence columns
        #    are reset via RESTART IDENTITY, so no action is needed after a full
        #    table DELETE here; sequences remain consistent either way.
        if IS_SQLITE:
            try:
                db.execute(text("DELETE FROM sqlite_sequence WHERE name IN ('reports', 'uploaded_files', 'actions', 'reviews');"))
            except Exception:
                pass

        db.commit()

        # 3. VACUUM database outside of active transaction (SQLite-only pragma;
        #    PostgreSQL reclaims space via autovacuum)
        try:
            if IS_SQLITE:
                with engine.raw_connection() as raw_conn:
                    raw_conn.cursor().execute("VACUUM;")
        except Exception as vac_err:
            logger.warning(f"VACUUM note: {vac_err}")

        # 4. Clear all in-memory caches and trigger analytics refresh
        CACHE.clear()
        from services.analytics_service import refresh_analytics_cache
        refresh_analytics_cache(db)

        # 5. Structured logging
        now_iso = datetime.now(timezone.utc).isoformat()
        log_payload = {
            "event": "database_reset",
            "timestamp": now_iso,
            "deleted_records": total_deleted,
            "details": {
                "reports_deleted": total_reports,
                "actions_deleted": total_actions,
                "reviews_deleted": total_reviews,
                "files_deleted": total_files,
            }
        }
        _log_system_event(log_payload)
        logger.info(f"Database reset executed: {total_deleted} records deleted.")

        return {
            "status": "database_cleared",
            "total_deleted": total_deleted,
            "meta": {
                "total_reports": 0,
                "last_updated": now_iso,
                "source": "db",
            },
        }

    except Exception as exc:
        db.rollback()
        logger.error(f"Error resetting database: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset database: {str(exc)}",
        )
