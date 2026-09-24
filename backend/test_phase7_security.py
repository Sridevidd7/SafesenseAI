"""
SafeSense AI — Phase 7 Production Security & Deployment Test Suite
Validates:
1. Production Configuration & Fail-Fast Secrets Validation
2. Password Hashing & Verification (bcrypt)
3. Authentication & RBAC Authorization Gates
4. Demo Mode Isolation
5. Security Response Headers Middleware
6. Request ID Tracing Middleware
7. Rate Limiting Middleware
8. Upload Validation (File Size 413, File Extension 422)
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
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from main import app, DEMO_USERS
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


def test_demo_user_passwords_verify_correctly():
    """Passwords in DEMO_USERS verify against expected demo credentials."""
    for email, data in DEMO_USERS.items():
        assert verify_password(data["password"], data["password"]) is True
    assert verify_password("admin123", DEMO_USERS["admin@safesense.ai"]["password"]) is True


# =========================================================================
# 3. JWT Lifecycle & RBAC Roles
# =========================================================================
def test_jwt_token_lifecycle():
    """Token generation, UTC expiry, and claims decoding."""
    token = create_access_token(
        data={"sub": "admin@safesense.ai", "role": "Administrator", "name": "Admin User"},
        expires_minutes=15,
    )
    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == "admin@safesense.ai"
    assert decoded["role"] == "Administrator"
    assert "exp" in decoded


def test_jwt_invalid_token_returns_none():
    """Tampered token fails verification safely."""
    assert decode_access_token("invalid.token.payload") is None


# =========================================================================
# 4. Demo Mode Isolation
# =========================================================================
def test_login_demo_mode_allowed():
    """Login with valid demo credentials when demo mode is active."""
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@safesense.ai", "password": "admin123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert data["user"]["role"] == "Administrator"


def test_login_demo_mode_rejected_when_disabled():
    """Demo login is rejected in production when allow_demo_auth=False."""
    prod_settings = Settings(
        environment="production",
        allow_demo_auth=False,
        jwt_secret_key="a" * 32,
    )
    with patch("main.settings", prod_settings):
        response = client.post(
            "/api/auth/login",
            json={"email": "admin@safesense.ai", "password": "admin123"},
        )
        assert response.status_code == 403
        assert "Demo authentication is disabled" in response.json()["detail"]


def test_login_invalid_password():
    """Invalid credentials return 401 Unauthorized."""
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@safesense.ai", "password": "wrongpassword"},
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
    response = client.post("/api/upload", files=files)
    assert response.status_code == 422
    assert "not supported" in response.json()["detail"].lower()


def test_upload_rejects_oversized_file():
    """Files exceeding MAX_UPLOAD_SIZE_BYTES are rejected with 413."""
    oversized = b"a" * (16 * 1024 * 1024)
    files = {"file": ("large.csv", io.BytesIO(oversized), "text/csv")}
    response = client.post("/api/upload", files=files)
    assert response.status_code == 413
    assert "maximum allowed" in response.json()["detail"].lower()


# =========================================================================
# 9. Admin Endpoint RBAC & Production Disablement
# =========================================================================
def test_admin_reset_requires_authentication():
    """Unauthenticated call to /api/admin/reset-db returns 401."""
    response = client.post("/api/admin/reset-db")
    assert response.status_code == 401


def test_admin_reset_requires_admin_role():
    """Safety Officer token calling reset-db returns 403 Forbidden."""
    officer_token = create_access_token({"sub": "officer@safesense.ai", "role": "Safety Officer"})
    response = client.post(
        "/api/admin/reset-db",
        headers={"Authorization": f"Bearer {officer_token}"},
    )
    assert response.status_code == 403
    assert "Access forbidden" in response.json()["detail"]


def test_admin_reset_disabled_in_production():
    """Admin reset endpoint is permanently disabled in production."""
    admin_token = create_access_token({"sub": "admin@safesense.ai", "role": "Administrator"})
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
