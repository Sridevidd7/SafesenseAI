"""
services/auth.py — Authentication, password hashing, and role-based authorization (Phase 7).

Provides:
- JWT token generation & verification using centralized secrets from config.py
- Password hashing & verification using bcrypt (passlib)
- Role-based authorization dependencies for FastAPI endpoints (RBAC)
- Fail-safe user context extraction
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

import bcrypt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import settings

logger = logging.getLogger("safesense.auth")

security_bearer = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash, with plain fallback for demo passwords."""
    if not hashed_password:
        return False
    # If the stored password starts with bcrypt signature
    if hashed_password.startswith("$2b$") or hashed_password.startswith("$2a$"):
        try:
            pwd_bytes = plain_password.encode("utf-8")[:72]
            return bcrypt.checkpw(pwd_bytes, hashed_password.encode("utf-8"))
        except Exception as exc:
            logger.warning(f"Bcrypt verification failed: {exc}")
            return False
    # Constant-time comparison for legacy/plain demo passwords
    return hmac.compare_digest(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt (max 72 bytes)."""
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


hash_password = get_password_hash


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * pad)


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
    expires_minutes: Optional[int] = None,
) -> str:
    """
    Generate a signed JWT token using HMAC-SHA256 and the configured secret key.
    """
    header = _b64url_encode(json.dumps({"alg": settings.jwt_algorithm, "typ": "JWT"}).encode())
    payload = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    elif expires_minutes is not None:
        expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)

    payload["exp"] = expire.timestamp()
    payload["iat"] = datetime.now(timezone.utc).timestamp()
    payload_enc = _b64url_encode(json.dumps(payload).encode())

    sig_input = f"{header}.{payload_enc}".encode()
    sig = _b64url_encode(
        hmac.new(settings.jwt_secret_key.encode(), sig_input, hashlib.sha256).digest()
    )
    return f"{header}.{payload_enc}.{sig}"


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify signature and expiration of a JWT token.
    Returns decoded payload dictionary or None if invalid/expired.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, payload_enc, sig = parts

        sig_input = f"{header}.{payload_enc}".encode()
        expected = _b64url_encode(
            hmac.new(settings.jwt_secret_key.encode(), sig_input, hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig, expected):
            return None

        payload = json.loads(_b64url_decode(payload_enc))
        exp = payload.get("exp")
        if exp is None or exp < datetime.now(timezone.utc).timestamp():
            return None

        return payload
    except Exception:
        return None


decode_access_token = verify_token


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
) -> Dict[str, Any]:
    """
    FastAPI dependency requiring a valid Bearer token.
    Raises 401 Unauthorized if missing, expired, or invalid.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "email": payload.get("email") or payload.get("sub"),
        "role": payload.get("role", "Viewer"),
        "name": payload.get("name"),
    }


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
) -> Optional[Dict[str, Any]]:
    """
    FastAPI dependency that returns user dictionary if a valid token is provided,
    or None if unauthenticated (for public/permissive endpoints).
    """
    if not credentials or not credentials.credentials:
        return None
    payload = verify_token(credentials.credentials)
    if not payload:
        return None
    return {
        "email": payload.get("email") or payload.get("sub"),
        "role": payload.get("role", "Viewer"),
        "name": payload.get("name"),
    }


def require_role(allowed_roles: Sequence[str]):
    """
    FastAPI dependency factory enforcing Role-Based Access Control (RBAC).
    Usage:
        user = Depends(require_role(["Administrator", "Safety Manager"]))
    """
    allowed_set = {r.lower() for r in allowed_roles}

    def role_checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_role = (user.get("role") or "").lower()
        if user_role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: requires one of the following roles: {', '.join(allowed_roles)}.",
            )
        return user

    return role_checker
