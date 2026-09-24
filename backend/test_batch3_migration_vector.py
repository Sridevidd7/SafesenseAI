"""
test_batch3_migration_vector.py — Phase 6 Batch 3 tests.

Coverage:
- Embedding provider: disabled default, unavailable provider (never fake vectors),
  custom provider resolution, hook behavior in all flag states.
- Vector store native PG path configuration (skip-guarded on TEST_DATABASE_URL):
  native writes, model_id filtering, dimension handling, candidate-set filter,
  similarity ordering, upsert idempotency.
- SQLite -> PostgreSQL migration logic (tested against a second SQLite target
  standing in for PostgreSQL — the migration code is ORM-generic and reads
  DATABASE_URL; the PG-specific URL check is unit-tested separately):
  dry-run, idempotency, parent/child ordering, ID/hash preservation,
  integrity verification, source-unchanged guarantee.
- Docker compose: file parses, postgres service profile-gated, no hardcoded
  production credentials, default stack unchanged.
- Safety: protected modules untouched by vector infra; deterministic outputs
  invariant.
"""
import json
import os
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"


class EmbeddingProviderTests(unittest.TestCase):

    def setUp(self):
        for k in ("SAFESENSE_EMBEDDINGS", "SAFESENSE_EMBEDDING_PROVIDER",
                  "SAFESENSE_EMBEDDING_PROVIDER_MODULE"):
            os.environ.pop(k, None)

    def tearDown(self):
        for k in ("SAFESENSE_EMBEDDINGS", "SAFESENSE_EMBEDDING_PROVIDER",
                  "SAFESENSE_EMBEDDING_PROVIDER_MODULE"):
            os.environ.pop(k, None)

    def test_default_provider_unavailable(self):
        from services.embedding_provider import get_provider, UnavailableEmbeddingProvider
        self.assertIsInstance(get_provider(), UnavailableEmbeddingProvider)

    def test_unavailable_provider_never_generates_vectors(self):
        from services.embedding_provider import get_provider
        p = get_provider()
        self.assertIsNone(p.embed("any text"))
        self.assertEqual(p.embed_batch(["a", "b"]), [None, None])

    def test_provider_info_reports_unavailable(self):
        from services.embedding_provider import get_provider_info
        info = get_provider_info()
        self.assertFalse(info["available"])
        self.assertEqual(info["model_id"], "unavailable")

    def test_custom_provider_resolution(self):
        os.environ["SAFESENSE_EMBEDDING_PROVIDER"] = "custom"
        os.environ["SAFESENSE_EMBEDDING_PROVIDER_MODULE"] = "services.embedding_provider"
        # The module exposes no get_provider symbol usable as a *provider module*
        # (it would import itself) — but the failure path must degrade safely:
        from services.embedding_provider import get_provider, UnavailableEmbeddingProvider
        self.assertIsInstance(get_provider(), UnavailableEmbeddingProvider)

    def test_hook_disabled_by_default(self):
        from services.vector_store import queue_embedding_on_ingest
        self.assertIsNone(queue_embedding_on_ingest("R-1", "text"))

    def test_hook_graceful_without_provider(self):
        os.environ["SAFESENSE_EMBEDDINGS"] = "on"
        from services.vector_store import queue_embedding_on_ingest
        res = queue_embedding_on_ingest("R-1", "text")
        self.assertEqual(res["status"], "no_provider")

    def test_hook_persists_with_fake_provider_but_never_fakes_itself(self):
        """With an explicitly configured working provider, the hook persists a
        vector; with none, it never invents one."""
        os.environ["SAFESENSE_EMBEDDINGS"] = "on"
        os.environ["SAFESENSE_EMBEDDING_PROVIDER"] = "custom"
        os.environ["SAFESENSE_EMBEDDING_PROVIDER_MODULE"] = "test_batch3_migration_vector"
        # This test module exposes get_provider() returning a deterministic
        # test-only provider — exercising the full persistence path.
        res = None
        from services import vector_store as VS
        engine = None
        try:
            from sqlalchemy import create_engine, event
            from sqlalchemy.orm import sessionmaker
            from database import Base
            import models
            engine = create_engine("sqlite:///:memory:")

            @event.listens_for(engine, "connect")
            def _fk(dbapi_conn, _):
                dbapi_conn.execute("PRAGMA foreign_keys=ON")

            Base.metadata.create_all(bind=engine)
            db = sessionmaker(bind=engine)()
            db.add(models.Report(
                report_id="HP-1", description="x" * 20, category="Unsafe Act",
                risk_level="LOW", risk_score=10, sif_potential="NO",
                site="S", unit="U", area="A", activity="Act",
                barrier_failure=None, date="2026-03-01",
                pii_detected=0, pii_count=0, pii_types="",
            ))
            db.commit()
            # The hook creates its own session via database.SessionLocal;
            # point that factory at the test DB for the duration of the call.
            with patch("database.SessionLocal", sessionmaker(bind=engine)):
                res = VS.queue_embedding_on_ingest("HP-1", "gas test missing on tank entry")
            self.assertEqual(res["status"], "ok")
            self.assertEqual(db.query(models.ReportEmbedding).count(), 1)
            row = db.query(models.ReportEmbedding).first()
            self.assertEqual(row.model_id, "batch3-test-provider")
            # Safety fields on the report untouched
            rpt = db.query(models.Report).filter_by(report_id="HP-1").first()
            self.assertEqual((rpt.risk_score, rpt.sif_potential), (10, "NO"))
            db.close()
        finally:
            if engine is not None:
                engine.dispose()


# Deterministic test-only provider (used via env module path above)
def get_provider():
    from services.embedding_provider import EmbeddingProvider

    class _Batch3TestProvider(EmbeddingProvider):
        model_id = "batch3-test-provider"
        dim = 4

        def embed(self, text):
            # Deterministic, NOT random: simple 4-dim bag-of-chars for tests only
            v = [float(min(text.count(c), 9)) for c in ("gas", "tank", "test", "lock")]
            return v

        def embed_batch(self, texts):
            return [self.embed(t) for t in texts]

    return _Batch3TestProvider()


class MigrationScriptRealRunTests(unittest.TestCase):
    """End-to-end migration script runs in subprocesses. The migration body is
    ORM-generic; the PG-URL gate is exercised by monkeypatching database flags
    inside the subprocess (real-PG runs are skip-guarded separately)."""

    def _make_subprocess_code(self, extra: str) -> str:
        """Build a subprocess program with safely-quoted absolute paths.
        Source/target paths are passed as raw strings and URLs are constructed
        inside the subprocess to avoid Windows backslash escape issues."""
        backend_abs = str(BACKEND)
        scripts_abs = str(ROOT / "scripts")
        tgt = str(self.tgt_path)
        src = str(self.src_path)
        return (
            "import sys, os\n"
            f"sys.path.insert(0, r'{backend_abs}')\n"
            f"sys.path.insert(0, r'{scripts_abs}')\n"
            "import database\n"
            f"_tgt_path = r'{tgt}'\n"
            f"_src_path = r'{src}'\n"
            "database.DATABASE_URL = 'sqlite:///' + _tgt_path.replace('\\\\', '/')\n"
            "database.IS_SQLITE = False\n"  # simulate the PG gate for the ORM-generic body
            + extra
        )

    def _run_code(self, code: str, timeout: int = 300):
        return subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=timeout, cwd=str(BACKEND),
        )

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.src_path = os.path.join(self.tmp.name, "source.db")
        self.tgt_path = os.path.join(self.tmp.name, "target.db")

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from database import Base
        import models

        src_engine = create_engine(f"sqlite:///{self.src_path}",
                                   connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=src_engine)
        s = sessionmaker(bind=src_engine)()
        s.add(models.Report(
            report_id="MIG-1", content_hash="hash-MIG-1",
            description="Technician entered tank without gas test.",
            category="Unsafe Act", risk_level="CRITICAL", risk_score=90,
            sif_potential="YES", site="Site Alpha", unit="U", area="A",
            activity="Act", barrier_failure="Gas Testing Not Completed",
            pii_detected=0, pii_count=0, pii_types="", date="2026-03-01",
        ))
        s.add(models.Action(report_id="MIG-1", description="fix", owner="hse", status="OPEN"))
        s.commit()
        s.close()
        src_engine.dispose()

        # Pre-create target schema
        tgt_engine = create_engine(f"sqlite:///{self.tgt_path}")
        Base.metadata.create_all(bind=tgt_engine)
        tgt_engine.dispose()

    def tearDown(self):
        # Windows: subprocesses may briefly hold the DB files; retry cleanup
        import time
        for attempt in range(5):
            try:
                self.tmp.cleanup()
                break
            except PermissionError:
                time.sleep(0.4)

    def _script_source_snapshot(self):
        return Path(self.src_path).read_bytes()

    def test_source_database_unchanged_by_migration(self):
        """CRITICAL: the SQLite source must never be mutated."""
        before = self._script_source_snapshot()
        code = self._make_subprocess_code(
            "import migrate_sqlite_to_postgres as M\n"
            "rc = M.migrate(dry_run=False, source_path=_src_path)\n"
            "print('RC:', rc)\n"
        )
        result = self._run_code(code)
        self.assertIn("RC: 0", result.stdout, result.stderr)
        self.assertEqual(before, self._script_source_snapshot(),
                         "source SQLite file must be byte-identical after migration")

    def test_idempotency_and_preservation(self):
        code = self._make_subprocess_code(
            "import migrate_sqlite_to_postgres as M\n"
            "rc1 = M.migrate(dry_run=False, source_path=_src_path)\n"
            "rc2 = M.migrate(dry_run=False, source_path=_src_path)\n"  # idempotency
            "print('RC:', rc1, rc2)\n"
            "import sqlite3\n"
            f"con = sqlite3.connect(r'{self.tgt_path}'.replace('\\\\', '/'))\n"
            "r = con.execute('SELECT report_id, content_hash, risk_score, sif_potential FROM reports').fetchall()\n"
            "print('ROW:', r)\n"
            "a = con.execute('SELECT report_id FROM actions').fetchall()\n"
            "print('ACTION:', a)\n"
        )
        result = self._run_code(code)
        self.assertIn("RC: 0 0", result.stdout, result.stderr)
        self.assertIn("MIG-1", result.stdout)
        self.assertIn("hash-MIG-1", result.stdout)  # hash preserved, not regenerated
        self.assertIn("('MIG-1',)", result.stdout)  # child FK preserved
        # Safety semantics migrated exactly (inside the full row tuple)
        self.assertIn("90, 'YES')", result.stdout)
        # Idempotency: second run skipped everything (no duplicates)
        con = sqlite3.connect(self.tgt_path)
        count = con.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        con.close()
        self.assertEqual(count, 1)

    def test_dry_run_writes_nothing(self):
        code = self._make_subprocess_code(
            "import migrate_sqlite_to_postgres as M\n"
            "rc = M.migrate(dry_run=True, source_path=_src_path)\n"
            "print('RC:', rc)\n"
        )
        result = self._run_code(code)
        self.assertIn("RC: 0", result.stdout, result.stderr)
        self.assertIn("reports: would_migrate=1 already_present=0", result.stdout)
        con = sqlite3.connect(self.tgt_path)
        count = con.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        con.close()
        self.assertEqual(count, 0, "dry run must not write any rows")

    def test_missing_pg_url_exits_nonzero(self):
        backend_abs = str(BACKEND)
        scripts_abs = str(ROOT / "scripts")
        code = (
            "import sys, os\n"
            f"sys.path.insert(0, r'{backend_abs}')\n"
            f"sys.path.insert(0, r'{scripts_abs}')\n"
            "os.environ['DATABASE_URL'] = ''\n"
            "import migrate_sqlite_to_postgres as M\n"
            "M.migrate(dry_run=True)\n"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True,
                                text=True, timeout=60, cwd=str(BACKEND))
        self.assertEqual(result.returncode, 2)  # refuses to run without PG URL


class DockerComposeTests(unittest.TestCase):

    COMPOSE = ROOT / "docker-compose.yml"

    def test_compose_parses(self):
        result = subprocess.run(
            ["docker", "compose", "-f", str(self.COMPOSE), "config", "--quiet"],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_postgres_is_profile_gated(self):
        result = subprocess.run(
            ["docker", "compose", "-f", str(self.COMPOSE), "config", "--services"],
            capture_output=True, text=True, timeout=60,
        )
        services = set(result.stdout.split())
        self.assertIn("backend", services)
        self.assertIn("frontend", services)
        self.assertNotIn("postgres", services)  # profile-gated = not in default set

    def test_postgres_profile_listed(self):
        result = subprocess.run(
            ["docker", "compose", "-f", str(self.COMPOSE), "config", "--profiles"],
            capture_output=True, text=True, timeout=60,
        )
        self.assertIn("postgres", result.stdout)

    def test_pgvector_image_and_pg16(self):
        content = self.COMPOSE.read_text(encoding="utf-8")
        self.assertIn("pgvector/pgvector:pg16", content)

    def test_no_hardcoded_production_credentials(self):
        """Credentials must come from env with only developer defaults."""
        content = self.COMPOSE.read_text(encoding="utf-8")
        self.assertIn("${POSTGRES_USER:-", content)
        self.assertIn("${POSTGRES_PASSWORD:-", content)
        # No literal production-style secret values (word-boundary match,
        # so documentation words like "production" in comments don't match)
        import re
        for bad in (r"\bprod_password\b", r"\bproduction_password\b", r"\bsupersecret\b"):
            self.assertIsNone(
                re.search(bad, content, re.IGNORECASE),
                f"compose contains hardcoded credential-like value: {bad}",
            )

    def test_default_stack_unchanged(self):
        content = self.COMPOSE.read_text(encoding="utf-8")
        self.assertIn("VITE_API_URL=http://localhost:8000", content)
        self.assertIn('"3000:3000"', content)
        self.assertIn('"8000:8000"', content)


class SearchSqlConstructionTests(unittest.TestCase):
    """Structural proof of the LIMIT-before-filter fix (no PG server needed):
    candidate filtering must live in the WHERE clause, BEFORE ORDER BY/LIMIT."""

    def test_candidate_filter_in_where_clause_before_order_and_limit(self):
        from services.vector_store import _build_search_sql
        sql, params = _build_search_sql(
            [1.0, 0.0, 0.0], "m", top_k=5, candidate_report_ids=["B", "A"]
        )
        text = str(sql)
        where_pos = text.upper().find("WHERE")
        in_pos = text.upper().find("REPORT_ID IN")
        order_pos = text.upper().find("ORDER BY")
        limit_pos = text.upper().find("LIMIT")
        self.assertGreater(in_pos, where_pos, "IN clause must be inside WHERE")
        self.assertLess(in_pos, order_pos, "filtering must precede ORDER BY")
        self.assertLess(order_pos, limit_pos, "LIMIT must apply after filtering")
        # Parameterized identifiers (no value concatenation into SQL)
        self.assertIn(":cid0", text)
        self.assertIn(":cid1", text)
        self.assertNotIn("'B'", text)
        self.assertNotIn("'A'", text)
        self.assertEqual(params["cid0"], "B")
        self.assertEqual(params["cid1"], "A")
        self.assertEqual(params["limit"], 5)

    def test_no_candidate_filter_omits_in_clause(self):
        from services.vector_store import _build_search_sql
        sql, params = _build_search_sql([1.0], "m", top_k=3, candidate_report_ids=None)
        text = str(sql)
        self.assertNotIn("IN (", text.upper())
        self.assertNotIn(":cid0", text)
        self.assertEqual(params["limit"], 3)

    def test_similarity_ordering_uses_cosine_distance_ascending(self):
        from services.vector_store import _build_search_sql
        text = str(_build_search_sql([1.0], "m", top_k=3)[0])
        # distance operator present, ORDER BY ascending (no DESC)
        self.assertIn("<=>", text)
        order_fragment = text.upper().split("ORDER BY")[1]
        self.assertNotIn("DESC", order_fragment)


class SafetyBoundaryTests(unittest.TestCase):

    def test_protected_modules_have_no_vector_imports(self):
        import inspect
        import services.risk_engine, services.rule_classifier
        import services.barrier_dictionary, services.concept_extractor
        import services.pattern_engine
        for mod in (services.risk_engine, services.rule_classifier,
                    services.barrier_dictionary, services.concept_extractor,
                    services.pattern_engine):
            src = inspect.getsource(mod)
            self.assertNotIn("vector_store", src, mod.__name__)
            self.assertNotIn("embedding_provider", src, mod.__name__)

    def test_deterministic_outputs_invariant(self):
        from services.risk_engine import analyze_report
        from services.rule_classifier import classify_life_saving_rule
        from services.barrier_dictionary import detect_barriers
        text = "Worker entered vessel without checking oxygen levels."
        before = (
            analyze_report({"report_text": text})["risk_score"],
            analyze_report({"report_text": text})["sif_potential"],
            classify_life_saving_rule(text)["primary_rule"],
            detect_barriers(text),
        )
        from services import vector_store as VS
        with patch.dict(os.environ, {"SAFESENSE_EMBEDDINGS": "on"}):
            VS.queue_embedding_on_ingest("SX-1", text)
            VS.search_similar([0.1] * 4, "m")
        after = (
            analyze_report({"report_text": text})["risk_score"],
            analyze_report({"report_text": text})["sif_potential"],
            classify_life_saving_rule(text)["primary_rule"],
            detect_barriers(text),
        )
        self.assertEqual(before, after)


class PostgreSQLIntegrationTests(unittest.TestCase):
    """Real PostgreSQL tests — SKIPPED unless TEST_DATABASE_URL is set and
    reachable. The full suite must never depend on a running PostgreSQL."""

    TEST_URL = os.getenv("TEST_DATABASE_URL", "")

    def setUp(self):
        if not self.TEST_URL:
            self.skipTest("TEST_DATABASE_URL not set — PostgreSQL integration tests skipped")
        from sqlalchemy import create_engine, text
        try:
            engine = create_engine(self.TEST_URL)
            with engine.connect():
                pass
        except Exception as exc:
            self.skipTest(f"PostgreSQL not reachable at TEST_DATABASE_URL: {exc}")
        self.engine = engine
        # Build a SQLite source fixture for the migration test
        import tempfile
        from sqlalchemy.orm import sessionmaker
        from database import Base
        import models
        self.tmp = tempfile.TemporaryDirectory()
        self.src_path = os.path.join(self.tmp.name, "source.db")
        src_engine = create_engine(f"sqlite:///{self.src_path}",
                                   connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=src_engine)
        s = sessionmaker(bind=src_engine)()
        s.add(models.Report(
            report_id="MIG-1", content_hash="hash-MIG-1",
            description="Technician entered tank without gas test.",
            category="Unsafe Act", risk_level="CRITICAL", risk_score=90,
            sif_potential="YES", site="Site Alpha", unit="U", area="A",
            activity="Act", barrier_failure="Gas Testing Not Completed",
            pii_detected=0, pii_count=0, pii_types="", date="2026-03-01",
        ))
        s.add(models.Action(report_id="MIG-1", description="fix", owner="hse", status="OPEN"))
        s.commit()
        s.close()
        src_engine.dispose()

    def tearDown(self):
        import time
        for _ in range(5):
            try:
                self.tmp.cleanup()
                break
            except PermissionError:
                time.sleep(0.4)

    def _fresh_schema(self):
        from database import Base
        import models  # noqa: F401
        # pgvector extension needed for the vector column
        from sqlalchemy import text
        with self.engine.begin() as conn:
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            except Exception:
                pass
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

    def test_native_upsert_and_similarity_search(self):
        from sqlalchemy.orm import sessionmaker
        from database import Base
        import models
        from services import vector_store as VS

        self._fresh_schema()
        db = sessionmaker(bind=self.engine)()
        try:
            for i, desc in enumerate([
                "worker entered tank without gas test",
                "forklift reversed without a spotter",
                "no lockout applied during pump maintenance",
            ]):
                db.add(models.Report(
                    report_id=f"PG-{i}", description=desc, category="Unsafe Act",
                    risk_level="HIGH", risk_score=70, sif_potential="NO",
                    site="S", unit="U", area="A", activity="Act",
                    barrier_failure=None, date="2026-03-01",
                    pii_detected=0, pii_count=0, pii_types="",
                ))
            db.commit()

            with patch.dict(os.environ, {"SAFESENSE_EMBEDDINGS": "on"}):
                # Vectors chosen so PG-0 and PG-2 point the same direction,
                # PG-1 is orthogonal-ish
                res = VS.upsert_embeddings([
                    VS.EmbeddingInput("PG-0", "m", [1.0, 0.0, 0.0]),
                    VS.EmbeddingInput("PG-1", "m", [0.0, 1.0, 0.0]),
                    VS.EmbeddingInput("PG-2", "m", [1.0, 0.0, 0.0]),
                ], session=db)
                self.assertEqual(res["status"], "ok")

                # Native vector write check: pgvector column (not JSON text)
                row = db.query(models.ReportEmbedding).filter_by(report_id="PG-0").first()
                self.assertIsNotNone(row)
                self.assertNotIn("[", str(row.embedding)[:1])  # native vector repr

                # Search uses the SAME injected TEST_DATABASE_URL session
                search = VS.search_similar([1.0, 0.0, 0.0], "m", top_k=3, session=db)
                self.assertEqual(search["status"], "ok")
                ids = [c["report_id"] for c in search["candidates"]]
                self.assertEqual(len(ids), 3)
                self.assertEqual(ids[0], "PG-0")  # exact direction match ranks first
                # Advisory-only fields
                self.assertEqual(
                    set(search["candidates"][0].keys()),
                    {"report_id", "model_id", "score", "distance"},
                )

                # model_id isolation: other model has no rows
                empty = VS.search_similar([1.0, 0.0, 0.0], "other-model", session=db)
                self.assertEqual(empty["candidates"], [])

                # candidate-set filtering (in-SQL, pre-LIMIT)
                filtered = VS.search_similar(
                    [1.0, 0.0, 0.0], "m", top_k=3, candidate_report_ids=["PG-1"], session=db
                )
                self.assertEqual([c["report_id"] for c in filtered["candidates"]], ["PG-1"])

                # candidate-set filtering before LIMIT: top-1 WITHIN a candidate
                # set whose members are NOT the global top-1
                narrow = VS.search_similar(
                    [1.0, 0.0, 0.0], "m", top_k=1,
                    candidate_report_ids=["PG-1", "PG-2"], session=db,
                )
                # Global top-1 would be PG-0; restricting to {PG-1, PG-2} must
                # still return 1 result (the better of the two), proving LIMIT
                # applied after candidate filtering.
                self.assertEqual(len(narrow["candidates"]), 1)
                self.assertEqual(narrow["candidates"][0]["report_id"], "PG-2")

                # empty candidate set -> no matches (explicit semantics)
                none = VS.search_similar(
                    [1.0, 0.0, 0.0], "m", top_k=3, candidate_report_ids=[], session=db
                )
                self.assertEqual(none["candidates"], [])

                # upsert idempotency
                VS.upsert_embeddings([VS.EmbeddingInput("PG-0", "m", [0.5, 0.5, 0.0])], session=db)
                self.assertEqual(db.query(models.ReportEmbedding).count(), 3)
        finally:
            db.close()
            self.engine.dispose()

    def test_migration_to_real_postgres(self):
        """Full script run against real PostgreSQL, if available."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from database import Base
        import models

        # Prepare target schema
        tgt_engine = create_engine(self.TEST_URL)
        with tgt_engine.begin() as conn:
            from sqlalchemy import text
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            except Exception:
                pass
        Base.metadata.drop_all(bind=tgt_engine)
        Base.metadata.create_all(bind=tgt_engine)

        code = (
            "import sys, os;"
            f"sys.path.insert(0, {str(BACKEND)!r});"
            f"sys.path.insert(0, {str(ROOT / 'scripts')!r});"
            f"os.environ['DATABASE_URL'] = {self.TEST_URL!r};"
            "import database;"
            "database.IS_SQLITE = False;"
            f"database.DATABASE_URL = {self.TEST_URL!r};"
            "import migrate_sqlite_to_postgres as M;"
            f"rc1 = M.migrate(dry_run=False, source_path={str(self.src_path)!r});"
            f"rc2 = M.migrate(dry_run=False, source_path={str(self.src_path)!r});"
            "print('RC:', rc1, rc2)"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True,
                                text=True, timeout=300, cwd=str(BACKEND))
        self.assertIn("RC: 0 0", result.stdout, result.stderr)

        db = sessionmaker(bind=tgt_engine)()
        try:
            row = db.query(models.Report).filter_by(report_id="MIG-1").first()
            self.assertIsNotNone(row)
            self.assertEqual((row.risk_score, row.sif_potential), (90, "YES"))
            self.assertEqual(db.query(models.Action).filter_by(report_id="MIG-1").count(), 1)
        finally:
            db.close()
            tgt_engine.dispose()


if __name__ == "__main__":
    unittest.main()
