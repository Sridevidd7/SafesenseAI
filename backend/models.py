"""
models.py — SQLAlchemy ORM models (table definitions).
Each class maps directly to a database table.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Index, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


class Report(Base):
    """
    Safety report record.

    Columns
    -------
    report_id     : string primary key (e.g. user-provided ID or md5(description + date + category))
    description   : full text of the safety observation
    category      : life-saving rule category detected (e.g. "Confined Space")
    risk_level    : "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    risk_score    : integer 0–100 computed by the rule engine
    sif_potential : "YES" | "NO"
    date          : string date "YYYY-MM-DD"
    created_at    : UTC timestamp set automatically on insert
    """
    __tablename__ = "reports"

    report_id     = Column(String(64),    primary_key=True, index=True)
    content_hash  = Column(String(64),    unique=True, nullable=True)
    description   = Column(Text,          nullable=False)
    category      = Column(String(100),   nullable=False, default="General Safety")
    risk_level    = Column(String(10),    nullable=False, default="LOW")
    risk_score    = Column(Integer,       nullable=False, default=0)
    sif_potential = Column(String(3),     nullable=False, default="NO")
    site          = Column(String(100),   nullable=False, default="Site Alpha")
    unit          = Column(String(100),   nullable=False, default="Not Specified")
    area          = Column(String(100),   nullable=False, default="Not Specified")
    activity      = Column(String(100),   nullable=False, default="General Operation")
    barrier_failure = Column(String(100), nullable=True,  default="Unspecified")
    pii_detected  = Column(Integer,       nullable=False, default=0)
    pii_count     = Column(Integer,       nullable=False, default=0)
    pii_types     = Column(String(255),   nullable=True,  default="")
    date          = Column(String(50),    nullable=True, index=True)
    created_at    = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    @property
    def id(self) -> str:
        """Alias for backward compatibility with frontend expecting .id"""
        return self.report_id

    # Indexes used by dashboard and analytics GROUP BY queries
    __table_args__ = (
        Index("ix_reports_risk_level",    "risk_level"),
        Index("ix_reports_sif_potential", "sif_potential"),
        Index("ix_reports_category",      "category"),
        Index("ix_reports_site",          "site"),
        Index("ix_reports_unit",          "unit"),
        Index("ix_reports_area",          "area"),
        Index("ix_reports_activity",      "activity"),
        Index("ix_reports_barrier",       "barrier_failure"),
        Index("ix_reports_content_hash",  "content_hash", unique=True),
    )

    def __repr__(self) -> str:
        return (
            f"<Report report_id={self.report_id!r} hash={self.content_hash!r} category={self.category!r} "
            f"site={self.site!r} activity={self.activity!r} "
            f"risk_score={self.risk_score} level={self.risk_level} date={self.date!r}>"
        )


class Action(Base):
    """
    Corrective action item record.
    """
    __tablename__ = "actions"

    id          = Column(Integer,     primary_key=True, index=True, autoincrement=True)
    report_id   = Column(String(64),  ForeignKey("reports.report_id", ondelete="CASCADE"), nullable=True, index=True)
    description = Column(Text,        nullable=False)
    owner       = Column(String(100), nullable=False)
    status      = Column(String(20),  nullable=False, default="OPEN")
    deadline    = Column(String(50),  nullable=True)
    created_at  = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationship to Report model
    report = relationship("Report", backref="actions")

    def __repr__(self) -> str:
        return (
            f"<Action id={self.id} report_id={self.report_id} "
            f"owner={self.owner!r} status={self.status!r}>"
        )


class Review(Base):
    """
    Human-in-the-Loop (HITL) review audit decision.
    """
    __tablename__ = "reviews"

    id          = Column(Integer,     primary_key=True, index=True, autoincrement=True)
    report_id   = Column(String(64),  ForeignKey("reports.report_id", ondelete="CASCADE"), nullable=False, index=True)
    decision    = Column(String(20),  nullable=False)
    comment     = Column(Text,        nullable=True)
    reviewer    = Column(String(100), nullable=False, default="HSE Officer")
    created_at  = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationship to Report model
    report = relationship("Report", backref="reviews")

    def __repr__(self) -> str:
        return (
            f"<Review id={self.id} report_id={self.report_id} "
            f"decision={self.decision!r} reviewer={self.reviewer!r}>"
        )


class UploadedFile(Base):
    """
    Tracks uploaded files by MD5 hash for idempotent file-level deduplication.
    """
    __tablename__ = "uploaded_files"

    id          = Column(Integer,     primary_key=True, index=True, autoincrement=True)
    file_hash   = Column(String(64),  unique=True, index=True, nullable=False)
    filename    = Column(String(255), nullable=True)
    uploaded_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<UploadedFile id={self.id} hash={self.file_hash[:8]}... name={self.filename!r}>"


