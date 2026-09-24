"""
services/embedding_provider.py — Phase 6 Batch 3 embedding provider abstraction.

Minimal contract for future embedding implementations. This batch ships ONLY
the abstraction with an explicitly unavailable default provider:

- NO OpenAI/cloud embedding APIs
- NO sentence-transformers / torch / transformers
- NO network downloads
- NO API keys
- NO fake/random embeddings (ever — an unavailable provider must say so)

Resolution order (get_provider):
    1. SAFESENSE_EMBEDDING_PROVIDER env:
         "none"/"off"/unset  -> UnavailableEmbeddingProvider (default)
         "custom"            -> import path from
                                SAFESENSE_EMBEDDING_PROVIDER_MODULE
                                (dotted path exposing get_provider())
    2. Anything else -> UnavailableEmbeddingProvider

The provider is consumed only by services/vector_store.py (advisory retrieval
infrastructure). It is never imported by, and must never be imported into, the
deterministic safety engines.
"""
from __future__ import annotations

import importlib
import logging
import os
from abc import ABC, abstractmethod
from typing import List, Optional, Sequence

logger = logging.getLogger("safesense.embedding_provider")

PROVIDER_FLAG = "SAFESENSE_EMBEDDING_PROVIDER"
PROVIDER_MODULE_FLAG = "SAFESENSE_EMBEDDING_PROVIDER_MODULE"


class EmbeddingProvider(ABC):
    """Minimal provider contract: text in, vectors out (deterministic per model)."""

    model_id: str = "unspecified"
    dim: Optional[int] = None

    @abstractmethod
    def embed(self, text: str) -> Optional[List[float]]:
        """Embed one text; None when the provider cannot embed."""

    @abstractmethod
    def embed_batch(self, texts: Sequence[str]) -> List[Optional[List[float]]]:
        """Embed many texts, preserving order; None entries on failure."""


class UnavailableEmbeddingProvider(EmbeddingProvider):
    """
    Default provider: explicitly unavailable. Never generates vectors —
    fake/random embeddings would poison similarity semantics, so the absent
    capability is always reported instead of simulated.
    """

    model_id = "unavailable"
    dim = None

    def embed(self, text: str) -> Optional[List[float]]:
        return None

    def embed_batch(self, texts: Sequence[str]) -> List[Optional[List[float]]]:
        return [None for _ in texts]


def get_provider() -> EmbeddingProvider:
    """
    Resolve the configured embedding provider. Defaults to the unavailable
    provider; a custom provider can be supplied via environment variables
    (dotted module path exposing get_provider()). Import failures degrade to
    the unavailable provider — ingestion must never break over embeddings.
    """
    configured = (os.getenv(PROVIDER_FLAG, "none").strip().lower())
    if configured in ("", "none", "off", "unavailable"):
        return UnavailableEmbeddingProvider()

    module_path = (os.getenv(PROVIDER_MODULE_FLAG) or "").strip()
    if not module_path:
        logger.warning(
            "[EMBEDDING_PROVIDER] %s=%s but %s is not set; using unavailable provider",
            PROVIDER_FLAG, configured, PROVIDER_MODULE_FLAG,
        )
        return UnavailableEmbeddingProvider()

    try:
        module = importlib.import_module(module_path)
        provider = module.get_provider()
        if not isinstance(provider, EmbeddingProvider):
            raise TypeError("custom provider does not implement EmbeddingProvider")
        logger.info("[EMBEDDING_PROVIDER] loaded custom provider from %s", module_path)
        return provider
    except Exception as exc:
        logger.warning("[EMBEDDING_PROVIDER] custom provider failed (%s); using unavailable", exc)
        return UnavailableEmbeddingProvider()


def get_provider_info() -> dict:
    """Explainability: which provider is configured and available."""
    provider = get_provider()
    return {
        "provider_flag": PROVIDER_FLAG,
        "configured": (os.getenv(PROVIDER_FLAG, "none").strip().lower()),
        "model_id": provider.model_id,
        "dim": provider.dim,
        "available": not isinstance(provider, UnavailableEmbeddingProvider),
    }
