"""
test_vector_store.py — Phase 6 Batch 2 tests for the pgvector-ready embedding
architecture.

Coverage map:
- report_embeddings model metadata (composite PK, dim guard, no safety fields)
- FK relationship + CASCADE behavior (testable on SQLite)
- unique(report_id, model_id) / model_id isolation
- SQLite application works without pgvector (create_all + full app import)
- vector store SQLite fallback / flag-off behavior
- pgvector backend import guards and configuration
- safety boundary: import guard + deterministic analysis unaffected
- embedding flag defaults to off
"""
import json
import os
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from database import Base
import models


def _make_db():
    """SQLite test DB with FK enforcement enabled (SQLite defaults FKs OFF)."""
    from sqlalchemy import event

    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine)()


def _add_report(db, rid="R-1"):
    db.add(models.Report(
        report_id=rid, description="Technician entered tank without gas test.",
        category="Unsafe Act", risk_level="CRITICAL", risk_score=90,
        sif_potential="YES", site="Site Alpha", unit="U", area="A",
        activity="Act", barrier_failure="Gas Testing Not Completed",
        date="2026-03-01", pii_detected=0, pii_count=0, pii_types="",
    ))
    db.commit()


class ReportEmbeddingModelTests(unittest.TestCase):
    """Model metadata, FK, CASCADE, uniqueness, model isolation."""

    def setUp(self):
        self.engine, self.db = _make_db()
        _add_report(self.db, "R-1")

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_model_metadata(self):
        table = models.ReportEmbedding.__table__
        self.assertEqual(table.name, "report_embeddings")
        cols = set(table.columns.keys())
        # Exactly the allowed columns — NO safety fields may ever appear here
        self.assertEqual(
            cols, {"report_id", "model_id", "embedding", "dim", "created_at"},
            f"report_embeddings must contain only vector-reference columns, got: {cols}",
        )

    def test_no_safety_fields_in_vector_table(self):
        """Safety boundary: vector rows must never duplicate safety attributes."""
        forbidden = {
            "risk_level", "risk_score", "sif_potential", "category",
            "barrier_failure", "temporal_state", "exposure_state",
            "life_saving_rule", "severity", "lsr",
        }
        cols = set(models.ReportEmbedding.__table__.columns.keys())
        self.assertEqual(forbidden & cols, set())

    def test_composite_pk_enforces_unique_report_model(self):
        emb = models.ReportEmbedding(
            report_id="R-1", model_id="m1", embedding="[0.1,0.2]", dim=2
        )
        self.db.add(emb)
        self.db.commit()
        dup = models.ReportEmbedding(
            report_id="R-1", model_id="m1", embedding="[0.3,0.4]", dim=2
        )
        self.db.add(dup)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    def test_same_report_multiple_models_allowed(self):
        """model_id versioning: several models may coexist for one report."""
        self.db.add(models.ReportEmbedding(report_id="R-1", model_id="model-a", embedding="[0.1]", dim=1))
        self.db.add(models.ReportEmbedding(report_id="R-1", model_id="model-b", embedding="[0.2]", dim=1))
        self.db.commit()
        rows = self.db.query(models.ReportEmbedding).filter_by(report_id="R-1").all()
        self.assertEqual({r.model_id for r in rows}, {"model-a", "model-b"})

    def test_model_id_isolation(self):
        self.db.add(models.ReportEmbedding(report_id="R-1", model_id="model-a", embedding="[1]", dim=1))
        self.db.add(models.ReportEmbedding(report_id="R-1", model_id="model-b", embedding="[2]", dim=1))
        self.db.commit()
        a = self.db.query(models.ReportEmbedding).filter_by(model_id="model-a").all()
        self.assertEqual(len(a), 1)
        self.assertEqual(json.loads(a[0].embedding), [1.0])

    def test_fk_relationship_to_report(self):
        emb = models.ReportEmbedding(report_id="R-1", model_id="m1", dim=2)
        self.db.add(emb)
        self.db.commit()
        row = self.db.query(models.ReportEmbedding).first()
        self.assertEqual(row.report.report_id, "R-1")  # relationship works
        # FK enforcement on invalid reference
        self.db.add(models.ReportEmbedding(report_id="MISSING", model_id="m2", dim=2))
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    def test_cascade_delete_with_report(self):
        self.db.add(models.ReportEmbedding(report_id="R-1", model_id="m1", dim=2))
        self.db.commit()
        report = self.db.query(models.Report).filter_by(report_id="R-1").first()
        self.db.delete(report)
        self.db.commit()
        remaining = self.db.query(models.ReportEmbedding).all()
        self.assertEqual(remaining, [], "embedding rows must CASCADE-delete with their report")

    def test_dim_guard_metadata(self):
        emb = models.ReportEmbedding(report_id="R-1", model_id="m1", dim=768)
        self.db.add(emb)
        self.db.commit()
        self.assertEqual(self.db.query(models.ReportEmbedding).first().dim, 768)
        self.assertEqual(models.EMBEDDING_DIMENSION, 768)


class SQLiteWithoutPgvectorTests(unittest.TestCase):
    """SQLite mode must work with pgvector absent from the runtime path."""

    def test_metadata_loadable_and_create_all_sqlite(self):
        engine, db = _make_db()
        try:
            self.assertIn("report_embeddings", Base.metadata.tables)
            # A plain query works — table exists, no pgvector involvement
            self.assertEqual(db.query(models.ReportEmbedding).count(), 0)
        finally:
            db.close()
            engine.dispose()

    def test_app_imports_without_pgvector_usage(self):
        # Full application import (all routers/services) on SQLite
        import logging
        logging.disable(logging.CRITICAL)
        from main import app  # noqa: F401
        from database import IS_SQLITE
        self.assertTrue(IS_SQLITE)

    def test_embedding_column_is_portable_text_on_sqlite(self):
        col = models.ReportEmbedding.__table__.columns["embedding"]
        self.assertEqual(type(col.type).__name__, "Text")


class VectorStoreBehaviorTests(unittest.TestCase):
    """Flag-off defaults, SQLite fallback, upsert/search semantics."""

    def setUp(self):
        from services import vector_store as VS
        self.VS = VS
        os.environ.pop("SAFESENSE_EMBEDDINGS", None)
        self.engine, self.db = _make_db()
        _add_report(self.db, "R-1")
        _add_report(self.db, "R-2")

    def tearDown(self):
        os.environ.pop("SAFESENSE_EMBEDDINGS", None)
        self.db.close()
        self.engine.dispose()

    def test_flag_defaults_off(self):
        self.assertFalse(self.VS.embeddings_enabled())

    def test_flag_on(self):
        with patch.dict(os.environ, {"SAFESENSE_EMBEDDINGS": "on"}):
            self.assertTrue(self.VS.embeddings_enabled())

    def test_upsert_disabled_when_flag_off(self):
        res = self.VS.upsert_embeddings(
            [self.VS.EmbeddingInput("R-1", "m", [0.1, 0.2])]
        )
        self.assertEqual(res["status"], "disabled")
        self.assertEqual(res["inserted"], 0)

    def test_search_disabled_when_flag_off(self):
        res = self.VS.search_similar([0.1, 0.2], "m")
        self.assertEqual(res["status"], "disabled")
        self.assertEqual(res["candidates"], [])

    def test_upsert_persists_rows_when_enabled(self):
        with patch.dict(os.environ, {"SAFESENSE_EMBEDDINGS": "on"}):
            res = self.VS.upsert_embeddings([
                self.VS.EmbeddingInput("R-1", "m1", [0.1, 0.2, 0.3]),
                self.VS.EmbeddingInput("R-2", "m1", [0.9, 0.8, 0.7]),
            ], session=self.db)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["inserted"], 2)
            rows = self.db.query(models.ReportEmbedding).all()
            self.assertEqual(len(rows), 2)
            self.assertEqual(json.loads(rows[0].embedding)[0], 0.1)

    def test_upsert_is_idempotent_per_model(self):
        with patch.dict(os.environ, {"SAFESENSE_EMBEDDINGS": "on"}):
            self.VS.upsert_embeddings([self.VS.EmbeddingInput("R-1", "m1", [0.1, 0.2])], session=self.db)
            res = self.VS.upsert_embeddings([self.VS.EmbeddingInput("R-1", "m1", [0.3, 0.4])], session=self.db)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(self.db.query(models.ReportEmbedding).count(), 1)
            row = self.db.query(models.ReportEmbedding).first()
            self.assertEqual(json.loads(row.embedding), [0.3, 0.4])

    def test_upsert_validation_rejects_bad_input(self):
        with patch.dict(os.environ, {"SAFESENSE_EMBEDDINGS": "on"}):
            res = self.VS.upsert_embeddings([
                self.VS.EmbeddingInput("", "m", [0.1]),
                self.VS.EmbeddingInput("R-1", "m", []),
                self.VS.EmbeddingInput("R-1", "m", [0.1], dim=5),  # dim mismatch
            ])
            # All items invalid -> nothing inserted; each reported with reason
            self.assertEqual(res["inserted"], 0)
            self.assertEqual(len(res["errors"]), 3)
            self.assertIn(res["status"], ("error", "partial"))

    def test_search_unavailable_on_sqlite(self):
        """SQLite fallback: explicit unavailability, app unaffected."""
        with patch.dict(os.environ, {"SAFESENSE_EMBEDDINGS": "on"}):
            res = self.VS.search_similar([0.1, 0.2], "m1")
            self.assertEqual(res["status"], "unavailable")
            self.assertEqual(res["backend"], "sqlite")
            self.assertEqual(res["candidates"], [])
            self.assertIn("deterministic", res["note"])

    def test_search_rejects_empty_query(self):
        with patch.dict(os.environ, {"SAFESENSE_EMBEDDINGS": "on"}):
            res = self.VS.search_similar([], "m1")
            self.assertEqual(res["status"], "error")

    def test_candidates_carry_no_safety_fields(self):
        """SimilarCandidate must expose only reference + advisory score."""
        fields = set(self.VS.SimilarCandidate("r", "m", 0.9, 0.1).to_dict().keys())
        self.assertEqual(fields, {"report_id", "model_id", "score", "distance"})

    def test_ingest_hook_none_when_disabled(self):
        self.assertIsNone(self.VS.queue_embedding_on_ingest("R-1", "text"))

    def test_ingest_hook_reports_no_provider_when_enabled(self):
        with patch.dict(os.environ, {"SAFESENSE_EMBEDDINGS": "on"}):
            res = self.VS.queue_embedding_on_ingest("R-1", "text")
            self.assertIsNotNone(res)
            self.assertEqual(res["status"], "no_provider")

    def test_backend_info_explains_state(self):
        info = self.VS.get_backend_info()
        self.assertEqual(info["backend"], "sqlite")
        self.assertFalse(info["embeddings_enabled"])
        self.assertIn("never", info["note"])


class PgvectorImportGuardTests(unittest.TestCase):
    """pgvector usage must be guarded; SQLite path never requires it."""

    def test_pgvector_importable_flag(self):
        # pgvector IS installed in this environment (added this batch);
        # a fresh subprocess verifies the natural import state.
        import subprocess, sys as _sys
        result = subprocess.run(
            [_sys.executable, "-c", "import models; print(models._PGVECTOR_AVAILABLE)"],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "True")

    def test_sqlite_uses_text_even_with_pgvector_installed(self):
        """Dialect gate: SQLite stays portable even when pgvector is present."""
        col = models.ReportEmbedding.__table__.columns["embedding"]
        self.assertEqual(type(col.type).__name__, "Text")

    def test_models_import_does_not_require_pgvector(self):
        """Simulate missing pgvector in a clean subprocess: models must still
        import and the embedding column must fall back to Text on SQLite."""
        import subprocess, sys as _sys
        code = (
            "import sys;"
            "sys.modules['pgvector'] = None; sys.modules['pgvector.sqlalchemy'] = None;"
            "import models;"
            "assert models._PGVECTOR_AVAILABLE is False;"
            "assert type(models.ReportEmbedding.__table__.columns['embedding'].type).__name__ == 'Text';"
            "print('OK')"
        )
        result = subprocess.run(
            [_sys.executable, "-c", code],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK", result.stdout)

    def test_vector_store_pg_search_requires_postgres_dialect(self):
        """The native pgvector SQL path must be unreachable from SQLite mode."""
        from services import vector_store as VS
        info = VS.get_backend_info()
        if info["backend"] == "sqlite":
            with patch.dict(os.environ, {"SAFESENSE_EMBEDDINGS": "on"}):
                res = VS.search_similar([0.1], "m")
                self.assertEqual(res["status"], "unavailable")


class SafetyBoundaryTests(unittest.TestCase):
    """Vector similarity must never touch deterministic safety decisions."""

    PROTECTED = [
        "risk_engine",
        "rule_classifier",
        "barrier_dictionary",
        "concept_extractor",
        "pattern_engine",
    ]

    def test_protected_modules_do_not_import_vector_store(self):
        import sys
        for name in self.PROTECTED:
            module = sys.modules.get(f"services.{name}")
            if module is None:
                module = __import__(f"services.{name}", fromlist=["x"])
            source_deps = {
                dep.split(".")[0]
                for dep in getattr(module, "__dict__", {})
                if "vector" in str(dep).lower()
            }
            self.assertEqual(
                source_deps, set(),
                f"services/{name}.py must not reference vector_store",
            )
            # Stronger: scan loaded module source if available
            import inspect
            try:
                src = inspect.getsource(module)
                self.assertNotIn(
                    "vector_store", src,
                    f"services/{name}.py must not import vector_store",
                )
            except (OSError, TypeError):
                pass  # source unavailable (e.g. frozen); dict check above still holds

    def test_vector_analysis_loop_leaves_safety_outputs_identical(self):
        """Full safety pipeline before/after vector operations must match."""
        from services.risk_engine import analyze_report
        from services.rule_classifier import classify_life_saving_rule
        from services.barrier_dictionary import detect_barriers

        text = "Technician entered reactor vessel without permit and oxygen levels were not tested."
        before = (
            analyze_report({"report_text": text})["risk_score"],
            analyze_report({"report_text": text})["sif_potential"],
            classify_life_saving_rule(text)["primary_rule"],
            detect_barriers(text),
        )

        from services import vector_store as VS
        with patch.dict(os.environ, {"SAFESENSE_EMBEDDINGS": "on"}):
            VS.upsert_embeddings([VS.EmbeddingInput("SR-1", "m", [0.1] * 8)])
            VS.search_similar([0.1] * 8, "m")
            VS.queue_embedding_on_ingest("SR-1", text)

        after = (
            analyze_report({"report_text": text})["risk_score"],
            analyze_report({"report_text": text})["sif_potential"],
            classify_life_saving_rule(text)["primary_rule"],
            detect_barriers(text),
        )
        self.assertEqual(before, after)

    def test_ingest_hook_does_not_alter_report_row(self):
        """Hook invocation must not modify the persisted report."""
        engine, db = _make_db()
        try:
            _add_report(db, "HR-1")
            before = (
                db.query(models.Report).filter_by(report_id="HR-1").first().risk_score,
                db.query(models.Report).filter_by(report_id="HR-1").first().sif_potential,
            )
            from services import vector_store as VS
            with patch.dict(os.environ, {"SAFESENSE_EMBEDDINGS": "on"}):
                VS.queue_embedding_on_ingest("HR-1", "anything")
            row = db.query(models.Report).filter_by(report_id="HR-1").first()
            self.assertEqual((row.risk_score, row.sif_potential), before)
        finally:
            db.close()
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
