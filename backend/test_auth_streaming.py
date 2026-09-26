"""
test_auth_streaming.py — Production authentication, RBAC and Copilot SSE streaming tests.

Covers:
1. Password hashing (bcrypt) and strength validation.
2. JWT creation/decoding and expiry handling.
3. Signup (register) via API: success, duplicate email, weak password, password mismatch.
4. Login via API: success, invalid credentials, deactivated account.
5. /api/auth/me session resolution; invalid/expired/revoked token rejection.
6. Token-version revocation invalidates previously issued tokens.
7. Password reset: request (uniform response, no enumeration), token consumption,
   session revocation, invalid/expired tokens.
8. RBAC enforcement across routers: 401 unauthenticated, 403 insufficient role,
   write-role required for mutations, admin-only database reset.
9. Health & platform-info endpoints (public, dynamic labels, no secrets).
10. Copilot SSE streaming: protocol, stage ordering, real stages, token events,
    complete event with grounding; error event when GROQ_API_KEY missing.
11. Safety regression spot-checks through the full app stack (risk engine semantics unchanged).
"""
import json
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

# ─── Isolated temp SQLite database for this test module ───────────────────────
_tempdir = tempfile.mkdtemp(prefix="safesense-auth-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tempdir.replace(chr(92), '/')}/auth_test.db"
os.environ.pop("GROQ_API_KEY", None)

import database  # noqa: E402
database.DATABASE_URL = os.environ["DATABASE_URL"]
database.IS_SQLITE = True
database.engine = database.create_database_engine(os.environ["DATABASE_URL"])
database.SessionLocal = database.sessionmaker(autocommit=False, autoflush=False, bind=database.engine)

import models  # noqa: E402
models.Base.metadata.create_all(bind=database.engine)

import main  # noqa: E402  (imports app; routers bound to overridden get_db)
from main import app  # noqa: E402


def _override_get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _install_overrides():
    """Point app dependencies at the isolated test DB.
    Removed again at module teardown so the override cannot leak into other
    test modules collected in the same pytest session (session-scoped state)."""
    app.dependency_overrides[database.get_db] = _override_get_db


def _teardown_module(module):
    app.dependency_overrides.pop(database.get_db, None)

from services.auth import (  # noqa: E402
    hash_password,
    verify_password,
    validate_password_strength,
    create_access_token,
    decode_access_token,
    generate_reset_token,
    hash_reset_token,
    EXPIRE_MINUTES,
)

client = TestClient(app)
_install_overrides()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Password & token primitives
# ═══════════════════════════════════════════════════════════════════════════════

class TestPasswordAndTokenPrimitives(unittest.TestCase):

    def test_bcrypt_hash_and_verify(self):
        h = hash_password("Sup3rSecret!")
        self.assertNotIn("Sup3rSecret!", h)
        self.assertTrue(h.startswith("$2"), "password hash must be bcrypt")
        self.assertTrue(verify_password("Sup3rSecret!", h))
        self.assertFalse(verify_password("wrong", h))

    def test_plaintext_never_stored(self):
        pw = "An0therPassw0rd"
        h = hash_password(pw)
        self.assertNotEqual(h, pw)
        self.assertTrue(verify_password(pw, h))

    def test_password_strength_rules(self):
        self.assertIsNotNone(validate_password_strength("short1"))
        self.assertIsNotNone(validate_password_strength("nodigitsatall"))
        self.assertIsNotNone(validate_password_strength("12345678"))
        self.assertIsNone(validate_password_strength("GoodPass1"))

    def test_jwt_roundtrip_and_expiry(self):
        user = models.User(id=123, email="t@x.io", name="T", password_hash="x", role="Viewer", token_version=2)
        token = create_access_token(user)
        claims = decode_access_token(token)
        self.assertIsNotNone(claims)
        self.assertEqual(claims["sub"], "123")
        self.assertEqual(claims["role"], "Viewer")
        self.assertEqual(claims["tv"], 2)
        self.assertGreater(claims["exp"], time.time())

    def test_jwt_rejects_tampered_token(self):
        user = models.User(id=1, email="t@x.io", name="T", password_hash="x", role="Viewer")
        token = create_access_token(user)
        tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
        self.assertIsNone(decode_access_token(tampered))

    def test_expired_token_rejected(self):
        with patch("services.auth.EXPIRE_MINUTES", -1):
            import services.auth as authsvc
            from datetime import datetime, timedelta, timezone
            from jose import jwt as jose_jwt
            expired = jose_jwt.encode(
                {"sub": "1", "email": "t@x.io", "role": "Viewer", "tv": 0, "type": "access",
                 "iat": datetime.now(timezone.utc) - timedelta(minutes=10),
                 "exp": datetime.now(timezone.utc) - timedelta(minutes=5)},
                authsvc.JWT_SECRET, algorithm="HS256")
        self.assertIsNone(decode_access_token(expired))

    def test_reset_token_hashing(self):
        tok = generate_reset_token()
        h = hash_reset_token(tok)
        self.assertEqual(h, hash_reset_token(tok))
        self.assertNotEqual(h, tok)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Signup / login / session API
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Create accounts here (NOT in test methods) so tests are order-independent.
        # The first account overall becomes Administrator (bootstrap); the second defaults to Viewer.
        r1 = client.post("/api/auth/register", json={
            "name": "Asha Verma", "email": "asha@plantco.com",
            "password": "Str0ngPass!", "confirm_password": "Str0ngPass!",
            "organization": "PlantCo",
        })
        assert r1.status_code == 201, r1.text
        cls.asha = r1.json()
        r2 = client.post("/api/auth/register", json={
            "name": "Ravi Kumar", "email": "ravi@plantco.com",
            "password": "Str0ngPass2", "confirm_password": "Str0ngPass2",
        })
        assert r2.status_code == 201, r2.text
        cls.ravi = r2.json()

    def test_register_first_user_is_admin_bootstrap(self):
        self.assertEqual(self.asha["user"]["role"], "Administrator")  # first account bootstrap
        self.assertIn("token", self.asha)
        self.assertNotIn("password_hash", self.asha["user"])
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {self.asha['token']}"})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], "asha@plantco.com")
        self.assertEqual(me.json()["organization"], "PlantCo")

    def test_register_second_user_defaults_viewer(self):
        self.assertEqual(self.ravi["user"]["role"], "Viewer")

    def test_register_duplicate_email_409(self):
        resp = client.post("/api/auth/register", json={
            "name": "Dup User", "email": "asha@plantco.com",
            "password": "Str0ngPass!", "confirm_password": "Str0ngPass!",
        })
        self.assertEqual(resp.status_code, 409)

    def test_register_weak_password_422(self):
        resp = client.post("/api/auth/register", json={
            "name": "Weak", "email": "weak@plantco.com",
            "password": "short1", "confirm_password": "short1",
        })
        self.assertEqual(resp.status_code, 422)

    def test_register_password_mismatch_422(self):
        resp = client.post("/api/auth/register", json={
            "name": "Mismatch", "email": "mm@plantco.com",
            "password": "GoodPass1", "confirm_password": "GoodPass2",
        })
        self.assertEqual(resp.status_code, 422)

    def test_login_success(self):
        resp = client.post("/api/auth/login", json={
            "email": "asha@plantco.com", "password": "Str0ngPass!",
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["user"]["role"], "Administrator")
        self.assertIn("token", body)

    def test_login_invalid_password_401(self):
        resp = client.post("/api/auth/login", json={"email": "asha@plantco.com", "password": "wrongpass1"})
        self.assertEqual(resp.status_code, 401)

    def test_login_unknown_account_401(self):
        resp = client.post("/api/auth/login", json={"email": "ghost@nowhere.io", "password": "whatever1"})
        self.assertEqual(resp.status_code, 401)

    def test_me_requires_token(self):
        self.assertEqual(client.get("/api/auth/me").status_code, 401)

    def test_me_rejects_garbage_token(self):
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
        self.assertEqual(resp.status_code, 401)

    def test_deactivated_account_403_and_login_blocked(self):
        # create + deactivate
        r = client.post("/api/auth/register", json={
            "name": "Gone User", "email": "gone@plantco.com",
            "password": "Str0ngPass9", "confirm_password": "Str0ngPass9",
        })
        token = r.json()["token"]
        with database.SessionLocal() as db:
            u = db.query(models.User).filter(models.User.email == "gone@plantco.com").first()
            u.is_active = False
            db.commit()
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me.status_code, 403)
        login = client.post("/api/auth/login", json={"email": "gone@plantco.com", "password": "Str0ngPass9"})
        self.assertEqual(login.status_code, 403)

    def test_token_version_bump_revokes_sessions(self):
        r = client.post("/api/auth/register", json={
            "name": "Revoke Me", "email": "revoke@plantco.com",
            "password": "Str0ngPass7", "confirm_password": "Str0ngPass7",
        })
        token = r.json()["token"]
        me_before = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me_before.status_code, 200)
        with database.SessionLocal() as db:
            u = db.query(models.User).filter(models.User.email == "revoke@plantco.com").first()
            u.token_version = int(u.token_version or 0) + 1
            db.commit()
        me_after = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me_after.status_code, 401)

    def test_logout_requires_auth(self):
        r = client.post("/api/auth/register", json={
            "name": "Out User", "email": "out@plantco.com",
            "password": "Str0ngPass4", "confirm_password": "Str0ngPass4",
        })
        token = r.json()["token"]
        self.assertEqual(client.post("/api/auth/logout").status_code, 401)
        ok = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(ok.status_code, 200)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Password reset flow
# ═══════════════════════════════════════════════════════════════════════════════

class TestPasswordReset(unittest.TestCase):

    def test_forgot_uniform_response_and_no_enumeration(self):
        with patch.dict(os.environ, {"SAFESENSE_DEV_EXPOSE_RESET_TOKEN": "0"}, clear=False):
            os.environ.pop("SMTP_HOST", None)
            known = client.post("/api/auth/forgot-password", json={"email": "asha@plantco.com"})
            unknown = client.post("/api/auth/forgot-password", json={"email": "nobody@nowhere.io"})
        self.assertEqual(known.status_code, 200)
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(known.json()["message"], unknown.json()["message"])
        self.assertIsNone(known.json().get("dev_reset_token"))

    def test_full_reset_flow_revokes_old_sessions(self):
        # register
        r = client.post("/api/auth/register", json={
            "name": "Reset User", "email": "reset@plantco.com",
            "password": "0ldPassw0rd", "confirm_password": "0ldPassw0rd",
        })
        old_token = r.json()["token"]

        with patch.dict(os.environ, {"SAFESENSE_DEV_EXPOSE_RESET_TOKEN": "1"}, clear=False):
            os.environ.pop("SMTP_HOST", None)
            fr = client.post("/api/auth/forgot-password", json={"email": "reset@plantco.com"})
        dev_token = fr.json().get("dev_reset_token")
        self.assertTrue(dev_token, "dev token should be exposed under explicit dev flag")

        rr = client.post("/api/auth/reset-password", json={
            "token": dev_token, "password": "N3wPassw0rd!", "confirm_password": "N3wPassw0rd!",
        })
        self.assertEqual(rr.status_code, 200, rr.text)
        new_token = rr.json()["token"]

        # old token revoked, new token works
        self.assertEqual(client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"}).status_code, 401)
        self.assertEqual(client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"}).status_code, 200)

        # login with new password
        self.assertEqual(client.post("/api/auth/login", json={
            "email": "reset@plantco.com", "password": "N3wPassw0rd!"}).status_code, 200)

        # token is single-use
        reuse = client.post("/api/auth/reset-password", json={
            "token": dev_token, "password": "An0therPass1", "confirm_password": "An0therPass1"})
        self.assertEqual(reuse.status_code, 400)

    def test_reset_with_invalid_token_400(self):
        resp = client.post("/api/auth/reset-password", json={
            "token": "totally-invalid-token-value", "password": "N3wPassw0rd!", "confirm_password": "N3wPassw0rd!"})
        self.assertEqual(resp.status_code, 400)

    def test_reset_mismatch_422(self):
        resp = client.post("/api/auth/reset-password", json={
            "token": "totally-invalid-token-value", "password": "N3wPassw0rd!", "confirm_password": "Diff3rent1!"})
        self.assertEqual(resp.status_code, 422)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. RBAC enforcement across routers
# ═══════════════════════════════════════════════════════════════════════════════

class TestRBAC(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        def _mk(email, role):
            with database.SessionLocal() as db:
                u = models.User(email=email, name=email.split("@")[0],
                                password_hash=hash_password("Str0ngPass1"), role=role, is_active=True)
                db.add(u)
                db.commit()
                db.refresh(u)
                return create_access_token(u)
        cls.admin_token = _mk("admin.r@plantco.com", "Administrator")
        cls.hse_token = _mk("hse.r@plantco.com", "HSE Officer")
        cls.viewer_token = _mk("viewer.r@plantco.com", "Viewer")

    def _h(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_protected_routes_reject_anonymous(self):
        cases = [
            ("GET", "/api/reports"),
            ("POST", "/api/reports", {"description": "Worker at height without harness and tied off to nothing above."}),
            ("GET", "/api/dashboard/summary"),
            ("GET", "/api/actions"),
            ("GET", "/api/analytics/patterns"),
            ("GET", "/api/risk-intelligence/trends"),
            ("POST", "/api/copilot/chat", {"message": "How many SIF reports this year?"}),
            ("POST", "/api/analyze-report", {"report_text": "Confined space entry without gas testing completed."}),
        ]
        for case in cases:
            method, path = case[0], case[1]
            body = case[2] if len(case) > 2 else None
            resp = client.request(method, path, json=body)
            self.assertEqual(resp.status_code, 401, f"{method} {path} should require auth")

    def test_viewer_cannot_write(self):
        self.assertEqual(client.post("/api/reports", headers=self._h(self.viewer_token),
                                     json={"description": "Forklift operating with failed horn in busy aisle."}).status_code, 403)
        self.assertEqual(client.post("/api/actions", headers=self._h(self.viewer_token),
                                     json={"description": "Fix signage", "owner": "Viewer"}).status_code, 403)

    def test_hse_can_write_and_read(self):
        resp = client.post("/api/reports", headers=self._h(self.hse_token),
                           json={"description": "Confined space entry started before gas testing was completed."})
        self.assertEqual(resp.status_code, 201, resp.text)
        self.assertEqual(client.get("/api/reports", headers=self._h(self.hse_token)).status_code, 200)
        self.assertEqual(client.get("/api/dashboard/summary", headers=self._h(self.hse_token)).status_code, 200)
        self.assertEqual(client.get("/api/analytics/patterns", headers=self._h(self.hse_token)).status_code, 200)

    def test_reset_db_requires_admin(self):
        self.assertEqual(client.post("/api/admin/reset-db?confirm=true", headers=self._h(self.hse_token)).status_code, 403)
        self.assertEqual(client.post("/api/admin/reset-db?confirm=true", headers=self._h(self.viewer_token)).status_code, 403)
        self.assertEqual(client.post("/api/admin/reset-db?confirm=true", headers=self._h(self.admin_token)).status_code, 200)

    def test_roles_never_trusted_from_browser(self):
        """Server-side role resolution: DB role changes apply immediately, per request."""
        # Dedicated user so this test cannot affect sibling RBAC tests.
        with database.SessionLocal() as db:
            u = models.User(email="promote.r@plantco.com", name="Promote",
                            password_hash=hash_password("Str0ngPass1"), role="Viewer", is_active=True)
            db.add(u)
            db.commit()
            db.refresh(u)
            token = create_access_token(u)

        # As Viewer: writes forbidden
        resp = client.post("/api/reports", headers=self._h(token),
                           json={"description": "Viewer should not be able to write this report."})
        self.assertEqual(resp.status_code, 403)

        # Promote in DB — same token, new role applies immediately (no re-login)
        with database.SessionLocal() as db:
            u = db.query(models.User).filter(models.User.email == "promote.r@plantco.com").first()
            u.role = "Safety Manager"
            db.commit()
        resp = client.post("/api/reports", headers=self._h(token),
                           json={"description": "Role change reflected immediately via server-side resolution."})
        self.assertEqual(resp.status_code, 201, "server-side role resolution must reflect DB role changes")


# ═════════════════════════════════════════════════════════════════ dashboard.py
# 5. Health / platform-info
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealthAndPlatformInfo(unittest.TestCase):

    def test_health_public_and_dynamic(self):
        resp = client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["database"], "SQLite (local)")  # dynamic, not hardcoded PostgreSQL claims

    def test_platform_info_public_no_secrets(self):
        resp = client.get("/api/auth/platform-info")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn(body["database"], ["SQLite (local)", "PostgreSQL"])
        self.assertIn(body["environment"], ["local", "development", "production"])
        blob = json.dumps(body)
        for secret_marker in ["postgres://", "postgresql://", "supabase", "password", "key"]:
            self.assertNotIn(secret_marker, blob.lower())


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Copilot SSE streaming
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_sse(text: str):
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


class TestCopilotStreaming(unittest.TestCase):

    def test_stream_requires_auth(self):
        resp = client.post("/api/copilot/chat/stream", json={"message": "How many SIF reports?"})
        self.assertEqual(resp.status_code, 401)

    def test_stream_missing_groq_key_yields_error_event(self):
        r = client.post("/api/auth/register", json={
            "name": "Stream User", "email": "stream@plantco.com",
            "password": "Str0ngPass6", "confirm_password": "Str0ngPass6"})
        token = r.json()["token"]
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GROQ_API_KEY", None)
            resp = client.post("/api/copilot/chat/stream", headers={"Authorization": f"Bearer {token}"},
                               json={"message": "How many SIF reports do we have?"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/event-stream", resp.headers["content-type"])
        events = _parse_sse(resp.text)
        types = [e["type"] for e in events]
        # Real stages appear in order before the error
        self.assertIn("stage", types)
        self.assertEqual(types[0], "stage")
        self.assertEqual(events[0]["stage"], "SANITIZE")
        self.assertIn("error", types)
        self.assertNotIn("token", types)
        self.assertNotIn("complete", types)

    def test_stream_stage_sequence_and_grounding_with_mocked_llm(self):
        r = client.post("/api/auth/register", json={
            "name": "Stream Admin", "email": "streamadmin@plantco.com",
            "password": "Str0ngPass5", "confirm_password": "Str0ngPass5"})
        token = r.json()["token"]

        # seed one report so retrieval has data
        client.post("/api/reports", headers={"Authorization": f"Bearer {token}"},
                    json={"description": "Confined space entry without completed gas testing, energy isolation not applied."})

        fake_completion = MagicMock()
        fake_completion.choices = [MagicMock(delta=MagicMock(content="SIF"))]
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = iter([fake_completion, fake_completion])

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key-123", "GROQ_MODEL": "llama-3.3-70b-versatile"}, clear=False):
            with patch("groq.Groq", return_value=fake_client):
                resp = client.post("/api/copilot/chat/stream",
                                   headers={"Authorization": f"Bearer {token}"},
                                   json={"message": "What is our confined space SIF exposure?"})
        self.assertEqual(resp.status_code, 200)
        events = _parse_sse(resp.text)
        types = [e["type"] for e in events]
        stages = [e["stage"] for e in events if e["type"] == "stage"]
        self.assertEqual(stages, ["SANITIZE", "UNDERSTAND", "RETRIEVE", "SIF_ANALYSIS",
                                  "BARRIER_ANALYSIS", "PATTERN_ANALYSIS", "EVIDENCE", "GENERATION"])
        self.assertIn("token", types)
        complete = [e for e in events if e["type"] == "complete"][0]
        self.assertIn("grounding", complete)
        self.assertIn("reports_examined", complete["grounding"])
        self.assertGreaterEqual(complete["grounding"]["reports_examined"], 0)
        self.assertIn("data_source", complete)
        self.assertTrue(complete["data_source"])

    def test_blocking_chat_backward_compatible_503_without_key(self):
        r = client.post("/api/auth/register", json={
            "name": "Block User", "email": "block@plantco.com",
            "password": "Str0ngPass3", "confirm_password": "Str0ngPass3"})
        token = r.json()["token"]
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GROQ_API_KEY", None)
            resp = client.post("/api/copilot/chat", headers={"Authorization": f"Bearer {token}"},
                               json={"message": "How many reports?"})
        self.assertEqual(resp.status_code, 503)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Safety regression spot-checks (deterministic engines unchanged)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafetyRegressionSpotChecks(unittest.TestCase):
    """Representative cases through the full app stack; engine semantics must be unchanged."""

    def test_harmless_low_risk(self):
        from services.risk_engine import analyze_report
        res = analyze_report({"report_text": "Routine walkthrough completed, all PPE worn, no hazards found during housekeeping in the control room."})
        self.assertLessEqual(res["risk_score"], 40)
        self.assertEqual(res["sif_potential"], "NO")

    def test_confined_space_unsafe_exposure_high(self):
        from services.risk_engine import analyze_report
        res = analyze_report({"report_text": "Worker entered confined space without completing gas testing while energy isolation was not applied."})
        self.assertGreaterEqual(res["risk_score"], 60)
        self.assertEqual(res["sif_potential"], "YES")

    def test_working_at_height_violation(self):
        from services.risk_engine import analyze_report
        res = analyze_report({"report_text": "Technician working at height on scaffold without fall protection harness in place."})
        self.assertGreaterEqual(res["risk_score"], 50)

    def test_preventive_stop_before_exposure_lower_than_active(self):
        from services.risk_engine import analyze_report
        stopped = analyze_report({"report_text": "Operator stopped the job before confined space entry; gas testing was completed and permit verified."})
        active = analyze_report({"report_text": "Worker inside confined space without gas testing completed and energy isolation not applied."})
        self.assertLess(stopped["risk_score"], active["risk_score"])

    def test_multiple_barrier_failures_score_higher_than_single(self):
        from services.risk_engine import analyze_report
        single = analyze_report({"report_text": "Gas testing not completed before confined space entry."})
        multi = analyze_report({"report_text": "Gas testing not completed and energy isolation not applied and worker inside confined space without rescue plan."})
        self.assertGreater(multi["risk_score"], single["risk_score"])


if __name__ == "__main__":
    unittest.main()
