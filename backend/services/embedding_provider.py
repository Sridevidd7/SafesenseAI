"""
services/embedding_provider.py — Phase 6/7 embedding provider abstraction & production provider.

Provides:
- Abstract base class EmbeddingProvider (contract: text in, vectors out)
- UnavailableEmbeddingProvider (default: explicitly unavailable, zero fake vectors)
- OpenAICompatibleEmbeddingProvider (production: HTTP/REST endpoint integration)
- Dynamic custom module loading via SAFESENSE_EMBEDDING_PROVIDER_MODULE

Resolution order (get_provider):
    1. SAFESENSE_EMBEDDING_PROVIDER env:
         "none"/"off"/unset       -> UnavailableEmbeddingProvider (default)
         "openai"/"http"/"openai_compatible" -> OpenAICompatibleEmbeddingProvider
         "custom"                 -> import path from SAFESENSE_EMBEDDING_PROVIDER_MODULE
    2. Anything else              -> UnavailableEmbeddingProvider

SAFETY BOUNDARY:
The provider is consumed only by services/vector_store.py (advisory retrieval infrastructure).
It is never imported by, and must never be imported into, the deterministic safety engines.
Embeddings and similarity outputs are strictly advisory and NEVER authoritative for safety decisions.
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence

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


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    """
    Production-ready HTTP/REST embedding provider for OpenAI-compatible endpoints
    (e.g., OpenAI, Azure OpenAI, vLLM, Ollama, or internal embedding gateways).

    Configuration via environment variables:
    - SAFESENSE_EMBEDDING_API_URL: endpoint URL (default: https://api.openai.com/v1/embeddings)
    - SAFESENSE_EMBEDDING_API_KEY: authentication key (optional if internal gateway)
    - SAFESENSE_EMBEDDING_MODEL: model identifier (default: text-embedding-3-small)
    - SAFESENSE_EMBEDDING_DIM: output vector dimensions (default: 768 to match PostgreSQL schema)
    - SAFESENSE_EMBEDDING_TIMEOUT: network timeout in seconds (default: 5.0)
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_id: Optional[str] = None,
        dim: Optional[int] = None,
        timeout: float = 5.0,
    ):
        self.api_url = (api_url or os.getenv("SAFESENSE_EMBEDDING_API_URL", "https://api.openai.com/v1/embeddings")).strip()
        self.api_key = (api_key if api_key is not None else os.getenv("SAFESENSE_EMBEDDING_API_KEY", "")).strip()
        self.model_id = (model_id or os.getenv("SAFESENSE_EMBEDDING_MODEL", "text-embedding-3-small")).strip()
        self.dim = dim or int(os.getenv("SAFESENSE_EMBEDDING_DIM", "768"))
        self.timeout = float(os.getenv("SAFESENSE_EMBEDDING_TIMEOUT", str(timeout)))

    def embed(self, text: str) -> Optional[List[float]]:
        """Embed a single string."""
        if not text or not text.strip():
            return None
        res = self.embed_batch([text])
        return res[0] if res else None

    def embed_batch(self, texts: Sequence[str]) -> List[Optional[List[float]]]:
        """
        Embed a sequence of texts via the configured HTTP endpoint.
        Returns a list of vectors matching input length, with None on failures.
        """
        if not texts:
            return []

        # If calling OpenAI directly and API key is missing, fail safely
        if "api.openai.com" in self.api_url and not self.api_key:
            logger.warning("[EMBEDDING_PROVIDER] SAFESENSE_EMBEDDING_API_KEY is not set for OpenAI endpoint; skipping embedding.")
            return [None for _ in texts]

        payload: Dict[str, Any] = {
            "model": self.model_id,
            "input": list(texts),
        }
        # Include dimensions parameter if supported (e.g. text-embedding-3)
        if self.dim:
            payload["dimensions"] = self.dim

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "SafeSenseAI/1.2.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            req = urllib.request.Request(
                url=self.api_url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status != 200:
                    logger.warning("[EMBEDDING_PROVIDER] Endpoint returned HTTP %s", resp.status)
                    return [None for _ in texts]
                body = json.loads(resp.read().decode("utf-8"))

            data_list = body.get("data", [])
            # Sort by index if provided to guarantee order
            data_list = sorted(data_list, key=lambda item: item.get("index", 0))

            vectors: List[Optional[List[float]]] = []
            for item in data_list:
                vec = item.get("embedding")
                if isinstance(vec, list) and (self.dim is None or len(vec) == self.dim):
                    vectors.append(vec)
                else:
                    vectors.append(None)

            # Pad if returned list is shorter
            while len(vectors) < len(texts):
                vectors.append(None)

            return vectors

        except urllib.error.HTTPError as http_err:
            logger.warning("[EMBEDDING_PROVIDER] HTTP error %s from %s: %s", http_err.code, self.api_url, http_err.reason)
            return [None for _ in texts]
        except urllib.error.URLError as url_err:
            logger.warning("[EMBEDDING_PROVIDER] Network error contacting %s: %s", self.api_url, url_err.reason)
            return [None for _ in texts]
        except Exception as exc:
            logger.warning("[EMBEDDING_PROVIDER] Unexpected embedding failure: %s", exc)
            return [None for _ in texts]


def get_provider() -> EmbeddingProvider:
    """
    Resolve the configured embedding provider. Defaults to the unavailable
    provider; 'openai_compatible' / 'http' instantiates the production HTTP provider;
    'custom' imports from SAFESENSE_EMBEDDING_PROVIDER_MODULE.
    """
    configured = (os.getenv(PROVIDER_FLAG, "none").strip().lower())
    if configured in ("", "none", "off", "unavailable"):
        return UnavailableEmbeddingProvider()

    if configured in ("openai", "http", "openai_compatible", "production"):
        return OpenAICompatibleEmbeddingProvider()

    if configured == "custom":
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

    logger.warning("[EMBEDDING_PROVIDER] unrecognized provider '%s'; using unavailable provider", configured)
    return UnavailableEmbeddingProvider()


get_embedding_provider = get_provider


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
