"""
config.py — SafeSense AI centralized configuration & secrets management (Phase 7).

Manages environment profiles (development, testing, production), validates critical
secrets at startup, and enforces fail-fast security constraints in production mode.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    load_dotenv()
except ImportError:
    pass


DEFAULT_INSECURE_SECRET = "safesense-ai-secret-key-change-in-production"
LEGACY_INSECURE_SECRET = "safesense-ai-change-this-in-production"
KNOWN_INSECURE_SECRETS = {
    DEFAULT_INSECURE_SECRET,
    LEGACY_INSECURE_SECRET,
    "secret",
    "changeme",
    "password",
    "admin123",
}


@dataclass(frozen=True)
class Settings:
    # ── Environment Profile ──────────────────────────────────────────────────
    environment: str = field(
        default_factory=lambda: (
            os.getenv("SAFESENSE_ENV")
            or os.getenv("ENVIRONMENT")
            or "development"
        ).strip().lower()
    )

    # ── Authentication & Secrets ─────────────────────────────────────────────
    jwt_secret_key: str = field(
        default_factory=lambda: os.getenv("JWT_SECRET_KEY", DEFAULT_INSECURE_SECRET)
    )
    jwt_algorithm: str = field(
        default_factory=lambda: os.getenv("JWT_ALGORITHM", "HS256")
    )
    jwt_expire_minutes: int = field(
        default_factory=lambda: int(
            os.getenv(
                "JWT_EXPIRE_MINUTES",
                "60" if (os.getenv("SAFESENSE_ENV") or "").lower() == "production" else "480"
            )
        )
    )

    # ── Security Toggles & Demo Isolation ────────────────────────────────────
    allow_demo_auth: bool = field(
        default_factory=lambda: (
            os.getenv("ALLOW_DEMO_AUTH", "true" if (os.getenv("SAFESENSE_ENV") or "").lower() != "production" else "false")
            .strip().lower() in ("true", "1", "yes")
        )
    )
    allow_admin_reset: bool = field(
        default_factory=lambda: (
            os.getenv("ALLOW_ADMIN_RESET", "true" if (os.getenv("SAFESENSE_ENV") or "").lower() != "production" else "false")
            .strip().lower() in ("true", "1", "yes")
        )
    )

    # ── CORS & Host Hardening ────────────────────────────────────────────────
    allowed_origins: List[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173,https://safesenseai.onrender.com").split(",")
            if o.strip()
        ]
    )

    # ── Upload Limits ────────────────────────────────────────────────────────
    max_upload_size_bytes: int = field(
        default_factory=lambda: int(
            os.getenv("MAX_UPLOAD_SIZE_BYTES", str(15 * 1024 * 1024))  # 15 MB default
        )
    )
    allowed_upload_extensions: tuple = field(
        default=(".csv", ".xlsx", ".xls")
    )

    # ── Rate Limiting ────────────────────────────────────────────────────────
    rate_limit_enabled: bool = field(
        default_factory=lambda: os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower() in ("true", "1", "yes")
    )
    rate_limit_standard_per_min: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_STANDARD_PER_MIN", "120"))
    )
    rate_limit_sensitive_per_min: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_SENSITIVE_PER_MIN", "20"))
    )

    # ── Database Connection Pool (PostgreSQL) ────────────────────────────────
    db_pool_size: int = field(
        default_factory=lambda: int(os.getenv("DB_POOL_SIZE", "10"))
    )
    db_max_overflow: int = field(
        default_factory=lambda: int(os.getenv("DB_MAX_OVERFLOW", "20"))
    )
    db_pool_recycle: int = field(
        default_factory=lambda: int(os.getenv("DB_POOL_RECYCLE", "1800"))
    )
    db_pool_timeout: int = field(
        default_factory=lambda: int(os.getenv("DB_POOL_TIMEOUT", "30"))
    )

    @property
    def is_production(self) -> bool:
        return self.environment in ("production", "prod")

    @property
    def is_testing(self) -> bool:
        return self.environment in ("testing", "test")

    def validate_production(self) -> None:
        """
        Enforce fail-fast security constraints when running in production mode.
        Raises ValueError with clear remediation instructions if violated.
        """
        if not self.is_production:
            return

        errors = []

        # 1. JWT Secret Validation
        if not self.jwt_secret_key:
            errors.append("JWT_SECRET_KEY must be provided in production mode.")
        elif self.jwt_secret_key in KNOWN_INSECURE_SECRETS:
            errors.append(
                "JWT_SECRET_KEY is set to a default/insecure placeholder. "
                "Set a secure, high-entropy secret (>= 32 characters)."
            )
        elif len(self.jwt_secret_key) < 32:
            errors.append(
                f"JWT_SECRET_KEY length ({len(self.jwt_secret_key)}) is insecure. "
                "Production requires at least 32 characters."
            )

        # 2. Database Backend Validation
        db_url = (os.getenv("DATABASE_URL") or "").strip()
        if not db_url:
            errors.append(
                "DATABASE_URL is not set. Production mode requires an explicit "
                "PostgreSQL connection string (e.g. postgresql+psycopg://...)."
            )
        elif db_url.startswith("sqlite"):
            # SQLite allowed only if explicitly forced
            allow_sqlite_prod = os.getenv("ALLOW_SQLITE_IN_PROD", "false").strip().lower() in ("true", "1")
            if not allow_sqlite_prod:
                errors.append(
                    "DATABASE_URL points to SQLite in production mode. "
                    "PostgreSQL is the production-target database. "
                    "(Set ALLOW_SQLITE_IN_PROD=true if this is intentional)."
                )
        elif "safesense:safesense@" in db_url:
            errors.append(
                "Default postgres credentials 'safesense:safesense' detected in "
                "DATABASE_URL. Set dedicated, strong production credentials."
            )

        # 3. CORS Wildcard Check
        for origin in self.allowed_origins:
            if origin == "*":
                errors.append(
                    "ALLOWED_ORIGINS cannot contain wildcard '*' in production "
                    "when allow_credentials=True."
                )

        if errors:
            raise ValueError(
                "CRITICAL: SafeSense AI failed production security validation:\n"
                + "\n".join(f" - {err}" for err in errors)
            )


# Global settings singleton
settings = Settings()
