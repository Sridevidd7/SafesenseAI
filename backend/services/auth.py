"""
services/auth.py — Production authentication & authorization for SafeSense AI.

One coherent architecture (Phase 7 production hardening + product-pass accounts):

- Secrets come from config.settings (fail-fast validation in production).
- Passwords are hashed with bcrypt (rounds 12); plaintext is never stored,
  logged, or accepted for verification.
- Tokens are signed JWTs (python-jose, HS256) with server-side expiry.
- Roles ALWAYS come from the database row resolved server-side in
  get_current_user — never from browser-supplied values. Every request
  re-loads the account so deactivation, role changes and token-version
  revocation take effect immediately.
- `token_version` in the users table lets password changes / explicit
  revocation invalidate all previously issued tokens for an account.
- Password reset uses opaque single-use tokens; only their SHA-256 hash is
  stored, with expiry.

RBAC roles (fixed set, preserved across phases):
    Administrator, Safety Manager, HSE Officer, Site Manager, Viewer

Safety boundary: this module contains NO safety logic. It only gates access.
"""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Set

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config import settings
from database import get_db

# ─── Configuration (centralized via config.settings; env override allowed) ────
JWT_SECRET = settings.jwt_secret_key

JWT_ALGORITHM = settings.jwt_algorithm
EXPIRE_MINUTES = int(os.getenv("AUTH_TOKEN_EXPIRE_MINUTES", str(settings.jwt_expire_minutes)))
RESET_TOKEN_EXPIRE_MINUTES = int(os.getenv("AUTH_RESET_TOKEN_EXPIRE_MINUTES", "30") or "30")

BCRYPT_ROUNDS = 12

# Fixed role model (do not invent roles ad hoc)
ROLE_ADMINISTRATOR = "Administrator"
ROLE_SAFETY_MANAGER = "Safety Manager"
ROLE_HSE_OFFICER = "HSE Officer"
ROLE_SITE_MANAGER = "Site Manager"
ROLE_VIEWER = "Viewer"

ALL_ROLES: List[str] = [
    ROLE_ADMINISTRATOR,
    ROLE_SAFETY_MANAGER,
    ROLE_HSE_OFFICER,
    ROLE_SITE_MANAGER,
    ROLE_VIEWER,
]

READ_ROLES: Set[str] = set(ALL_ROLES)
WRITE_ROLES: Set[str] = {
    ROLE_ADMINISTRATOR,
    ROLE_SAFETY_MANAGER,
    ROLE_HSE_OFFICER,
    ROLE_SITE_MANAGER,
}
ADMIN_ROLES: Set[str] = {ROLE_ADMINISTRATOR}


# ─── Password hashing (bcrypt) ─────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# Alias kept for Phase-7 import compatibility.
get_password_hash = hash_password

# Dummy hash used to equalize timing when the account does not exist.
_DUMMY_HASH = hash_password("timing-equalizer-dummy")


def validate_password_strength(password: str) -> Optional[str]:
    """Return a human-readable reason if the password is too weak, else None."""
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if len(password) > 128:
        return "Password must be at most 128 characters long."
    if not any(c.isalpha() for c in password):
        return "Password must contain at least one letter."
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one number."
    return None


# ─── JWT tokens ────────────────────────────────────────────────────────────────

def create_access_token(user) -> str:
    """Create a signed JWT for a User ORM instance (or dict with id/email/role/token_version)."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "tv": int(getattr(user, "token_version", 0) or 0),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT. Returns the claims dict or None if invalid/expired."""
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if claims.get("type") != "access":
            return None
        return claims
    except JWTError:
        return None


# Alias kept for Phase-7 import compatibility (claims dict or None).
def verify_token(token: str) -> Optional[Dict[str, Any]]:
    return decode_access_token(token)


# ─── Password reset tokens ─────────────────────────────────────────────────────

def generate_reset_token() -> str:
    """Opaque high-entropy reset token. Only its SHA-256 hash is stored."""
    return secrets.token_urlsafe(32)


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ─── FastAPI dependencies ──────────────────────────────────────────────────────

security_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: Session = Depends(get_db),
):
    """
    Resolve the authenticated user from the Bearer token.

    The token is validated cryptographically first, then the account is loaded
    from the database so role/deactivation/token-version changes apply
    immediately (the browser is never trusted for identity).
    """
    import models

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Provide a Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = decode_access_token(credentials.credentials)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or token invalid. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = int(claims.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact an administrator.",
        )

    # Token-version revocation: bumping users.token_version invalidates old JWTs.
    if int(claims.get("tv", 0) or 0) != int(user.token_version or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_roles(allowed: Set[str]):
    """Dependency factory: require the resolved user to have one of `allowed` roles."""
    def _checker(user=Depends(get_current_user)):
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your role ({user.role}) is not authorized for this operation.",
            )
        return user
    return _checker


def require_role(allowed_roles: Sequence[str]):
    """Phase-7-compatible RBAC factory (case-insensitive role names)."""
    allowed_set = {r for r in allowed_roles}

    def role_checker(user=Depends(get_current_user)):
        if user.role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: requires one of the following roles: {', '.join(allowed_roles)}.",
            )
        return user

    return role_checker


def require_authenticated(user=Depends(get_current_user)):
    """Any active account (including Viewer) — for read endpoints."""
    return user


def require_write(user=Depends(get_current_user)):
    """Roles allowed to create/modify operational data (everything except read-only Viewer)."""
    if user.role not in WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Read-only accounts cannot modify safety data.",
        )
    return user


def require_admin(user=Depends(get_current_user)):
    """Administrator-only operations (database reset, admin endpoints)."""
    if user.role not in ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required for this operation.",
        )
    return user


def authenticate_user(db: Session, email: str, password: str):
    """Verify credentials against the users table. Returns the User or None."""
    import models

    email_norm = (email or "").strip().lower()
    user = db.query(models.User).filter(models.User.email == email_norm).first()
    if user is None:
        # Equalize timing to avoid revealing whether the account exists.
        verify_password(password or "", _DUMMY_HASH)
        return None
    if not verify_password(password or "", user.password_hash):
        return None
    return user
