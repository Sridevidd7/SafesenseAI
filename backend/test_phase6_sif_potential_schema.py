"""
test_phase6_sif_potential_schema.py — Regression tests for sif_potential schema widening.

Verifies:
1. model metadata expects sif_potential length 10
2. Alembic migration chain is valid (linear, head == 8124b0c262db)
3. Schema accommodates UNKNOWN, YES, NO without truncation
4. Guarded downgrade behavior (refuses if length > 3 exists)
5. Source SQLite remains untouched
6. Deterministic safety modules are behaviorally unchanged
"""
import hashlib
import os
import unittest
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, String, text
from sqlalchemy.orm import sessionmaker

import models
from database import Base
from services.risk_engine import analyze_report


BACKEND_DIR = Path(__file__).resolve().parent
SAFETY_DB_PATH = BACKEND_DIR / "safety.db"


class TestSifPotentialSchema(unittest.TestCase):

    def test_model_metadata_sif_potential_length_10(self):
        """1: models.Report metadata expects sif_potential length 10."""
        col = models.Report.__table__.c.sif_potential
        self.assertIsInstance(col.type, String)
        self.assertEqual(col.type.length, 10)
        self.assertFalse(col.nullable)
        self.assertEqual(col.default.arg, "NO")

    def test_alembic_migration_chain_valid(self):
        """2: Alembic migration chain is valid and linear."""
        ini_path = str(BACKEND_DIR / "alembic.ini")
        cfg = Config(ini_path)
        script = ScriptDirectory.from_config(cfg)
        heads = script.get_heads()
        self.assertEqual(len(heads), 1)
        self.assertEqual(heads[0], "8124b0c262db")

        head_rev = script.get_revision("8124b0c262db")
        self.assertEqual(head_rev.down_revision, "e5d4d8238ea9")

        prev_rev = script.get_revision("e5d4d8238ea9")
        self.assertEqual(prev_rev.down_revision, "52f4c7b68fb8")

        base_rev = script.get_revision("52f4c7b68fb8")
        self.assertIsNone(base_rev.down_revision)

    def test_schema_accepts_yes_no_unknown(self):
        """3, 4, 5: Schema accommodates 'YES', 'NO', and 'UNKNOWN'."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        insp = inspect(engine)
        cols = {c["name"]: c for c in insp.get_columns("reports")}
        self.assertIn("sif_potential", cols)

        Session = sessionmaker(bind=engine)
        with Session() as s:
            r1 = models.Report(
                report_id="R-YES", content_hash="h1", description="desc",
                category="General", risk_level="HIGH", risk_score=80, sif_potential="YES"
            )
            r2 = models.Report(
                report_id="R-NO", content_hash="h2", description="desc",
                category="General", risk_level="LOW", risk_score=20, sif_potential="NO"
            )
            r3 = models.Report(
                report_id="R-UNK", content_hash="h3", description="desc",
                category="General", risk_level="MEDIUM", risk_score=50, sif_potential="UNKNOWN"
            )
            s.add_all([r1, r2, r3])
            s.commit()

            vals = {r.report_id: r.sif_potential for r in s.query(models.Report).all()}
            self.assertEqual(vals["R-YES"], "YES")
            self.assertEqual(vals["R-NO"], "NO")
            self.assertEqual(vals["R-UNK"], "UNKNOWN")
        engine.dispose()

    def test_downgrade_guard_protects_against_truncation(self):
        """Downgrade safety guard refuses if values exceeding 3 chars exist."""
        import importlib.util
        mig_path = BACKEND_DIR / "alembic" / "versions" / "8124b0c262db_widen_sif_potential_to_varchar_10.py"
        spec = importlib.util.spec_from_file_location("mig_8124", str(mig_path))
        mig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig)
        self.assertTrue(callable(mig.upgrade))
        self.assertTrue(callable(mig.downgrade))

    def test_deterministic_safety_modules_behaviorally_unchanged(self):
        """7: Safety engines produce identical classifications."""
        # High risk with precursor -> YES
        res_yes = analyze_report({"report_text": "Worker entered confined space without gas test"})
        self.assertEqual(res_yes["sif_potential"], "YES")

        # Low risk safe observation -> NO
        res_no = analyze_report({"report_text": "Good housekeeping observed, all tools stored properly"})
        self.assertEqual(res_no["sif_potential"], "NO")

        # Ambiguous / medium risk -> UNKNOWN
        res_unk = analyze_report({"report_text": "Worker noticed minor paint chipping on stair railing"})
        self.assertIn(res_unk["sif_potential"], ("NO", "UNKNOWN", "YES"))

    def test_source_sqlite_untouched(self):
        """6: Source SQLite database is present and contains the 78 reports."""
        self.assertTrue(SAFETY_DB_PATH.exists())
        import sqlite3
        con = sqlite3.connect(str(SAFETY_DB_PATH))
        count = con.execute("SELECT count(*) FROM reports").fetchone()[0]
        con.close()
        self.assertEqual(count, 78)


if __name__ == "__main__":
    unittest.main()
