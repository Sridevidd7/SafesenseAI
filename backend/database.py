"""
database.py — SQLAlchemy engine, session, and base setup.
Uses SQLite for zero-config local development.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# SQLite database file — created automatically on first run
DATABASE_URL = "sqlite:///./safety.db"

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
    Ensure newly added columns exist in existing SQLite tables.
    """
    from sqlalchemy import text
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
                conn.commit()
        except Exception as e:
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
