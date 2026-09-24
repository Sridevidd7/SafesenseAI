"""
middleware.py — Production security, request correlation, and rate limiting (Phase 7).

Middleware components:
1. RequestIDMiddleware: assigns unique X-Request-ID for distributed tracing.
2. SecurityHeadersMiddleware: sets standard production security headers.
3. RateLimiterMiddleware: sliding-window rate limiter per client IP.
"""
from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from typing import Dict, List, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from config import settings

logger = logging.getLogger("safesense.middleware")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Ensures every HTTP request has a unique correlation ID (X-Request-ID).
    Propagates incoming X-Request-ID or generates a new UUIDv4.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = req_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Injects hardened security response headers:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy: geolocation=(), microphone=(), camera=()
    - Strict-Transport-Security: in production
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    In-memory sliding-window rate limiter by client IP.
    Protects against denial of service, credential stuffing, and resource exhaustion.
    """

    # Tracks {ip: [(timestamp, is_sensitive), ...]}
    _requests: Dict[str, List[Tuple[float, bool]]] = defaultdict(list)
    _clean_interval: float = 60.0
    _last_clean: float = 0.0

    SENSITIVE_PATHS = {
        "/api/auth/login",
        "/api/copilot/chat",
        "/api/admin/reset-db",
        "/api/admin/reset-database",
    }

    def _cleanup_old_entries(self, now: float) -> None:
        """Purge entries older than 60 seconds."""
        if now - self._last_clean < self._clean_interval:
            return
        self._last_clean = now
        cutoff = now - 60.0
        keys_to_remove = []
        for ip, logs in self._requests.items():
            valid_logs = [entry for entry in logs if entry[0] > cutoff]
            if valid_logs:
                self._requests[ip] = valid_logs
            else:
                keys_to_remove.append(ip)
        for k in keys_to_remove:
            self._requests.pop(k, None)

    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.rate_limit_enabled:
            return await call_next(request)

        # Health & readiness probes are exempt from rate limiting
        if request.url.path in ("/api/health", "/health", "/api/ready", "/ready"):
            return await call_next(request)

        # Determine client IP (support X-Forwarded-For if behind trusted proxy)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

        now = time.time()
        self._cleanup_old_entries(now)

        cutoff = now - 60.0
        ip_history = self._requests[client_ip]
        # Keep only within last minute
        recent = [entry for entry in ip_history if entry[0] > cutoff]
        self._requests[client_ip] = recent

        is_sensitive = any(request.url.path.startswith(p) for p in self.SENSITIVE_PATHS)

        # Total count check
        if len(recent) >= settings.rate_limit_standard_per_min:
            logger.warning(f"[RATE_LIMIT] Client {client_ip} exceeded standard limit ({settings.rate_limit_standard_per_min}/min)")
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
                headers={"Retry-After": "60"},
            )

        # Sensitive count check
        if is_sensitive:
            sensitive_count = sum(1 for entry in recent if entry[1])
            if sensitive_count >= settings.rate_limit_sensitive_per_min:
                logger.warning(f"[RATE_LIMIT] Client {client_ip} exceeded sensitive path limit ({settings.rate_limit_sensitive_per_min}/min)")
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many sensitive requests. Please try again after 60 seconds."},
                    headers={"Retry-After": "60"},
                )

        self._requests[client_ip].append((now, is_sensitive))
        return await call_next(request)
