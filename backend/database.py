import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# SQLite database file — use absolute path to guarantee same DB regardless of cwd
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "safety.db")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(
    DATABASE_URL,
    # Required for SQLite: allows multiple threads to share one connection
    connect_args={"check_same_thread": False},
)

# Session factory — used as a dependency in route handlers
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


def ensure_schema_migrations():
    """
    Ensure newly added columns and constraints exist in existing SQLite tables.
    Non-destructive, idempotent, safe to execute repeatedly without dropping or altering existing data.
    """
    with engine.connect() as conn:
        try:
            # Check existing columns in reports table
            cols_res = conn.execute(text("PRAGMA table_info(reports);")).fetchall()
            existing_cols = {row[1] for row in cols_res}
            if existing_cols:
                if "site" not in existing_cols:
                    conn.execute(text("ALTER TABLE reports ADD COLUMN site VARCHAR DEFAULT 'Site Alpha';"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reports_site ON reports (site);"))
                if "unit" not in existing_cols:
                    conn.execute(text("ALTER TABLE reports ADD COLUMN unit VARCHAR DEFAULT 'Not Specified';"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reports_unit ON reports (unit);"))
                if "area" not in existing_cols:
                    conn.execute(text("ALTER TABLE reports ADD COLUMN area VARCHAR DEFAULT 'Not Specified';"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reports_area ON reports (area);"))
                if "activity" not in existing_cols:
                    conn.execute(text("ALTER TABLE reports ADD COLUMN activity VARCHAR DEFAULT 'General Operation';"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reports_activity ON reports (activity);"))
                if "barrier_failure" not in existing_cols:
                    conn.execute(text("ALTER TABLE reports ADD COLUMN barrier_failure VARCHAR DEFAULT 'Unspecified';"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reports_barrier ON reports (barrier_failure);"))
                if "pii_detected" not in existing_cols:
                    conn.execute(text("ALTER TABLE reports ADD COLUMN pii_detected BOOLEAN DEFAULT 0;"))
                if "pii_count" not in existing_cols:
                    conn.execute(text("ALTER TABLE reports ADD COLUMN pii_count INTEGER DEFAULT 0;"))
                if "pii_types" not in existing_cols:
                    conn.execute(text("ALTER TABLE reports ADD COLUMN pii_types VARCHAR DEFAULT '';"))
                if "content_hash" not in existing_cols:
                    conn.execute(text("ALTER TABLE reports ADD COLUMN content_hash VARCHAR(64);"))
                    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_reports_content_hash ON reports (content_hash);"))
                conn.commit()

                # Intelligent backfill for existing rows where barrier_failure is Unspecified or NULL
                try:
                    from services.barrier_dictionary import detect_barriers
                    cur_rows = conn.execute(text("SELECT report_id, description FROM reports WHERE barrier_failure IS NULL OR barrier_failure = 'Unspecified';")).fetchall()
                    for r_id, desc in cur_rows:
                        if desc:
                            detected = detect_barriers(desc)
                            if detected:
                                conn.execute(
                                    text("UPDATE reports SET barrier_failure = :b WHERE report_id = :rid"),
                                    {"b": detected[0], "rid": r_id}
                                )
                    conn.commit()
                except Exception:
                    pass

                # Non-destructive idempotent seed of demo dataset if no unit-specified records exist
                try:
                    enriched_count = conn.execute(text("SELECT COUNT(*) FROM reports WHERE unit IS NOT NULL AND unit != 'Not Specified';")).scalar()
                    if enriched_count == 0:
                        demo_csv_path = os.path.join(os.path.dirname(BASE_DIR), "demo_dataset.csv")
                        if not os.path.exists(demo_csv_path):
                            demo_csv_path = os.path.join(BASE_DIR, "demo_dataset.csv")
                        if os.path.exists(demo_csv_path):
                            from services.upload_service import process_csv_upload
                            with open(demo_csv_path, "rb") as f:
                                data = f.read()
                            with SessionLocal() as db_sess:
                                process_csv_upload(db_sess, data, "demo_dataset.csv")
                except Exception:
                    pass
        except Exception:
            # Table might not exist yet on fresh start, create_all handles it
            pass

ensure_schema_migrations()



def get_db():
    """
    FastAPI dependency that yields a database session
    and guarantees it is closed after the request completes.

    Usage in a route:
        db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
