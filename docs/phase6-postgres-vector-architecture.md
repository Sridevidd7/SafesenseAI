# Phase 6 — PostgreSQL / Vector-Ready Architecture

## Overview

Phase 6 makes SafeSense AI portable across databases and vector-ready, while
SQLite remains the **default local/demo database** and the deterministic safety
engines remain the **only safety authority**.

Batches:
1. `DATABASE_URL` engine factory + dialect-portable queries + Alembic baseline
2. `report_embeddings` model + pgvector migration + `vector_store.py`
3. Migration script + Docker PostgreSQL profile + embedding provider abstraction

## Database configuration (DATABASE_URL)

| Setting | Behavior |
|---|---|
| `DATABASE_URL` unset/empty | **SQLite** at `backend/safety.db` (default, zero setup; schema auto-bootstrapped + demo seed) |
| `DATABASE_URL=sqlite:///backend/safety.db` | SQLite, explicit |
| `DATABASE_URL=postgresql+psycopg://safesense:safesense@localhost:5432/safesense` | **PostgreSQL** (always use the `postgresql+psycopg://` prefix) |

Engine behavior per dialect:
- SQLite: `check_same_thread=False` (FastAPI threadpool), legacy `ensure_schema_migrations()` bootstrap **runs only on SQLite**.
- PostgreSQL: `pool_pre_ping=True`; schema owned exclusively by **Alembic** (`cd backend && alembic upgrade head`).

## Alembic

```
cd backend
alembic upgrade head          # apply all migrations
alembic downgrade -1          # rollback last migration
alembic revision --autogenerate -m "..."
alembic check                 # verify models match migrations (no drift)
```

URL resolution: `-x db_url=…` > `ALEMBIC_DATABASE_URL` env > app `DATABASE_URL`.
Migrations: `52f4c7b68fb8` baseline (Phases 1–5 schema) → `e5d4d8238ea9`
`report_embeddings` (pgvector on PostgreSQL, portable TEXT variant on SQLite).

## Vector-ready architecture

- **Table** `report_embeddings`: composite PK `(report_id, model_id)`, `dim`
  guard, `created_at`, FK → `reports` with ON DELETE CASCADE. **Contains no
  safety fields** — vector rows are opaque references; risk/SIF/barrier/LSR
  live only in the relational tables and deterministic engines.
- **`services/vector_store.py`**: `upsert_embeddings(...)`, `search_similar(...)`,
  `get_backend_info()`. PostgreSQL+pgvector = native `<=>` cosine search
  (HNSW index, model_id-filtered, optional candidate-set restriction).
  SQLite = portable storage, search explicitly `unavailable` (never simulated).
- **`services/embedding_provider.py`**: `EmbeddingProvider` contract with an
  explicitly **unavailable** default. Custom providers can be plugged via
  `SAFESENSE_EMBEDDING_PROVIDER=custom` +
  `SAFESENSE_EMBEDDING_PROVIDER_MODULE=<dotted.path>`. An unavailable provider
  NEVER fabricates vectors.

## Flags

| Flag | Default | Effect |
|---|---|---|
| `SAFESENSE_EMBEDDINGS` | `off` | `off`: no embedding generation, no writes, ingestion unchanged. `on`: ingest hook embeds + persists when a provider is available; degrades gracefully (`no_provider`) when not. |
| `SAFESENSE_EMBEDDING_PROVIDER` | `none` | Provider selection (see above). |

Embedding generation itself is **deferred**: no model ships in Phase 6, no
network calls, no API keys, no fake/random embeddings.

## Optional PostgreSQL via Docker

The `postgres` service is **profile-gated** — the default stack is unchanged:

```bash
docker compose --profile postgres up -d postgres
# then run the backend with:
#   DATABASE_URL=postgresql+psycopg://safesense:safesense@localhost:5432/safesense
```

Image: `pgvector/pgvector:pg16` (PostgreSQL 16 + pgvector). Credentials are
developer defaults via `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`
env vars — production secrets management is Phase 7 scope.

## SQLite → PostgreSQL migration

```bash
cd backend
# plan without writing:
DATABASE_URL=postgresql+psycopg://… python ../scripts/migrate_sqlite_to_postgres.py --dry-run
# migrate:
DATABASE_URL=postgresql+psycopg://… python ../scripts/migrate_sqlite_to_postgres.py
```

Properties: parents before children; IDs/content hashes preserved (never
regenerated); PII-redacted text copied exactly as stored; idempotent
(existing target rows are skipped); post-run verification of table counts,
content_hash integrity, report_id integrity, child-FK integrity, and a
risk/SIF spot-check; non-zero exit code on any integrity failure; the SQLite
source is never modified.

## Safety boundary

Vector similarity is advisory metadata for **retrieval ordering, semantic
search, pattern-candidate discovery, and Copilot evidence retrieval** only.
It must never compute risk, determine SIF/temporal state/barriers/LSRs, or
override deterministic classification. Enforced structurally: vector tables
carry no safety fields, `vector_store`/`embedding_provider` are importable
only by advisory code paths, and tests assert the protected modules
(`risk_engine`, `rule_classifier`, `barrier_dictionary`, `concept_extractor`,
`pattern_engine`) contain no vector imports and produce identical outputs
across vector operations.

## Testing

```bash
cd backend
pytest                              # full suite (SQLite; no PG required)
TEST_DATABASE_URL=postgresql+psycopg://… pytest test_batch3_migration_vector.py
                                    # + real-PostgreSQL integration tests
```

PostgreSQL integration tests are **skip-guarded**: they run only when
`TEST_DATABASE_URL` is set and reachable. The suite never depends on a
running PostgreSQL.

## Implemented now vs deferred

Implemented in Phase 6: DATABASE_URL abstraction, Alembic foundation +
migrations, portable queries, `report_embeddings`, vector store with pgvector
backend + SQLite fallback, embedding provider abstraction, ingest hook,
migration script, Docker profile, tests/docs.

Deferred (actual production embedding model selection/operation, native
vector column conversion for pre-existing TEXT rows, bulk re-embedding tooling)
and to **Phase 7**: production deployment, managed PostgreSQL, TLS, secrets
management, monitoring, backups/DR, production-scale performance tuning.
