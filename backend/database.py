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
                if "activity" not in existing_cols:
                    conn.execute(text("ALTER TABLE reports ADD COLUMN activity VARCHAR DEFAULT 'General Operation';"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reports_activity ON reports (activity);"))
                if "content_hash" not in existing_cols:
                    conn.execute(text("ALTER TABLE reports ADD COLUMN content_hash VARCHAR(64);"))
                    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_reports_content_hash ON reports (content_hash);"))
                conn.commit()
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
