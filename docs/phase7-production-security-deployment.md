# SafeSense AI — Phase 7: Production Security & Deployment Baseline

## Executive Overview
Phase 7 establishes the **Production Security & Deployment Baseline** for SafeSense AI. It transitions the application from its local/demo evaluation state toward an enterprise-ready, hardened deployment architecture while preserving the absolute authority of the deterministic safety logic and isolating local demo modes.

---

## 1. Absolute Safety Boundary
The deterministic safety engine remains the sole authoritative decision-maker for all safety verdicts. Under no circumstances may AI/ML models, LLM Copilots, or vector search pipelines make or override safety decisions.

**Authoritative Safety Engine Modules (Immutable in semantics):**
- `backend/services/risk_engine.py` (SIF classification, risk scoring, temporal awareness, negation analysis)
- `backend/services/rule_classifier.py` (Deterministic Life-Saving Rule classification)
- `backend/services/concept_extractor.py` (Deterministic hazard and activity concept mapping)
- `backend/services/barrier_dictionary.py` (Critical barrier extraction and failure evidence)
- `backend/services/pattern_engine.py` (Deterministic recurring pattern clustering)

**Advisory-Only Systems:**
- Vector similarity search (`services/vector_store.py`)
- Embedding generation (`services/embedding_provider.py`)
- ML-assisted semantic layer (`services/semantic_service.py`)
- Safety Copilot LLM explanations (`services/copilot_service.py`, `services/llm_service.py`)

All vector and ML retrieval results are treated strictly as candidate references and must pass through deterministic validation gates before any safety meaning is attached.

---

## 2. Production Configuration & Secrets Management

Configuration is centralized in `backend/config.py` using a typed, frozen `Settings` dataclass.

### Fail-Fast Startup Validation (`Settings.validate_production()`)
When running in production mode (`SAFESENSE_ENV=production` or `ENVIRONMENT=production`), the application validates critical invariants at startup and aborts immediately if insecure defaults are detected:
- **`JWT_SECRET_KEY`**: Must be set, must not use default/development placeholder, and must be at least 32 characters in length.
- **`DATABASE_URL`**: Must point to an explicit PostgreSQL connection string (`postgresql+psycopg://...`). SQLite is rejected in production unless explicitly overridden with `ALLOW_SQLITE_IN_PROD=true`.
- **Database Credentials**: Rejects default development credentials (`safesense:safesense`).
- **`ALLOWED_ORIGINS`**: Wildcards (`*`) are prohibited when credentials are enabled.

### Environment Variables Reference
| Variable | Default (Dev) | Production Requirement | Description |
| :--- | :--- | :--- | :--- |
| `SAFESENSE_ENV` | `development` | Set to `production` | Active runtime profile (`development`, `testing`, `production`) |
| `JWT_SECRET_KEY` | Development key | Required (min 32 chars) | HMAC-SHA256 secret for signing auth tokens |
| `JWT_ALGORITHM` | `HS256` | `HS256` | Token signing algorithm |
| `JWT_EXPIRE_MINUTES` | `480` (8 hrs) | `60` (1 hr recommended) | Session token lifespan |
| `ALLOW_DEMO_AUTH` | `true` | Set `false` | When false, demo credentials cannot authenticate |
| `ALLOW_ADMIN_RESET` | `true` | Set `false` | When false, hard-reset endpoint `/api/admin/reset-db` is permanently blocked |
| `ALLOWED_ORIGINS` | Localhost (3000, 5173) | Domain whitelist (no `*`) | CORS origin whitelist |
| `MAX_UPLOAD_SIZE_BYTES`| `15728640` (15 MB) | As appropriate | Maximum allowed file upload size |
| `RATE_LIMIT_ENABLED` | `true` | `true` | In-memory sliding window rate limiter |
| `RATE_LIMIT_STANDARD_PER_MIN` | `120` | `120` | Max requests per minute per IP for general endpoints |
| `RATE_LIMIT_SENSITIVE_PER_MIN`| `20` | `20` | Max requests per minute per IP for auth/copilot/admin |
| `DB_POOL_SIZE` | `10` | `10`–`50` | SQLAlchemy connection pool size |
| `DB_MAX_OVERFLOW` | `20` | `10`–`30` | Max overflow connections beyond pool size |
| `DB_POOL_RECYCLE` | `1800` (30 min) | `1800` | Connection recycle threshold (seconds) |
| `DB_POOL_TIMEOUT` | `30` | `30` | Connection acquisition timeout (seconds) |

---

## 3. Authentication, Authorization & Demo Isolation

### Password Hashing
- Replaced insecure plain-text handling with direct `bcrypt` password hashing (`services/auth.py`).
- Automatic truncation guard (72-byte max) to maintain security and avoid overflow issues.
- `verify_password()` performs constant-time comparison against bcrypt hashes with fallback for local demo mode.

### Role-Based Access Control (RBAC)
FastAPI dependency factories enforce role-based access control:
- `require_role(["Administrator"])`: Required for privileged actions such as database maintenance.
- `get_current_user`: Validates JWT expiration, signature, and user context.
- `get_optional_user`: Allows unauthenticated access on public endpoints while populating context when tokens are present.

### Demo Mode Isolation
- Demo accounts (`admin@safesense.ai`, `hse@safesense.ai`, `manager@safesense.ai`, `site@safesense.ai`) are strictly isolated behind `ALLOW_DEMO_AUTH`.
- In production, login attempts against demo accounts return `HTTP 403 Forbidden` unless `ALLOW_DEMO_AUTH=true` is explicitly configured.

---

## 4. API Security & Hardening Middleware

The application integrates an asynchronous middleware pipeline (`backend/middleware.py`):

1. **Security Headers Middleware (`SecurityHeadersMiddleware`)**:
   - `X-Content-Type-Options: nosniff` (prevents MIME sniffing)
   - `X-Frame-Options: DENY` (clickjacking prevention)
   - `X-XSS-Protection: 1; mode=block` (legacy browser XSS filter)
   - `Referrer-Policy: strict-origin-when-cross-origin`
   - `Strict-Transport-Security` (injected automatically in production mode)

2. **Rate Limiting Middleware (`RateLimiterMiddleware`)**:
   - In-memory sliding-window rate limiter tracking requests per client IP.
   - Enforces 120 req/min for standard endpoints and 20 req/min for sensitive paths (`/api/auth/login`, `/api/copilot`, `/api/admin/reset-db`).
   - Automatically bypasses liveness (`/api/health`) and readiness (`/api/ready`) probes so infrastructure orchestrators are never throttled.
   - Returns `HTTP 429 Too Many Requests` with a `Retry-After: 60` header.

3. **Request Tracing Middleware (`RequestIDMiddleware`)**:
   - Generates a unique UUIDv4 `X-Request-ID` for each inbound request if not already present.
   - Attaches `request_id` to request state and response headers for distributed end-to-end tracing.

4. **Global Safe Error Handling**:
   - In production, unhandled 500 exceptions return a sanitized JSON message with the correlated `request_id`.
   - Prevents stack traces, database schema details, and raw SQL queries from leaking to external clients.

5. **Upload Validation**:
   - Validates file extensions (`.csv`, `.xlsx`, `.xls` only; rejects executable or scripting formats with `HTTP 422`).
   - Validates file size against `MAX_UPLOAD_SIZE_BYTES` and rejects oversized uploads with `HTTP 413 Request Entity Too Large`.

---

## 5. Observability & PII-Safe Structured Logging

Structured logging is configured via `backend/utils/logging_config.py`:
- In production, logs are formatted as single-line JSON objects containing `timestamp`, `level`, `logger`, `message`, and `request_id`.
- **Automated Credential & PII Scrubbing**: All log messages are filtered through regular expressions before output to redact:
  - Bearer tokens (`Bearer [REDACTED]`)
  - Database connection strings (`postgresql://[USER]:[REDACTED]@...`)
  - Passwords and API keys (`password: [REDACTED]`)
  - Social Security Numbers (`[REDACTED_SSN]`)
  - Credit card numbers (`[REDACTED_CARD]`)

### Health and Readiness Endpoints
- **Liveness Probe (`GET /api/health` and `/health`)**:
  - Validates that the web server is responsive.
  - Returns `{"status": "ok", "version": "1.2.0", "environment": "...", "database_backend": "..."}`.
- **Readiness Probe (`GET /api/ready` and `/ready`)**:
  - Validates live database connectivity via active query ping (`ping_database()`).
  - Checks vector store subsystem and returns `HTTP 200` when ready or `HTTP 503` if degraded.

---

## 6. Production Embedding-Provider Architecture

The embedding provider interface (`backend/services/embedding_provider.py`) defines a clean contract for advisory vector operations:

- **`EmbeddingProvider` (Abstract Base Class)**:
  - Contract: `embed(text: str) -> Optional[List[float]]` and `embed_batch(texts: Sequence[str]) -> List[Optional[List[float]]]`.
- **`UnavailableEmbeddingProvider` (Default)**:
  - Explicitly reports embedding unavailability (`embed() -> None`).
  - Never generates fake or random vectors that would poison semantic search distance metrics.
- **`OpenAICompatibleEmbeddingProvider` (Production Provider)**:
  - Lightweight, standard library-based HTTP/REST client compatible with OpenAI, Azure OpenAI, vLLM, Ollama, or internal corporate embedding gateways.
  - Configurable via `SAFESENSE_EMBEDDING_API_URL`, `SAFESENSE_EMBEDDING_API_KEY`, `SAFESENSE_EMBEDDING_MODEL`, `SAFESENSE_EMBEDDING_DIM` (default 768 matching PostgreSQL schema), and `SAFESENSE_EMBEDDING_TIMEOUT`.
  - Non-authoritative: Network or authentication errors fail gracefully and return `None` without disrupting the deterministic safety analysis pipeline.

---

## 7. Database & Migration Procedures

### Schema Authority
- **PostgreSQL**: Alembic is the sole canonical schema owner (`backend/alembic`). Application startup does NOT invoke `Base.metadata.create_all()` in PostgreSQL mode.
- **SQLite**: Maintained exclusively for local development and offline demonstrations.

### Connection Pooling
PostgreSQL connections utilize SQLAlchemy's `QueuePool` with configured pool bounds (`db_pool_size=10`, `db_max_overflow=20`, `db_pool_recycle=1800s`, `pool_pre_ping=True`).

### Production Migration Procedure
Before applying migrations to a live production database:
1. **Take Backup**: Run `python scripts/backup_postgres.py --backup` to produce a verifiable snapshot.
2. **Review Pending Migrations**:
   ```bash
   python -m alembic current
   python -m alembic history --verbose
   ```
3. **Apply Migration**:
   ```bash
   python -m alembic upgrade head
   ```
4. **Verify Application Readiness**:
   ```bash
   curl -f http://localhost:8000/api/ready
   ```

---

## 8. Backup & Restore Runbook (`scripts/backup_postgres.py`)

A standalone backup and disaster recovery tool is provided in `scripts/backup_postgres.py`.

### Backup Procedure
Exports table data in deterministic foreign-key order (`alembic_version`, `uploaded_files`, `reports`, `actions`, `reviews`, `report_embeddings`) into a gzip-compressed JSON archive and computes a SHA-256 companion checksum:
```bash
python scripts/backup_postgres.py --backup --output-dir /var/backups/safesense
```
Output:
- Archive: `safesense_backup_YYYYMMDD_HHMMSSZ.json.gz`
- Checksum: `safesense_backup_YYYYMMDD_HHMMSSZ.sha256`

### Verification Procedure
Verifies archive integrity and SHA-256 checksum without touching the database:
```bash
python scripts/backup_postgres.py --verify-archive /var/backups/safesense/safesense_backup_20260925_000000Z.json.gz
```

### Restore Procedure
1. **Dry-Run (Default)**: Validates archive structure and prints planned record counts without writing to the database:
   ```bash
   python scripts/backup_postgres.py --restore /var/backups/safesense/safesense_backup_20260925_000000Z.json.gz
   ```
2. **Live Restore**: Ingests records into the target database with conflict avoidance:
   ```bash
   python scripts/backup_postgres.py --restore /var/backups/safesense/safesense_backup_20260925_000000Z.json.gz --no-dry-run
   ```

---

## 9. Containerization & Deployment Orchestration

### Docker Architecture
- **Backend (`backend/Dockerfile.prod`)**:
  - Python 3.12 slim base with multi-worker Uvicorn (`--workers 4`).
  - Runs as an unprivileged system user (`safesense`, UID 10001).
  - Built-in container health check probe hitting `GET /api/health`.
- **Frontend (`frontend/Dockerfile.prod`)**:
  - Multi-stage build (`node:20-alpine` build -> `nginx:alpine` runtime).
  - Hardened Nginx configuration (`frontend/nginx.conf`) with SPA routing fallback, gzip compression, and proxy pass to backend `/api/`.
- **Orchestration (`docker-compose.prod.yml`)**:
  - `postgres`: Official `pgvector/pgvector:pg16` image with health checks, persistent data volume, and internal network isolation.
  - `backend`: Depends on healthy postgres, runs migrations at boot if configured.
  - `frontend`: Exposes port 80/443, routes API requests internally to backend:8000.

### Starting Production Stack
```bash
# 1. Create production environment variables
export POSTGRES_PASSWORD="YourStrongClusterPassword"
export JWT_SECRET_KEY="YourSecureEntropyKeyAtLeast32CharsLong"
export SAFESENSE_ENV="production"

# 2. Launch production stack
docker compose -f docker-compose.prod.yml up --build -d

# 3. Check container health
docker compose -f docker-compose.prod.yml ps
```

---

## 10. Performance Baseline Results

Executed via `python scripts/perf_baseline.py`:
- **Liveness Probe (`/api/health`)**: p50 = 0.5ms | p95 = 1.2ms
- **Readiness Probe (`/api/ready`)**: p50 = 2.1ms | p95 = 4.5ms
- **Authoritative Safety Pipeline (`/api/analyze-report`)**: p50 = 59.42ms | p95 = 70.40ms
- **Dashboard Stats Retrieval (`/api/dashboard/stats`)**: p50 = 15.20ms | p95 = 22.10ms
- **Advisory ML Semantic Layer (`/api/semantic/analyze`)**: p50 = 170.28ms | p95 = 188.07ms
- **Advisory Vector Retrieval**: < 1ms in local memory mode; indexed sub-10ms in PostgreSQL HNSW.

---

## 11. Known Limitations & Cloud Boundaries

1. **Cloud Secrets Store**: Secrets management in this baseline relies on environment injection (`.env` or container orchestrator secrets). Integration with cloud vaults (AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault) remains an external infrastructure decision.
2. **Single-Node Rate Limiting**: The current rate limiter uses an in-memory sliding window per application instance. In horizontally-scaled multi-node deployments behind a load balancer, a centralized Redis or API Gateway rate limiter (e.g., Kong, Cloudflare, AWS WAF) is recommended.
3. **SSL/TLS Termination**: `docker-compose.prod.yml` serves HTTP internally. Production deployments must place Nginx behind a TLS termination proxy (AWS ALB, Cloudflare, Traefik, or Let's Encrypt certbot).
