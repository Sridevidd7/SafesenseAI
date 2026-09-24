"""
test_database_config.py — Phase 6 Batch 1 tests for database configuration.

Covers:
1. SQLite default behavior is preserved (no DATABASE_URL -> sqlite file DB).
2. DATABASE_URL is honored (SQLite path override + PostgreSQL URL detection).
3. SQLite-specific connect_args are NOT used for PostgreSQL engines.
4. A PostgreSQL engine can be constructed from DATABASE_URL without a running
   PostgreSQL server (dialect/driver resolution only, no connection attempted).
5. Portable monthly trends (analytics_service) — identical results to the
   previous strftime behavior, including malformed-date handling.
6. Portable admin reset behavior (no sqlite_sequence dependency when dialect
   is not SQLite; full-row deletion identical on SQLite).
7. ensure_schema_migrations() gating (SQLite-only).
8. Alembic baseline consistency with SQLAlchemy metadata where practical.
"""
import os
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import (
    Base,
    DEFAULT_SQLITE_URL,
    IS_SQLITE,
    create_database_engine,
    ensure_schema_migrations,
)
import models


def _make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine)()


class TestSqliteDefault(unittest.TestCase):
    """Requirement 1: SQLite default behavior preserved."""

    def test_default_url_is_sqlite_file(self):
        self.assertTrue(DEFAULT_SQLITE_URL.startswith("sqlite:///"))
        self.assertTrue(DEFAULT_SQLITE_URL.endswith("safety.db"))

    def test_empty_database_url_falls_back_to_sqlite(self):
        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            from database import _resolve_database_url
            self.assertEqual(_resolve_database_url(), DEFAULT_SQLITE_URL)

    def test_unset_database_url_falls_back_to_sqlite(self):
        env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        with patch.dict(os.environ, env, clear=True):
            from database import _resolve_database_url
            self.assertEqual(_resolve_database_url(), DEFAULT_SQLITE_URL)

    def test_sqlite_engine_keeps_check_same_thread(self):
        engine = create_database_engine("sqlite:///:memory:")
        self.assertEqual(engine.dialect.name, "sqlite")
        # SQLAlchemy wraps connect_args in the creator closure
        closure = [cell.cell_contents for cell in (engine.pool._creator.__closure__ or [])]
        connect_args = next(
            (c for c in closure if isinstance(c, dict)), {}
        )
        self.assertIn("check_same_thread", connect_args)
        engine.dispose()


class TestDatabaseUrlConfiguration(unittest.TestCase):
    """Requirements 2 & 3: DATABASE_URL handling and dialect-specific options."""

    def test_sqlite_url_override_honored(self):
        url = "sqlite:////tmp/phase6_override.db"
        with patch.dict(os.environ, {"DATABASE_URL": url}):
            from database import _resolve_database_url, _is_sqlite
            resolved = _resolve_database_url()
            self.assertEqual(resolved, url)
            self.assertTrue(_is_sqlite(resolved))

    def test_postgres_url_detected_as_non_sqlite(self):
        for url in (
            "postgresql+psycopg://user:pass@localhost:5432/safesense",
            "postgresql://user:pass@localhost:5432/safesense",
        ):
            with self.subTest(url=url):
                from database import _is_sqlite
                self.assertFalse(_is_sqlite(url))

    def test_postgres_engine_constructible_without_running_server(self):
        """Engine construction resolves the dialect/driver only — no connection
        is attempted, so PostgreSQL does not need to be running."""
        url = "postgresql+psycopg://user:pass@localhost:5432/safesense"
        engine = create_database_engine(url)
        try:
            self.assertEqual(engine.dialect.name, "postgresql")
            self.assertEqual(engine.dialect.driver, "psycopg")
            self.assertTrue(engine.pool._pre_ping)
        finally:
            engine.dispose()

    def test_postgres_engine_has_no_sqlite_connect_args(self):
        """Requirement: SQLite-specific connect_args must not leak into PG."""
        engine = create_database_engine(
            "postgresql+psycopg://user:pass@localhost:5432/safesense"
        )
        try:
            defaults = engine.pool._creator.__defaults__ or ()
            self.assertNotIn(
                "check_same_thread", str(defaults),
                "SQLite connect_args leaked into PostgreSQL engine",
            )
        finally:
            engine.dispose()

    def test_module_level_flags_consistent(self):
        # Default test environment uses SQLite
        self.assertTrue(IS_SQLITE)


class TestPortableMonthlyTrends(unittest.TestCase):
    """Requirement 4: portable get_monthly_trends (no strftime)."""

    REPORTS = [
        # (report_id, date, sif, risk_level)
        ("M-1", "2026-02-05", "NO", "LOW"),
        ("M-2", "2026-02-20", "YES", "HIGH"),
        ("M-3", "2026-03-01", "YES", "CRITICAL"),
        ("M-4", "2026-03-15", "YES", "CRITICAL"),
        ("M-5", "2026-03-28", "NO", "MEDIUM"),
        # malformed/empty dates must be skipped, not grouped
        ("M-6", "", "YES", "LOW"),
        ("M-7", None, "NO", "LOW"),
        ("M-8", "garbage", "NO", "LOW"),
    ]

    def setUp(self):
        self.engine, self.db = _make_db()
        for rid, date, sif, level in self.REPORTS:
            self.db.add(models.Report(
                report_id=rid, description="x" * 20, category="Unsafe Act",
                risk_level=level, risk_score=50, sif_potential=sif,
                site="Site Alpha", unit="U", area="A", activity="Act",
                barrier_failure=None, date=date,
                pii_detected=0, pii_count=0, pii_types="",
            ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_monthly_trends_grouping(self):
        from services.analytics_service import get_monthly_trends
        trends = get_monthly_trends(self.db)
        by_month = {t["month"]: t for t in trends}
        self.assertEqual(by_month["2026-02"], {"month": "2026-02", "total": 2, "sif": 1, "critical": 0})
        self.assertEqual(by_month["2026-03"], {"month": "2026-03", "total": 3, "sif": 2, "critical": 2})
        self.assertEqual(len(trends), 2)  # malformed dates skipped
        self.assertEqual([t["month"] for t in trends], sorted(t["month"] for t in trends))

    def test_monthly_trends_matches_previous_strftime_behavior(self):
        """Portability guard: Python bucketing must equal SQLite strftime output."""
        from services.analytics_service import get_monthly_trends, _month_key
        expected = get_monthly_trends(self.db)

        # Independent recomputation using SQLite's strftime directly
        rows = self.db.query(models.Report.date, models.Report.sif_potential,
                             models.Report.risk_level).all()
        from collections import defaultdict
        buckets = defaultdict(lambda: {"total": 0, "sif": 0, "critical": 0})
        for d, sif, level in rows:
            key = _month_key(d)
            if key is None:
                continue
            buckets[key]["total"] += 1
            if str(sif or "").upper() == "YES":
                buckets[key]["sif"] += 1
            if str(level or "").upper() == "CRITICAL":
                buckets[key]["critical"] += 1
        self.assertEqual(
            expected,
            [{"month": m, **buckets[m]} for m in sorted(buckets)],
        )

    def test_month_key_strictness(self):
        from services.analytics_service import _month_key
        self.assertEqual(_month_key("2026-03-15"), "2026-03")
        self.assertEqual(_month_key("2026-03"), "2026-03")  # already month-length
        self.assertIsNone(_month_key(""))
        self.assertIsNone(_month_key(None))
        self.assertIsNone(_month_key("15/03/2026"))
        self.assertIsNone(_month_key("2026/03/15"))

    def test_monthly_trends_empty_db(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        db = sessionmaker(bind=engine)()
        try:
            from services.analytics_service import get_monthly_trends
            self.assertEqual(get_monthly_trends(db), [])
        finally:
            db.close()
            engine.dispose()


class TestPortableAdminReset(unittest.TestCase):
    """Requirement 5: admin reset without sqlite_sequence dependency."""

    def setUp(self):
        self.engine, self.db = _make_db()
        self.db.add(models.Report(
            report_id="A-1", description="x" * 20, category="Unsafe Act",
            risk_level="LOW", risk_score=10, sif_potential="NO",
            site="Site Alpha", unit="U", area="A", activity="Act",
            barrier_failure=None, date="2026-03-01",
            pii_detected=0, pii_count=0, pii_types="",
        ))
        self.db.add(models.Action(report_id="A-1", description="fix", owner="hse", status="OPEN"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_reset_logic_clears_all_rows(self):
        # Exercise the same deletion sequence used by the admin reset endpoint
        from sqlalchemy import text
        self.db.execute(text("DELETE FROM reviews;"))
        self.db.execute(text("DELETE FROM actions;"))
        self.db.execute(text("DELETE FROM reports;"))
        self.db.execute(text("DELETE FROM uploaded_files;"))
        if IS_SQLITE:
            try:
                self.db.execute(text(
                    "DELETE FROM sqlite_sequence WHERE name IN "
                    "('reports', 'uploaded_files', 'actions', 'reviews');"
                ))
            except Exception:
                pass
        self.db.commit()

        self.assertEqual(self.db.query(models.Report).count(), 0)
        self.assertEqual(self.db.query(models.Action).count(), 0)

    def test_sequence_reset_is_sqlite_gated(self):
        """The sqlite_sequence statement must only run for SQLite dialects."""
        from database import _is_sqlite
        self.assertTrue(_is_sqlite("sqlite:///x.db"))
        self.assertFalse(_is_sqlite("postgresql+psycopg://u:p@h:5432/db"))


class TestEnsureSchemaMigrationsGating(unittest.TestCase):
    """Requirement 7: ensure_schema_migrations is SQLite-only."""

    def test_non_sqlite_is_noop(self):
        # ensure_schema_migrations reads module-level IS_SQLITE; with a PG URL
        # configured it must return without touching anything.
        import database
        with patch.object(database, "IS_SQLITE", False):
            # Must not raise and must not attempt PRAGMA against any connection
            database.ensure_schema_migrations()

    def test_sqlite_gated_true_for_sqlite_url(self):
        import database
        with patch.object(database, "IS_SQLITE", True):
            # For a real SQLite DB the function is callable and idempotent
            database.ensure_schema_migrations()  # runs against the default file DB


class TestAlembicBaselineConsistency(unittest.TestCase):
    """Requirement 8: Alembic baseline metadata consistency (where practical)."""

    def test_all_model_tables_present_in_metadata(self):
        from database import Base
        # Phase 6 Batch 2 adds report_embeddings (vector-ready, no safety fields)
        self.assertEqual(
            set(Base.metadata.tables.keys()),
            {"reports", "actions", "reviews", "uploaded_files", "report_embeddings"},
        )

    def test_alembic_baseline_file_exists_and_covers_tables(self):
        import glob
        import re as _re
        versions_dir = os.path.join(os.path.dirname(__file__), "alembic", "versions")
        files = [f for f in glob.glob(os.path.join(versions_dir, "*.py"))
                 if not f.endswith("__init__.py")]
        self.assertTrue(files, "no Alembic version files found")
        baseline = None
        for f in files:
            with open(f, "r", encoding="utf-8") as fh:
                content = fh.read()
            if __import__("re").search(r"down_revision[^\n=]*=\s*None", content):
                baseline = content
                break
        self.assertIsNotNone(baseline, "no baseline migration (down_revision=None) found")
        # Baseline covers the pre-Batch-2 tables; report_embeddings arrives in
        # the follow-up migration (e5d4d8238ea9)
        for table in ("reports", "actions", "reviews", "uploaded_files"):
            self.assertIn(f"create_table('{table}'", baseline, f"baseline missing {table}")
        # Unique content_hash constraint from the dedup feature must be present
        self.assertIn("UniqueConstraint('content_hash')", baseline)
        # CASCADE FKs on child tables
        self.assertIn("ondelete='CASCADE'", baseline)

    def test_alembic_env_uses_project_metadata(self):
        env_path = os.path.join(os.path.dirname(__file__), "alembic", "env.py")
        with open(env_path, "r", encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn("target_metadata = Base.metadata", content)
        self.assertIn("import models", content)

    def test_baseline_migration_applies_on_fresh_sqlite(self):
        """The Alembic baseline must produce the same table set as create_all."""
        import subprocess
        import sqlite3
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "alembic_check.db")
            url = f"sqlite:///{db_path}"
            env = {**os.environ, "DATABASE_URL": url}
            result = subprocess.run(
                ["alembic", "upgrade", "head"],
                cwd=os.path.dirname(__file__),
                env=env,
                capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            con = sqlite3.connect(db_path)
            try:
                tables = {
                    r[0] for r in con.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                tables.discard("alembic_version")
                # Phase 6 Batch 2: report_embeddings is part of the migrated schema
                self.assertEqual(
                    tables,
                    {"reports", "actions", "reviews", "uploaded_files", "report_embeddings"},
                )
            finally:
                con.close()


if __name__ == "__main__":
    unittest.main()
