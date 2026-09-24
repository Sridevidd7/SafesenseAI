"""
scripts/migrate_sqlite_to_postgres.py — Phase 6 Batch 3.

One-off data migration from the SQLite database to PostgreSQL using the
application's SQLAlchemy models, so IDs, hashes and relationships are
preserved exactly.

SAFETY / INTEGRITY GUARANTEES
-----------------------------
- The SQLite source is opened READ-ONLY in intent: rows are only selected,
  never updated or deleted. Safety semantics (risk, SIF, barriers, LSRs) are
  copied byte-for-byte; nothing is recomputed during migration.
- PII-redacted report text is migrated exactly as stored.
- IDs and content hashes are NOT regenerated.
- Parents are inserted before children (reports -> actions/reviews/
  report_embeddings).
- Idempotent: rows that already exist in PostgreSQL (matched by primary key)
  are skipped, so re-running never duplicates data.
- Post-migration verification: table counts, content_hash integrity,
  report_id integrity, child foreign-key integrity. Exit code 1 on failure.

Usage:
    cd backend
    DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/safesense \
        python ../scripts/migrate_sqlite_to_postgres.py [--dry-run]

The SOURCE SQLite database is always backend/safety.db (the application's
default local database), independent of DATABASE_URL.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

# Make backend modules importable when run from anywhere
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, BACKEND_DIR)


def _log(message: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat()}] {message}", flush=True)


def _open_source_sqlite(source_path: str = None):
    """Open the SQLite source with the application models (read usage only)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_path = source_path or os.path.join(BACKEND_DIR, "safety.db")
    if not os.path.exists(db_path):
        _log(f"FATAL: SQLite source database not found at {db_path}")
        sys.exit(2)

    source_url = f"sqlite:///{db_path}"
    engine = create_engine(source_url, connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)
    return engine, Session()


def _open_target_postgres():
    """Open the PostgreSQL target using DATABASE_URL (must be a PG URL)."""
    from sqlalchemy.orm import sessionmaker

    from database import DATABASE_URL, IS_SQLITE

    if IS_SQLITE:
        _log(
            "FATAL: DATABASE_URL is not a PostgreSQL URL. Set DATABASE_URL to\n"
            "      postgresql+psycopg://user:pass@host:5432/safesense and ensure\n"
            "      the schema exists (alembic upgrade head)."
        )
        sys.exit(2)
    from database import create_database_engine

    engine = create_database_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    return engine, Session()


def _ensure_target_schema(engine) -> None:
    """Ensure the target schema exists (Alembic-managed databases)."""
    from database import Base

    # Importing models registers every table on Base.metadata
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def _row_dict(obj) -> dict:
    """Extract plain column values from an ORM instance."""
    return {
        col.name: getattr(obj, col.name)
        for col in obj.__table__.columns
    }


def migrate(dry_run: bool = False, source_path: str = None) -> int:
    from sqlalchemy import func as sa_func

    import models

    src_engine, src = _open_source_sqlite(source_path)
    tgt_engine, tgt = _open_target_postgres()

    # Migration order: parents before children. report_embeddings last since
    # it references reports and may only exist on newer schemas.
    TABLE_ORDER = [
        ("reports", models.Report, "report_id"),
        ("uploaded_files", models.UploadedFile, "id"),
        ("actions", models.Action, "id"),
        ("reviews", models.Review, "id"),
        ("report_embeddings", models.ReportEmbedding, ("report_id", "model_id")),
    ]

    try:
        _ensure_target_schema(tgt_engine)

        _log("=== SQLite -> PostgreSQL migration " + ("(DRY RUN) " if dry_run else "") + "===")

        # Count source rows
        source_counts = {}
        for name, model, _pk in TABLE_ORDER:
            source_counts[name] = src.query(sa_func.count(getattr(model, model.__table__.primary_key.columns.keys()[0]))).scalar() or 0
        _log("Source counts: " + ", ".join(f"{k}={v}" for k, v in source_counts.items()))

        migrated_counts = {name: 0 for name, _, _ in TABLE_ORDER}
        skipped_counts = {name: 0 for name, _, _ in TABLE_ORDER}

        if not dry_run:
            # ── Phase A: reports (parents) ────────────────────────────────
            src_rows = src.query(models.Report).all()
            for row in src_rows:
                data = _row_dict(row)
                exists = tgt.query(models.Report).filter_by(report_id=data["report_id"]).first()
                if exists:
                    skipped_counts["reports"] += 1
                    continue
                tgt.add(models.Report(**data))
                migrated_counts["reports"] += 1
            tgt.commit()
            _log(f"reports: migrated={migrated_counts['reports']} skipped(existing)={skipped_counts['reports']}")

            # ── Phase B: uploaded_files ───────────────────────────────────
            src_rows = src.query(models.UploadedFile).all()
            for row in src_rows:
                data = _row_dict(row)
                exists = tgt.query(models.UploadedFile).filter_by(id=data["id"]).first()
                if exists:
                    skipped_counts["uploaded_files"] += 1
                    continue
                tgt.add(models.UploadedFile(**data))
                migrated_counts["uploaded_files"] += 1
            tgt.commit()
            _log(f"uploaded_files: migrated={migrated_counts['uploaded_files']} skipped(existing)={skipped_counts['uploaded_files']}")

            # ── Phase C: actions ──────────────────────────────────────────
            src_rows = src.query(models.Action).all()
            for row in src_rows:
                data = _row_dict(row)
                exists = tgt.query(models.Action).filter_by(id=data["id"]).first()
                if exists:
                    skipped_counts["actions"] += 1
                    continue
                tgt.add(models.Action(**data))
                migrated_counts["actions"] += 1
            tgt.commit()
            _log(f"actions: migrated={migrated_counts['actions']} skipped(existing)={skipped_counts['actions']}")

            # ── Phase D: reviews ──────────────────────────────────────────
            src_rows = src.query(models.Review).all()
            for row in src_rows:
                data = _row_dict(row)
                exists = tgt.query(models.Review).filter_by(id=data["id"]).first()
                if exists:
                    skipped_counts["reviews"] += 1
                    continue
                tgt.add(models.Review(**data))
                migrated_counts["reviews"] += 1
            tgt.commit()
            _log(f"reviews: migrated={migrated_counts['reviews']} skipped(existing)={skipped_counts['reviews']}")

            # ── Phase E: report_embeddings (optional table) ───────────────
            try:
                src_rows = src.query(models.ReportEmbedding).all()
            except Exception:
                src_rows = []
            for row in src_rows:
                data = _row_dict(row)
                exists = (
                    tgt.query(models.ReportEmbedding)
                    .filter_by(report_id=data["report_id"], model_id=data["model_id"])
                    .first()
                )
                if exists:
                    skipped_counts["report_embeddings"] += 1
                    continue
                tgt.add(models.ReportEmbedding(**data))
                migrated_counts["report_embeddings"] += 1
            tgt.commit()
            _log(f"report_embeddings: migrated={migrated_counts['report_embeddings']} skipped(existing)={skipped_counts['report_embeddings']}")
        else:
            # Dry run: compute what WOULD be skipped, based on existing target rows
            for name, model, pk in TABLE_ORDER:
                if name == "report_embeddings":
                    existing_keys = {
                        (r[0], r[1]) for r in tgt.query(
                            models.ReportEmbedding.report_id, models.ReportEmbedding.model_id
                        ).all()
                    }
                    src_keys = {
                        (r[0], r[1]) for r in src.query(
                            models.ReportEmbedding.report_id, models.ReportEmbedding.model_id
                        ).all()
                    }
                else:
                    pk_col = getattr(model, pk if isinstance(pk, str) else pk[0])
                    existing_keys = {r[0] for r in tgt.query(pk_col).all()}
                    src_keys = {r[0] for r in src.query(pk_col).all()}
                already = len(src_keys & existing_keys)
                skipped_counts[name] = already
                migrated_counts[name] = max(0, len(src_keys) - already)
            _log("Dry-run plan: " + ", ".join(
                f"{k}: would_migrate={migrated_counts[k]} already_present={skipped_counts[k]}"
                for k in migrated_counts
            ))

        # ── Verification (always; dry run verifies source/plan consistency) ──
        _log("=== Verification ===")
        failures: list[str] = []

        if not dry_run:
            # 1. Table counts
            for name, model, _pk in TABLE_ORDER:
                src_count = src.query(sa_func.count()).select_from(model).scalar() or 0
                tgt_count = tgt.query(sa_func.count()).select_from(model).scalar() or 0
                status = "OK" if tgt_count >= src_count else "FAIL"
                _log(f"  counts {name}: source={src_count} target={tgt_count} [{status}]")
                if tgt_count < src_count:
                    failures.append(f"{name}: target count {tgt_count} < source {src_count}")

            # 2. content_hash integrity: every source hash must exist in target
            src_hashes = {r[0] for r in src.query(models.Report.content_hash).all() if r[0]}
            tgt_hashes = {r[0] for r in tgt.query(models.Report.content_hash).all() if r[0]}
            missing = src_hashes - tgt_hashes
            _log(f"  content_hash integrity: {len(src_hashes)} source hashes, missing in target: {len(missing)}")
            if missing:
                failures.append(f"content_hash missing in target: {sorted(missing)[:5]}")

            # 3. report_id integrity
            src_ids = {r[0] for r in src.query(models.Report.report_id).all()}
            tgt_ids = {r[0] for r in tgt.query(models.Report.report_id).all()}
            missing_ids = src_ids - tgt_ids
            _log(f"  report_id integrity: {len(src_ids)} source ids, missing in target: {len(missing_ids)}")
            if missing_ids:
                failures.append(f"report_id missing in target: {sorted(missing_ids)[:5]}")

            # 4. Child foreign-key integrity
            orphan_actions = tgt.query(models.Action).filter(
                ~models.Action.report_id.in_(tgt.query(models.Report.report_id))
            ).count()
            orphan_reviews = tgt.query(models.Review).filter(
                ~models.Review.report_id.in_(tgt.query(models.Report.report_id))
            ).count()
            _log(f"  child FK integrity: orphan actions={orphan_actions}, orphan reviews={orphan_reviews}")
            if orphan_actions or orphan_reviews:
                failures.append("orphan child rows detected in target")

            # 5. Safety-semantics spot check: risk/SIF values must be identical
            src_report_map = {r.report_id: (r.risk_score, r.sif_potential) for r in src.query(models.Report).all()}
            mismatches = 0
            for rpt in tgt.query(models.Report).all():
                expected = src_report_map.get(rpt.report_id)
                if expected and (rpt.risk_score, rpt.sif_potential) != expected:
                    mismatches += 1
            _log(f"  safety semantics spot-check: {mismatches} risk/SIF mismatches")
            if mismatches:
                failures.append(f"{mismatches} reports have altered risk/SIF values in target")
        else:
            _log("  (dry run: no verification against migrated data)")

        src.close()
        tgt.close()

        if failures:
            _log("=== INTEGRITY VERIFICATION FAILED ===")
            for f in failures:
                _log(f"  - {f}")
            return 1

        _log("=== Migration complete: integrity verified ===")
        return 0

    finally:
        src_engine.dispose()
        tgt_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate SafeSense SQLite data to PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="Plan the migration without writing")
    parser.add_argument(
        "--source",
        default=None,
        help="Path to the source SQLite file (default: backend/safety.db)",
    )
    args = parser.parse_args()
    sys.exit(migrate(dry_run=args.dry_run, source_path=args.source))
