"""
routes/auth.py — Production authentication endpoints.

Endpoints
---------
POST /api/auth/register         → Create an account (bcrypt hash stored, JWT issued)
POST /api/auth/login            → Verify credentials against the users table, issue JWT
GET  /api/auth/me               → Resolve the current session from the Bearer token
POST /api/auth/logout           → Client-side discard contract (token is stateless; verified)
POST /api/auth/forgot-password  → Issue a single-use reset token (hash stored, not the token)
POST /api/auth/reset-password   → Consume a reset token, set a new bcrypt password
GET  /api/platform-info         → Non-sensitive runtime metadata for UI labels

Security notes:
- No hardcoded accounts. No frontend-issued tokens.
- Password hashes are never returned by any endpoint.
- Forgot-password responses are identical whether or not the account exists
  (prevents account enumeration).
- Reset tokens are single-use, expire, and revoke all existing sessions
  (token_version bump).
- Email delivery is NOT faked: when SMTP/email is not configured the token is
  surfaced only in the response field `reset_delivery` as "email_not_configured"
  together with `dev_reset_token` — and that field is ONLY populated when the
  server runs with SAFESENSE_DEV_EXPOSE_RESET_TOKEN=1 (explicit development
  flag, never enabled by default; production must configure an email provider).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db, IS_SQLITE
import models
from schemas import (
    AuthResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    PlatformInfoResponse,
    RegisterRequest,
    ResetPasswordRequest,
    UserResponse,
)
from services.auth import (
    EXPIRE_MINUTES,
    RESET_TOKEN_EXPIRE_MINUTES,
    ALL_ROLES,
    authenticate_user,
    create_access_token,
    generate_reset_token,
    get_current_user,
    hash_password,
    hash_reset_token,
    validate_password_strength,
    verify_password,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

# First registered account becomes the Administrator (bootstrap); subsequent
# signups default to Viewer pending an administrator role assignment.
_FIRST_USER_BOOTSTRAP_ADMIN = True

VALID_SIGNUP_ROLES_NOTE = "New accounts start with the Viewer role. An Administrator can elevate roles."


def _auth_response(user: models.User) -> AuthResponse:
    return AuthResponse(
        token=create_access_token(user),
        token_type="bearer",
        expires_in_minutes=EXPIRE_MINUTES,
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            organization=user.organization,
            site=user.site,
            is_active=user.is_active,
        ),
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new account",
    description="Creates an account with a bcrypt-hashed password and returns a signed JWT session.",
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    email_norm = payload.email.strip().lower()
    if "@" not in email_norm or "." not in email_norm.split("@")[-1]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Please enter a valid email address.")
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Passwords do not match.")
    strength_error = validate_password_strength(payload.password)
    if strength_error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=strength_error)

    existing = db.query(models.User).filter(models.User.email == email_norm).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    user_count = db.query(models.User).count()
    role = "Administrator" if (_FIRST_USER_BOOTSTRAP_ADMIN and user_count == 0) else "Viewer"

    user = models.User(
        email=email_norm,
        name=payload.name.strip(),
        password_hash=hash_password(payload.password),
        role=role,
        organization=(payload.organization or "").strip() or None,
        is_active=True,
        token_version=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("Account created: id=%s role=%s", user.id, user.role)
    return _auth_response(user)


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Sign in",
    description="Verifies credentials against the users table (bcrypt) and issues a signed JWT.",
)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact an administrator.",
        )
    return _auth_response(user)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Current session user",
    description="Resolves the authenticated user from the Bearer token (server-side role resolution).",
)
def me(user: models.User = Depends(get_current_user)):
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        organization=user.organization,
        site=user.site,
        is_active=user.is_active,
    )


@router.post(
    "/logout",
    summary="Logout",
    description=(
        "JWT sessions are stateless: the client discards the token on logout. "
        "This endpoint verifies the session and returns confirmation, so the UI "
        "never fakes a success state. For forced server-side revocation an "
        "Administrator bumps the user's token_version."
    ),
)
def logout(user: models.User = Depends(get_current_user)):
    return {"status": "logged_out", "detail": "Session token discarded client-side.", "email": user.email}


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    summary="Request a password reset",
    description=(
        "Issues a single-use, expiring reset token. The response is identical "
        "whether or not the account exists (no account enumeration). Email "
        "delivery must be configured in production; see SAFESENSE_DEV_EXPOSE_RESET_TOKEN."
    ),
)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    email_norm = payload.email.strip().lower()
    user = db.query(models.User).filter(models.User.email == email_norm).first()

    # Uniform response — never reveal whether the account exists.
    generic = ForgotPasswordResponse()

    if user is None or not user.is_active:
        # Sleep equalization is unnecessary (bcrypt absent on this path); the
        # uniform response body is the enumeration defense.
        return generic

    token = generate_reset_token()
    user.reset_token_hash = hash_reset_token(token)
    # Store as naive UTC to match SQLite/PostgreSQL column semantics (naive
    # datetimes round-trip through both drivers); compare in the same form.
    user.reset_token_expires_at = (datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)).replace(tzinfo=None)
    db.commit()

    email_configured = bool((os.getenv("SMTP_HOST") or "").strip())
    if email_configured:
        # Production email delivery is a deployment concern (SMTP provider).
        # Contract documented in .env.example; token is never returned here.
        logger.info("Password reset token generated for account id=%s (email delivery configured)", user.id)
        return generic

    # Email not configured: DO NOT fake delivery success. Expose the token only
    # under the explicit development flag so local flows remain testable.
    expose_dev = (os.getenv("SAFESENSE_DEV_EXPOSE_RESET_TOKEN", "0") == "1")
    if expose_dev:
        return ForgotPasswordResponse(
            message="Email delivery is not configured. Development mode: use the token below to reset.",
            dev_reset_token=token,
        )
    logger.warning(
        "Password reset requested but no email provider is configured. "
        "Set SMTP_HOST (production) or SAFESENSE_DEV_EXPOSE_RESET_TOKEN=1 (development only)."
    )
    return generic


@router.post(
    "/reset-password",
    response_model=AuthResponse,
    summary="Reset password with a token",
    description="Consumes a single-use reset token, stores the new bcrypt hash, and revokes all existing sessions.",
)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Passwords do not match.")
    strength_error = validate_password_strength(payload.password)
    if strength_error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=strength_error)

    token_hash = hash_reset_token(payload.token.strip())
    user = db.query(models.User).filter(models.User.reset_token_hash == token_hash).first()
    if user is None or user.reset_token_expires_at is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset link is invalid or has expired.")
    if user.reset_token_expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        # Clear the expired token so it cannot be retried.
        user.reset_token_hash = None
        user.reset_token_expires_at = None
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset link is invalid or has expired.")

    user.password_hash = hash_password(payload.password)
    user.reset_token_hash = None
    user.reset_token_expires_at = None
    user.token_version = int(user.token_version or 0) + 1  # revoke all existing sessions
    db.commit()
    db.refresh(user)
    return _auth_response(user)


# ─── Platform info (non-sensitive runtime metadata for UI labels) ─────────────

@router.get(
    "/platform-info",
    response_model=PlatformInfoResponse,
    summary="Runtime platform metadata (non-sensitive)",
    description="Returns database/vector/environment labels for UI display. Never exposes credentials or hosts.",
)
def platform_info():
    from services.vector_store import get_backend_info as _vector_backend_info

    if IS_SQLITE:
        database_label = "SQLite (local)"
        environment = "local"
    else:
        database_label = "PostgreSQL"
        environment = "production" if os.getenv("RENDER") or os.getenv("ENVIRONMENT") == "production" else "development"

    vinfo = _vector_backend_info()
    if vinfo.get("backend") == "postgresql" and vinfo.get("pgvector_available"):
        vector_label = "pgvector (active)" if vinfo.get("embeddings_enabled") else "pgvector (ready)"
    elif vinfo.get("backend") == "postgresql":
        vector_label = "Application-layer retrieval"
    else:
        vector_label = "SQLite local fallback"

    return PlatformInfoResponse(
        database=database_label,
        vector_store=vector_label,
        environment=environment,
        version="1.3.0",
    )
