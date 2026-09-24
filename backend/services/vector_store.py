"""
services/vector_store.py — Phase 6 Batch 2 vector storage abstraction.

SAFETY BOUNDARY (READ FIRST)
----------------------------
This module provides PERSISTENCE and SIMILARITY SEARCH for report embedding
vectors. It is advisory retrieval infrastructure ONLY:

    ALLOWED uses:  retrieval ordering, semantic search, pattern candidate
                   discovery, Copilot evidence retrieval.

    FORBIDDEN uses: calculating risk scores, determining SIF, determining
                   temporal state, determining barrier failures, determining
                   life-saving rules, overriding deterministic classification,
                   or any other safety decision.

Accordingly:
- Vector rows contain NO safety fields (only report reference + model id +
  opaque vector + dimension metadata). Safety attributes live exclusively in
  the relational `reports` table and deterministic engines.
- This module must NEVER be imported by risk_engine.py, rule_classifier.py,
  barrier_dictionary.py, concept_extractor.py, or pattern_engine.py.
- Similarity results are candidate references (report_id + score), never
  safety verdicts. Any consumer attaching safety meaning MUST pass candidates
  through the existing deterministic validation (e.g. Phase 5
  semantic_service.validate_candidate, barrier_dictionary, rule_classifier).

DESIGN
------
Two backends behind one interface:

- PostgreSQL + pgvector (when the configured DATABASE_URL is PostgreSQL):
  native vector column with HNSW cosine index; similarity via `<=>`
  (cosine distance) executed inside the database.
- SQLite fallback (default local/demo mode): a functional no-op/derived
  backend. Upserts persist rows via the portable ORM model (embedding stored
  as JSON text) so the schema contract is exercised, but similarity search
  is unavailable and returns [] — semantic search therefore requires
  PostgreSQL + pgvector, while the application remains fully functional
  without it.

Configuration:
- SAFESENSE_EMBEDDINGS: "off" (default) | "on". Default OFF — persistence and
  search are inactive unless explicitly enabled.
- Embedding generation itself is intentionally NOT implemented in this batch:
  callers supply vectors; no model downloads, no network, no external APIs.

All operations degrade cleanly (return values indicating unavailability)
rather than raising when the backend or feature flag is disabled.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

logger = logging.getLogger("safesense.vector_store")

# ─── Configuration ────────────────────────────────────────────────────────────

EMBEDDINGS_FLAG = "SAFESENSE_EMBEDDINGS"
DEFAULT_EMBEDDING_DIM = 768


def embeddings_enabled() -> bool:
    """Feature flag: SAFESENSE_EMBEDDINGS must be explicitly 'on' (default off)."""
    return (os.getenv(EMBEDDINGS_FLAG, "off").strip().lower() == "on")


def _backend_kind() -> str:
    """Resolve the active backend from the configured database URL."""
    from database import IS_SQLITE
    return "sqlite" if IS_SQLITE else "postgresql"


def get_backend_info() -> Dict[str, Any]:
    """Explainability: which backend is active and why."""
    from database import IS_SQLITE
    return {
        "flag": EMBEDDINGS_FLAG,
        "embeddings_enabled": embeddings_enabled(),
        "database_dialect": "sqlite" if IS_SQLITE else "postgresql",
        "backend": _backend_kind(),
        "pgvector_available": _pgvector_importable(),
        "default_dim": DEFAULT_EMBEDDING_DIM,
        "note": (
            "Vector store is advisory retrieval infrastructure. Similarity "
            "results are candidate references only — never safety decisions."
        ),
    }


def _pgvector_importable() -> bool:
    try:
        import pgvector  # noqa: F401
        return True
    except ImportError:
        return False


# ─── Data types ───────────────────────────────────────────────────────────────

@dataclass
class EmbeddingInput:
    """One vector to persist: report reference + model id + raw floats."""
    report_id: str
    model_id: str
    vector: Sequence[float]
    dim: Optional[int] = None

    def validate(self) -> Optional[str]:
        """Return an error string if invalid, else None."""
        if not self.report_id:
            return "report_id is required"
        if not self.model_id:
            return "model_id is required"
        if not self.vector:
            return "vector must not be empty"
        dim = self.dim or len(self.vector)
        if dim != len(self.vector):
            return f"vector length {len(self.vector)} != declared dim {dim}"
        if any(not isinstance(v, (int, float)) for v in self.vector):
            return "vector must contain only numbers"
        return None


@dataclass
class SimilarCandidate:
    """
    A similarity-search result: a candidate REFERENCE with its advisory score.

    Carries no safety attributes by design — consumers join back to the
    relational reports table and deterministic engines for any safety meaning.
    """
    report_id: str
    model_id: str
    score: float            # advisory similarity in [0, 1] (1 - cosine distance)
    distance: float         # raw backend distance (cosine distance for pgvector)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "model_id": self.model_id,
            "score": round(self.score, 6),
            "distance": round(self.distance, 6),
        }


# ─── Vector serialization helpers ─────────────────────────────────────────────

def vector_to_text(vector: Sequence[float]) -> str:
    """Serialize a vector for the portable TEXT column (JSON array)."""
    return json.dumps([float(v) for v in vector])


def text_to_vector(text_repr: str) -> List[float]:
    """Deserialize a TEXT-stored vector (JSON array)."""
    return [float(v) for v in json.loads(text_repr)]


# ─── Public API ───────────────────────────────────────────────────────────────

def _build_search_sql(
    query_vector: Sequence[float],
    model_id: str,
    top_k: int,
    candidate_report_ids: Optional[Sequence[str]] = None,
):
    """
    Build the pgvector similarity-search statement.

    Contract (safety-relevant for correct advisory ranking):
    - candidate_report_ids constrains the query ITSELF via a parameterized IN
      clause placed in the WHERE block, so ORDER BY cosine distance and LIMIT
      operate over the FILTERED candidate set — never post-LIMIT filtering.
    - Bound parameters only; user values are never concatenated into SQL text.

    Returns (sqlalchemy TextClause, params dict).
    """
    from sqlalchemy import text as _text

    params: Dict[str, Any] = {
        "qvec": "[" + ",".join(str(float(v)) for v in query_vector) + "]",
        "model_id": model_id,
        "limit": int(top_k),
    }
    candidate_clause = ""
    if candidate_report_ids is not None:
        ids = [str(i) for i in candidate_report_ids]
        placeholders = ", ".join(f":cid{i}" for i in range(len(ids)))
        for i, cid in enumerate(ids):
            params[f"cid{i}"] = cid
        candidate_clause = f" AND report_id IN ({placeholders})"

    sql = _text(
        """
        SELECT report_id,
               embedding <=> CAST(:qvec AS vector) AS distance
        FROM report_embeddings
        WHERE model_id = :model_id
          AND embedding IS NOT NULL"""
        + candidate_clause
        + """
        ORDER BY embedding <=> CAST(:qvec AS vector)
        LIMIT :limit
        """
    )
    return sql, params


def upsert_embeddings(
    items: Iterable[EmbeddingInput],
    session: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Persist embedding vectors for reports (one row per (report_id, model_id)).

    Args:
        items: embeddings to persist.
        session: optional SQLAlchemy session to reuse (e.g. within an existing
            transaction or for tests). Defaults to a fresh application session.

    Returns an explainability dict; never raises for disabled/unavailable
    backends — degradation is explicit in the result.
    """
    info = get_backend_info()
    if not embeddings_enabled():
        return {
            "status": "disabled",
            "flag": EMBEDDINGS_FLAG,
            "inserted": 0,
            "backend": info["backend"],
            "reason": f"{EMBEDDINGS_FLAG} is off (default)",
        }

    items = list(items)
    errors: List[str] = []
    valid: List[EmbeddingInput] = []
    for item in items:
        err = item.validate()
        if err:
            errors.append(f"{item.report_id or '<missing>'}: {err}")
        else:
            valid.append(item)

    inserted = 0
    if valid:
        try:
            import models

            own_session = session is None
            if own_session:
                from database import SessionLocal
                session = SessionLocal()
            try:
                is_pg = session.bind is not None and session.bind.dialect.name == "postgresql"
                # Native pgvector write format for PostgreSQL ('[v1,v2,...]'::vector);
                # portable JSON text for SQLite (searchable only on PostgreSQL).
                def _write_value(vector: Sequence[float]) -> Any:
                    if is_pg:
                        # Cast to the real vector type server-side; the ORM
                        # column is declared as Vector(768) on PostgreSQL so
                        # a plain string is coerced by pgvector's type engine.
                        return "[" + ",".join(str(float(v)) for v in vector) + "]"
                    return vector_to_text(vector)

                for item in valid:
                    dim = item.dim or len(item.vector)
                    row = (
                        session.query(models.ReportEmbedding)
                        .filter_by(report_id=item.report_id, model_id=item.model_id)
                        .first()
                    )
                    if row is None:
                        row = models.ReportEmbedding(
                            report_id=item.report_id, model_id=item.model_id
                        )
                        session.add(row)
                    row.embedding = _write_value(item.vector)
                    row.dim = dim
                    inserted += 1
                session.commit()
            except Exception as exc:
                session.rollback()
                raise exc
            finally:
                if own_session:
                    session.close()
        except Exception as exc:
            logger.warning("[VECTOR_STORE] upsert failed: %s", exc)
            return {
                "status": "error",
                "inserted": 0,
                "backend": info["backend"],
                "reason": f"upsert failed: {exc}",
                "errors": errors,
            }

    return {
        "status": "ok" if not errors else "partial",
        "inserted": inserted,
        "backend": info["backend"],
        "errors": errors or [],
    }


def search_similar(
    query_vector: Sequence[float],
    model_id: str,
    top_k: int = 10,
    min_score: float = 0.0,
    candidate_report_ids: Optional[Sequence[str]] = None,
    session: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Advisory similarity search: returns candidate report references ordered by
    similarity to query_vector. NEVER returns safety decisions.

    - PostgreSQL + pgvector: native `<=>` cosine-distance search with HNSW
      index, filtered by model_id (and optionally restricted to a candidate
      set of report_ids). Candidate filtering happens INSIDE the SQL WHERE
      clause, so top-k is computed over the filtered set (never post-LIMIT).
    - SQLite / disabled flag / any failure: returns status explaining
      unavailability with an empty candidates list. The application and all
      deterministic safety paths are unaffected.

    Args:
        session: optional SQLAlchemy session to reuse (e.g. a session bound to
            a specific test/integration database). Defaults to a fresh
            application session, which is closed before returning; a supplied
            session is left open for the caller to manage.
    """
    info = get_backend_info()
    empty: Dict[str, Any] = {
        "status": "ok",
        "backend": info["backend"],
        "candidates": [],
        "model_id": model_id,
        "note": "Candidates are advisory references; deterministic validation governs any safety meaning.",
    }

    if not embeddings_enabled():
        return {
            **empty,
            "status": "disabled",
            "reason": f"{EMBEDDINGS_FLAG} is off (default)",
        }

    if not query_vector:
        return {**empty, "status": "error", "reason": "query_vector must not be empty"}

    if info["backend"] != "postgresql":
        # SQLite fallback: search unavailable (derived data lives in app
        # memory in this mode). Explicit degradation, no error surfaced.
        return {
            **empty,
            "status": "unavailable",
            "reason": (
                "similarity search requires PostgreSQL + pgvector; "
                "SQLite local/demo mode stores vectors without search"
            ),
        }

    if not _pgvector_importable():
        return {**empty, "status": "error", "reason": "pgvector package not installed"}

    try:
        import models
        from pgvector.sqlalchemy import Vector as PGVector  # noqa: F401
        from sqlalchemy import text as _text

        own_session = session is None
        if own_session:
            from database import SessionLocal
            session = SessionLocal()
        try:
            # Empty candidate set: semantically no matches possible.
            if candidate_report_ids is not None and len(candidate_report_ids) == 0:
                return {**empty, "candidates": []}

            sql, params = _build_search_sql(
                query_vector, model_id, top_k, candidate_report_ids
            )
            rows = session.execute(sql, params).fetchall()

            candidates: List[SimilarCandidate] = []
            for report_id, distance in rows:
                score = max(0.0, 1.0 - float(distance))
                if score < min_score:
                    continue
                candidates.append(
                    SimilarCandidate(
                        report_id=str(report_id),
                        model_id=model_id,
                        score=score,
                        distance=float(distance),
                    )
                )
            return {
                **empty,
                "candidates": [c.to_dict() for c in candidates],
            }
        finally:
            if own_session:
                session.close()
    except Exception as exc:
        logger.warning("[VECTOR_STORE] search failed: %s", exc)
        return {**empty, "status": "error", "reason": f"search failed: {exc}"}


# ─── Optional ingestion hook (minimal, disabled by default) ──────────────────

def queue_embedding_on_ingest(report_id: str, description: str) -> Optional[Dict[str, Any]]:
    """
    Optional embedding persistence hook, called after a report row is created.

    Behavior:
    - SAFESENSE_EMBEDDINGS=off (default): returns None immediately. No
      embedding generation, no DB writes; ingestion behavior is unchanged.
    - Flag on, no provider configured: fails gracefully with status
      "no_provider" — ingestion continues normally, nothing is written.
    - Flag on, provider available: embeds the (already PII-redacted)
      description and upserts the vector. Any failure degrades to a reported
      status without raising — ingestion must never break over embeddings.

    Never alters report analysis, risk, SIF, or any deterministic output.
    """
    if not embeddings_enabled():
        return None
    try:
        from services.embedding_provider import get_provider
        provider = get_provider()
        vector = provider.embed(description or "")
        if vector is None:
            info = get_backend_info()
            return {
                "status": "no_provider",
                "report_id": report_id,
                "backend": info["backend"],
                "model_id": provider.model_id,
                "reason": "embedding provider is unavailable; no vector written",
            }

        result = upsert_embeddings([
            EmbeddingInput(
                report_id=report_id,
                model_id=provider.model_id,
                vector=vector,
                dim=provider.dim or len(vector),
            )
        ])
        return {"status": result.get("status"), "report_id": report_id, "detail": result}
    except Exception as exc:  # absolute last resort — ingestion must never break
        logger.debug("Embedding hook degraded: %s", exc)
        return {"status": "error", "report_id": report_id, "reason": str(exc)}
