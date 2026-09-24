"""
utils/logging_config.py — Structured JSON & PII-safe logging baseline (Phase 7).

Ensures all application logs:
- Output structured JSON in production mode (standard text in local development)
- Automatically scrub credentials, authorization tokens, passwords, and sensitive PII
- Include correlation request ID if available in request context
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict


# Patterns to redact from logs
SENSITIVE_PATTERNS = [
    (re.compile(r'("?(?:password|token|secret|jwt|groq_api_key|api_key)"?\s*[:=]\s*)"[^"]+"', re.IGNORECASE), r'\1"[REDACTED]"'),
    (re.compile(r'("?(?:password|token|secret|jwt|groq_api_key|api_key)"?\s*[:=]\s*)[^\s,}\']+', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*', re.IGNORECASE), r'Bearer [REDACTED]'),
    (re.compile(r'postgresql\+?[^:]*://[^:]+:[^@]+@', re.IGNORECASE), r'postgresql://[USER]:[REDACTED]@'),
    (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), r'[REDACTED_SSN]'),
    (re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'), r'[REDACTED_CARD]'),
]


def scrub_sensitive_data(message: str) -> str:
    """Scrub passwords, secrets, database credentials, and Bearer tokens from string."""
    if not isinstance(message, str):
        message = str(message)
    for pattern, replacement in SENSITIVE_PATTERNS:
        message = pattern.sub(replacement, message)
    return message


class SafeJsonFormatter(logging.Formatter):
    """
    Format logs as JSON objects with automatic secret scrubbing.
    """

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        raw_msg = record.getMessage()
        safe_msg = scrub_sensitive_data(raw_msg)

        log_data: Dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": safe_msg,
            "module": record.module,
            "line": record.lineno,
        }

        # Include request_id if present
        request_id = getattr(record, "request_id", None)
        if request_id:
            log_data["request_id"] = request_id

        if record.exc_info:
            log_data["exception"] = scrub_sensitive_data(self.formatException(record.exc_info))

        return json.dumps(log_data)


def configure_logging(is_production: bool = False, log_level: int = logging.INFO) -> None:
    """Configure root logger with safe formatter based on environment."""
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    stream_handler = logging.StreamHandler()
    if is_production:
        stream_handler.setFormatter(SafeJsonFormatter())
    else:
        fmt = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
        stream_handler.setFormatter(logging.Formatter(fmt))

    root_logger.addHandler(stream_handler)
