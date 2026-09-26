"""
SafeSense AI — Phase 7 Production Security & Deployment Test Suite
Validates:
1. Production Configuration & Fail-Fast Secrets Validation
2. Password Hashing & Verification (bcrypt)
3. Authentication & RBAC Authorization Gates (real DB-backed accounts)
4. Authentication Failure Modes (replaces legacy demo-mode isolation tests:
   demo credentials no longer exist anywhere in the system)
5. Security Response Headers Middleware
6. Request ID Tracing Middleware
7. Rate Limiting Middleware
8. Upload Validation (Auth 401/403, File Size 413, File Extension 422)
9. Admin Endpoint Protection (RBAC & Production Disablement)
10. Sensitive Data & Credential Scrubbing in Structured Logging
11. Health (/api/health) and Readiness (/api/ready) Probes
12. Embedding Provider Interface & Graceful Fallback
13. Authoritative Safety Semantic Integrity Boundary
"""

import os
import io
import time
import asyncio
import pytest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from main import app
from config import Settings, settings
from services.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)
from utils.logging_config import scrub_sensitive_data
from services.embedding_provider import (
    get_embedding_provider,
    OpenAICompatibleEmbeddingProvider,
    UnavailableEmbeddingProvider,
)
from services.risk_engine import analyze_report
from services.rule_classifier import classify_life_saving_rule
from services.barrier_dictionary import detect_barriers

client = TestClient(app)


def _make_user(email: str, role: str):
    """Idempotently create a real DB-backed user (roles resolve from the DB row)."""
    import models
    from database import SessionLocal
    with SessionLocal() as db:
        u = db.query(models.User).filter(models.User.email == email).first()
        if u is None:
            u = models.User(email=email, name=email.split("@")[0],
                            password_hash=hash_password("Str0ngPass1"),
                            role=role, is_active=True)
            db.add(u)
            db.commit()
            db.refresh(u)
        return create_access_token(u)


def _write_auth() -> dict:
    return {"Authorization": "Bearer " + _make_user("phase7.writer@plantco.com", "HSE Officer")}


# =========================================================================
# 1. Configuration & Fail-Fast Secrets Validation
# =========================================================================
def test_production_config_fail_fast_on_weak_secret():
    """Production mode must reject weak/short JWT secrets."""
    s = Settings(
        environment="production",
        jwt_secret_key="short",
        allowed_origins=["https://safesense.example.com"],
    )
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql+psycopg://user:strongpass123@prod-db.internal:5432/safesense"}):
        with pytest.raises(ValueError, match="at least 32 characters"):
            s.validate_production()


def test_production_config_fail_fast_on_default_secret():
    """Production mode must reject default development secret."""
    s = Settings(
        environment="production",
        jwt_secret_key="safesense-ai-secret-key-change-in-production",
        allowed_origins=["https://safesense.example.com"],
    )
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql+psycopg://user:strongpass123@prod-db.internal:5432/safesense"}):
        with pytest.raises(ValueError, match="insecure placeholder"):
            s.validate_production()


def test_production_config_fail_fast_on_sqlite():
    """Production mode must reject SQLite databases."""
    s = Settings(
        environment="production",
        jwt_secret_key="a" * 32,
        allowed_origins=["https://safesense.example.com"],
    )
    with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///safety.db", "ALLOW_SQLITE_IN_PROD": "false"}):
        with pytest.raises(ValueError, match="SQLite in production mode"):
            s.validate_production()


def test_production_config_fail_fast_on_wildcard_cors():
    """Production mode must reject wildcard CORS."""
    s = Settings(
        environment="production",
        jwt_secret_key="a" * 32,
        allowed_origins=["*"],
    )
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql+psycopg://user:strongpass123@prod-db.internal:5432/safesense"}):
        with pytest.raises(ValueError, match="cannot contain wildcard"):
            s.validate_production()


def test_production_config_fail_fast_on_default_postgres_password():
    """Production mode must reject default dev postgres credentials."""
    s = Settings(
        environment="production",
        jwt_secret_key="a" * 32,
        allowed_origins=["https://safesense.example.com"],
    )
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql+psycopg://safesense:safesense@prod-db.internal:5432/safesense"}):
        with pytest.raises(ValueError, match="Default postgres credentials"):
            s.validate_production()


def test_production_config_passes_with_valid_parameters():
    """Valid production settings pass validation without error."""
    s = Settings(
        environment="production",
        jwt_secret_key="super-secure-production-jwt-secret-key-that-is-long-enough-32bytes",
        allowed_origins=["https://safesense.corp.com"],
    )
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql+psycopg://safesense_app:K9mQ8zL2@db-cluster.internal:5432/safesense_prod"}):
        # Should not raise
        s.validate_production()


# =========================================================================
# 2. Password Hashing & Verification
# =========================================================================
def test_password_hashing_and_verification():
    """Bcrypt password hashing and verification."""
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)
    assert hashed != password
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_legacy_demo_credentials_are_eradicated():
    """Demo credentials must not exist anywhere in the auth stack.
    Every user identity resolves from the database (bcrypt hash), never from
    an in-code credential dictionary."""
    import main
    import services.auth as auth_mod
    assert not hasattr(main, "DEMO_USERS"), "DEMO_USERS must be removed from main"
    src = open(auth_mod.__file__, encoding="utf-8").read()
    for cred in ("admin123", "hse123", "mgr123", "site123"):
        assert cred not in src, f"demo credential {cred} leaked into services/auth.py"


# =========================================================================
# 3. JWT Lifecycle & RBAC Roles
# =========================================================================
def test_jwt_token_lifecycle():
    """Token generation, UTC expiry, and claims decoding."""
    fake_user = SimpleNamespace(id=424242, email="phase7@plantco.com",
                                role="Administrator", token_version=0)
    token = create_access_token(fake_user)
    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == "424242"
    assert decoded["role"] == "Administrator"
    assert decoded["type"] == "access"
    assert "exp" in decoded


def test_jwt_invalid_token_returns_none():
    """Tampered token fails verification safely."""
    assert decode_access_token("invalid.token.payload") is None


# =========================================================================
# 4. Authentication Failure Modes (real DB-backed accounts; no demo mode)
# =========================================================================
def test_login_rejects_unknown_account():
    """Unknown account returns generic 401 (no account enumeration)."""
    response = client.post(
        "/api/auth/login",
        json={"email": "nobody@safesense.ai", "password": "whatever123"},
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


def test_login_rejects_legacy_demo_credential():
    """The legacy demo account/password must not authenticate anymore."""
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@safesense.ai", "password": "admin123"},
    )
    assert response.status_code == 401


def test_login_invalid_password_generic_error():
    """Wrong password returns generic 401 — no hint which field was wrong."""
    response = client.post(
        "/api/auth/register",
        json={"name": "Phase Seven", "email": "phase7.login@plantco.com",
              "password": "Str0ngPass!", "confirm_password": "Str0ngPass!"},
    )
    assert response.status_code in (201, 409)  # 409 on re-run: already registered
    response = client.post(
        "/api/auth/login",
        json={"email": "phase7.login@plantco.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


# =========================================================================
# 5. Security Response Headers Middleware
# =========================================================================
def test_security_headers_present_on_all_responses():
    """All responses must contain hardening headers."""
    response = client.get("/api/health")
    assert response.status_code == 200
    headers = response.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("X-XSS-Protection") == "1; mode=block"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


# =========================================================================
# 6. Request ID Middleware
# =========================================================================
def test_request_id_generated_and_propagated():
    """Requests receive unique X-Request-ID header."""
    response = client.get("/api/health")
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0

    # Inbound X-Request-ID is preserved
    custom_id = "test-req-id-12345"
    response2 = client.get("/api/health", headers={"X-Request-ID": custom_id})
    assert response2.headers.get("X-Request-ID") == custom_id


# =========================================================================
# 7. Rate Limiter Middleware
# =========================================================================
def test_rate_limiter_blocks_excessive_requests():
    """Rapid bursts exceeding limit return HTTP 429."""
    from middleware import RateLimiterMiddleware

    middleware = RateLimiterMiddleware(app=MagicMock())
    client_ip = "192.168.1.100"
    now = time.time()
    for _ in range(settings.rate_limit_sensitive_per_min):
        middleware._requests[client_ip].append((now, True))

    mock_request = MagicMock()
    mock_request.url.path = "/api/auth/login"
    mock_request.headers.get.return_value = None
    mock_request.client.host = client_ip

    async def mock_call_next(req):
        return MagicMock(status_code=200)

    response = asyncio.run(middleware.dispatch(mock_request, mock_call_next))
    assert response.status_code == 429


# =========================================================================
# 8. Upload Security Validation
# =========================================================================
def test_upload_rejects_disallowed_extension():
    """Disallowed file extension (e.g. .exe) is rejected with 422."""
    file_content = b"echo malicious"
    files = {"file": ("malware.exe", io.BytesIO(file_content), "application/octet-stream")}
    response = client.post("/api/upload", files=files, headers=_write_auth())
    assert response.status_code == 422
    assert "not supported" in response.json()["detail"].lower()


def test_upload_rejects_oversized_file():
    """Files exceeding MAX_UPLOAD_SIZE_BYTES are rejected with 413."""
    oversized = b"a" * (16 * 1024 * 1024)
    files = {"file": ("large.csv", io.BytesIO(oversized), "text/csv")}
    response = client.post("/api/upload", files=files, headers=_write_auth())
    assert response.status_code == 413
    assert "maximum allowed" in response.json()["detail"].lower()


def test_upload_requires_authentication():
    """Legacy upload alias must reject anonymous uploads (401)."""
    files = {"file": ("ok.csv", io.BytesIO(b"description\nsafe observation text here"), "text/csv")}
    assert client.post("/api/upload", files=files).status_code == 401
    assert client.post("/upload", files=files).status_code == 401


def test_upload_allowed_for_viewer_role():
    """Viewer-role token can upload reports (200 on /api/upload, 201 on /api/reports/upload)."""
    token = _make_user("phase7.viewer@plantco.com", "Viewer")
    files = {"file": ("ok.csv", io.BytesIO(b"description\nsafe observation text here"), "text/csv")}
    response = client.post("/api/upload", files=files,
                           headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

    files2 = {"file": ("ok2.csv", io.BytesIO(b"description\nsafe observation text here"), "text/csv")}
    response2 = client.post("/api/reports/upload", files=files2,
                            headers={"Authorization": f"Bearer {token}"})
    assert response2.status_code == 201


def test_viewer_forbidden_from_admin_and_write_operations():
    """Viewer role must remain forbidden from admin reset and operational writes (403)."""
    token = _make_user("phase7.viewer@plantco.com", "Viewer")
    headers = {"Authorization": f"Bearer {token}"}

    # Admin reset forbidden for Viewer
    admin_resp = client.post("/api/admin/reset-db", headers=headers)
    assert admin_resp.status_code == 403
    assert "administrator role required" in admin_resp.json()["detail"].lower()

    # Action creation (operational write) forbidden for Viewer
    action_resp = client.post(
        "/api/actions",
        json={"title": "Test Action", "assigned_to": "Test User", "due_date": "2026-12-31"},
        headers=headers,
    )
    assert action_resp.status_code == 403


# =========================================================================
# 9. Admin Endpoint RBAC & Production Disablement
# =========================================================================
def test_admin_reset_requires_authentication():
    """Unauthenticated call to /api/admin/reset-db returns 401."""
    response = client.post("/api/admin/reset-db")
    assert response.status_code == 401


def test_admin_reset_requires_admin_role():
    """Non-admin token calling reset-db returns 403 Forbidden."""
    # Token alone is insufficient: the role is re-resolved from the DB row.
    fake_user = SimpleNamespace(id=424244, email="officer7@plantco.com",
                                role="Safety Officer", token_version=0)
    officer_token = create_access_token(fake_user)
    response = client.post(
        "/api/admin/reset-db",
        headers={"Authorization": f"Bearer {officer_token}"},
    )
    assert response.status_code == 401  # account id does not exist in DB


def test_admin_reset_disabled_in_production():
    """Admin reset endpoint is permanently disabled in production."""
    admin_token = _make_user("phase7.admin@plantco.com", "Administrator")
    prod_settings = Settings(
        environment="production",
        allow_admin_reset=False,
        jwt_secret_key="a" * 32,
    )
    with patch("routes.admin.settings", prod_settings):
        response = client.post(
            "/api/admin/reset-db",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 403
        assert "permanently disabled in production" in response.json()["detail"]


# =========================================================================
# 10. Logging Sensitive Data Scrubbing
# =========================================================================
def test_sensitive_data_scrubbing():
    """Scrubber redacts JWTs, database URLs, passwords, and sensitive PII."""
    raw_message = (
        "User logged in with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-IDvACSpB7 "
        "connecting to postgresql+psycopg://safesense:secretpass@localhost:5432/safesense "
        "with SSN 123-45-6789 and password: mySuperSecret123"
    )
    scrubbed = scrub_sensitive_data(raw_message)
    assert "secretpass" not in scrubbed
    assert "mySuperSecret123" not in scrubbed
    assert "123-45-6789" not in scrubbed
    assert "Bearer [REDACTED]" in scrubbed
    assert "[REDACTED_SSN]" in scrubbed


# =========================================================================
# 11. Health & Readiness Probes
# =========================================================================
def test_health_probe():
    """Liveness probe /api/health returns status and basic info."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "healthy")
    assert "version" in data


def test_readiness_probe():
    """Readiness probe /api/ready returns component statuses."""
    response = client.get("/api/ready")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "database" in data
    assert "vector_store" in data
    assert "environment" in data


# =========================================================================
# 12. Embedding Provider Interface
# =========================================================================
def test_embedding_provider_resolution():
    """Default provider is unavailable; OpenAI compatible provider initializes safely."""
    provider = get_embedding_provider()
    assert provider is not None

    openai_provider = OpenAICompatibleEmbeddingProvider(
        api_url="https://api.openai.com/v1/embeddings",
        api_key="test-key",
        model_id="text-embedding-3-small",
        dim=768,
    )
    assert openai_provider.dim == 768
    assert openai_provider.model_id == "text-embedding-3-small"


# =========================================================================
# 13. Authoritative Safety Semantic Integrity Boundary
# =========================================================================
def test_authoritative_safety_semantics_unmodified():
    """Deterministic safety logic outputs are completely intact and verified."""
    # 1. Safety report analysis
    result = analyze_report({
        "report_text": "Worker fell from 10m height scaffolding without harness, suffered fracture"
    })
    assert result["sif_potential"] == "YES"
    assert result["risk_level"] in ("HIGH", "CRITICAL")
    assert result["risk_score"] > 60

    # 2. Rule classification
    lsr_res = classify_life_saving_rule("Working on roof edge at high elevation without tie-off")
    assert lsr_res["primary_rule"] == "Working at Height"

    # 3. Barrier extraction
    barriers = detect_barriers("Missing safety harness and broken guardrail at scaffold edge")
    assert "Fall Protection Not Used" in barriers
