# SafeSense AI — Industrial Safety Intelligence Platform

> **"Turning Safety Reports into Preventive Action"**

[![Phase 7: Production Security & Deployment](https://img.shields.io/badge/Phase%207-Deployment%20Baseline-brightgreen)](#14-phase-7--production-security--deployment-baseline)
[![Architecture: Hybrid Deterministic/Advisory](https://img.shields.io/badge/Architecture-Deterministic%20Authoritative-blue)](#4-safety-decision-architecture)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](#license)

SafeSense AI is an industrial safety intelligence platform designed to analyze written safety reports, extract safety concepts, detect Serious Injury or Fatality (SIF) precursors, compute transparent risk scores, map Life-Saving Rules (LSR), identify safety barrier failures, discover recurring cross-site patterns, and provide grounded AI assistant queries with verifiable citations.

> [!WARNING]
> **Decision-Support Notice**: Risk scores, SIF precursor detections, and Copilot syntheses produced by SafeSense AI are prototype decision-support outputs. They do **not** replace professional engineering judgment. Authorized, qualified Health, Safety, and Environment (HSE) personnel remain solely responsible for all final safety determinations and corrective actions.

---

## Table of Contents

- [1. Project Overview](#1-project-overview)
- [2. Core Capabilities](#2-core-capabilities)
- [3. Architecture](#3-architecture)
- [4. Safety Decision Architecture](#4-safety-decision-architecture)
- [5. Technology Stack](#5-technology-stack)
- [6. Project Structure](#6-project-structure)
- [7. Phase History](#7-phase-history)
- [8. Database Architecture](#8-database-architecture)
- [9. Local Development Setup](#9-local-development-setup)
- [10. Testing](#10-testing)
- [11. Git / Team Workflow](#11-git--team-workflow)
- [12. Important Safety Boundaries](#12-important-safety-boundaries)
- [13. Known Limitations / Current State](#13-known-limitations--current-state)
- [14. Phase 7 — Production Security & Deployment Baseline](#14-phase-7--production-security--deployment-baseline)
- [15. Operational Runbooks](#15-operational-runbooks)
- [16. Handoff Notes](#16-handoff-notes)

---

## 1. Project Overview

Industrial facilities generate hundreds of near-miss reports, hazard observations, and incident logs daily. Critical pre-incident signals (such as compromised barriers, temporal precursor exposures, and repeat hazard interactions) often stay buried in narrative text until a serious event occurs.

SafeSense AI provides an automated, transparent pipeline that:
- **Analyzes Safety Reports**: Ingests unstructured incident and observation narratives via CSV, Excel, or REST API.
- **Detects SIF Precursors**: Evaluates high-energy hazards and control degradation to flag Serious Injury or Fatality potential (`YES`, `NO`, or `UNKNOWN`).
- **Computes Explainable Risk Scores**: Generates a 0–100 risk score broken down by severity, exposure frequency, and control effectiveness.
- **Identifies Barrier Failures**: Maps findings to physical, administrative, and procedural barrier degradation.
- **Maps Life-Saving Rules**: Classifies reports against standard industrial Life-Saving Rules (e.g., Working at Height, Confined Space, Energy Isolation).
- **Discovers Recurring Patterns**: Clusters multi-incident signals by site, unit, and hazard category to catch systemic risks before escalation.
- **Powers a Grounded Safety Copilot**: Synthesizes cross-report insights with strict attribution to verified report IDs and deterministic evidence.
- **Provides an Advisory Semantic Layer**: Leverages TF-IDF candidate retrieval and pgvector-ready vector storage to support discovery without compromising safety authority.
- **Operates on a Dual-Database Model**: Uses lightweight SQLite for zero-setup local development and a PostgreSQL + pgvector production-target architecture.

---

## 2. Core Capabilities

The capabilities listed below are fully implemented and verified in the current repository:

| Capability | Module / Layer | Description |
|---|---|---|
| **Deterministic NLP & Concept Extraction** | `concept_extractor.py` | Tokenizes narratives, detects safety concepts, extracts equipment/activity entities, and identifies pre-exposure conditions without relying on non-deterministic LLMs. |
| **Deterministic SIF & Risk Scoring** | `risk_engine.py` | Computes 0–100 risk scores and classifies SIF potential (`YES`, `NO`, `UNKNOWN`) using auditable, calibrated decision trees and rule weights. |
| **Barrier Failure Detection** | `barrier_dictionary.py` | Detects physical, administrative, and procedural barrier degradation using explicit keyword matrices and negation-aware context matching. |
| **Temporal & Pre-Exposure Handling** | `risk_engine.py` | Distinguishes between active exposures, safe pre-job observations, and mitigated near-misses to avoid false-positive risk inflation. |
| **Life-Saving Rule Classification** | `rule_classifier.py` | Maps incident text to industry Life-Saving Rules (Bypass Controls, Confined Space, Driving, Energy Isolation, Fall Protection, etc.). |
| **Pattern Intelligence & Anomalies** | `pattern_engine.py` | Discovers repeat failure clusters across sites and equipment units, tracking emerging trends and precursor concentrations. |
| **Grounded Safety Copilot** | `copilot_service.py` | LLM-assisted conversational interface (powered by Groq with `openai/gpt-oss-120b`) that synthesizes answers strictly from verified report citations and deterministic metrics. |
| **Structured Explainability** | `analysis_utils.py` | Returns exact matched keywords, rule triggers, barrier states, and contributing score factors for every report. |
| **Advisory Semantic Candidates** | `semantic_service.py` | TF-IDF concept bank generating semantic similarity candidates without model weights or network dependencies. |
| **Deterministic Validation Gate** | `pattern_adapter.py` | Validates and constrains any ML-suggested candidates against deterministic barrier and rule dictionaries before presentation. |
| **PostgreSQL + pgvector Infrastructure** | `vector_store.py` | Provides vector storage schema, cosine distance search, and filtering over report embeddings for PostgreSQL. |
| **SQLite → PostgreSQL Migration Tooling** | `migrate_sqlite_to_postgres.py` | Automated, idempotent migration script with row-count, content-hash, foreign-key, and SIF-semantic integrity verification. |
| **Executive & Operational UI** | `frontend/src/pages/` | Modern React dashboard featuring KPI cards, hazard heatmaps, action tracking, site comparisons, report detail views, and Copilot chat. |

---

## 3. Architecture

```mermaid
flowchart TD
    subgraph Client["Client Layer"]
        UI["React 18 + Vite Frontend\n(Tailwind CSS, Recharts, Framer Motion)"]
    end

    subgraph API["API Gateway"]
        FastAPI["FastAPI Backend (/api)\n(CORS, PII Redaction, Input Validation)"]
    end

    subgraph Deterministic["Authoritative Safety Layer (Deterministic)"]
        RiskEng["Risk Engine\n(0-100 Score, SIF: YES/NO/UNKNOWN)"]
        RuleClass["Rule Classifier\n(Life-Saving Rules)"]
        ConceptExt["Concept Extractor\n(Hazards, Entities, Pre-Exposure)"]
        BarrierDict["Barrier Dictionary\n(Physical / Admin / Procedural Controls)"]
        PatternEng["Pattern Intelligence Engine\n(Cross-Site Clustering & Anomaly Detection)"]
    end

    subgraph Advisory["Advisory Infrastructure (Non-Authoritative)"]
        Semantic["TF-IDF Semantic Service\n(Advisory Concept Candidates)"]
        ValidationGate["Validation Gate\n(Filters ML proposals against dictionary)"]
        VectorStore["Vector Store Abstraction\n(pgvector Cosine Search)"]
        Copilot["Safety Copilot Service\n(Groq LLM Synthesis with Grounded Citations)"]
    end

    subgraph Storage["Storage Layer"]
        DBConfig["Database Switch (DATABASE_URL)"]
        SQLite["SQLite (Local/Demo)\n(backend/safety.db)"]
        Postgres["PostgreSQL 16 + pgvector (Production Target)\n(Docker / Dedicated Instance)"]
        Alembic["Alembic Migrations\n(Schema Versioning: Head 8124b0c262db)"]
    end

    UI <-->|HTTP REST / JSON| FastAPI
    FastAPI --> Deterministic
    Deterministic -->|Authoritative Results| FastAPI
    Deterministic -->|Authoritative Context| Copilot
    FastAPI --> Advisory
    Semantic --> ValidationGate
    ValidationGate -->|Validated Candidates| FastAPI
    VectorStore -.->|Advisory Retrieval| Copilot
    FastAPI --> DBConfig
    DBConfig -->|Default| SQLite
    DBConfig -->|Configured| Postgres
    Alembic --> Postgres
```

### The Authority Boundary
- **Deterministic safety logic is authoritative**: Risk scores, SIF flags, Life-Saving Rules, barrier statuses, and temporal classifications are calculated strictly by deterministic Python rules.
- **ML semantic suggestions and vector retrieval are advisory**: Vector distance and TF-IDF similarity assist with fuzzy discovery and search, but cannot alter a report's risk level or SIF classification.
- **LLMs must not directly determine authoritative outcomes**: The Safety Copilot synthesizes explanations and answers queries using deterministic metrics as ground truth. LLMs never assign risk scores or alter database records.

---

## 4. Safety Decision Architecture

The platform strictly separates authoritative safety computation from advisory AI capabilities.

### Authoritative Deterministic Layer
The following five modules are safety-authoritative and must remain deterministic, fully explainable, and regression-tested:
- `backend/services/risk_engine.py`: Core risk scoring (0–100), SIF potential logic (`YES`, `NO`, `UNKNOWN`), and severity weights.
- `backend/services/rule_classifier.py`: Life-Saving Rule detection using curated terminology and priority scoring.
- `backend/services/concept_extractor.py`: Grammar-based concept parsing, equipment detection, and pre-exposure logic.
- `backend/services/barrier_dictionary.py`: Safety control definitions, failure patterns, and negation rules.
- `backend/services/pattern_engine.py`: Statistical clustering, recurrence algorithms, and rate-of-change metrics.

### Advisory Layer
- `backend/services/semantic_service.py`: Generates TF-IDF concept candidates across narratives.
- `backend/services/pattern_adapter.py`: Passes advisory candidates through a deterministic validation gate to ensure adherence to safety ontology.
- `backend/services/vector_store.py`: Performs cosine distance queries against `report_embeddings` (pgvector).
- `backend/services/copilot_service.py`: Generates grounded summaries and recommendations referencing specific report IDs.

---

## 5. Technology Stack

### Frontend (from `frontend/package.json`)
- **Framework**: `react` (^18.2.0), `react-dom` (^18.2.0) with TypeScript (^5.2.2)
- **Bundler & Tooling**: `vite` (^5.0.8)
- **Styling**: `tailwindcss` (^3.3.6), `postcss` (^8.4.32), `autoprefixer` (^10.4.16)
- **Visualizations**: `recharts` (^2.10.3), `lucide-react` (^0.294.0), `framer-motion` (^10.16.16)
- **Data Parsing**: `papaparse` (^5.4.1), `xlsx` (^0.18.5)
- **Routing & Networking**: `react-router-dom` (^6.20.0), `axios` (^1.6.2)

### Backend (from `backend/requirements.txt`)
- **Framework**: `fastapi` (==0.104.1), `uvicorn[standard]` (==0.24.0)
- **Data & Validation**: `pydantic` (==2.5.0), `sqlalchemy` (==2.0.23)
- **Database Drivers & Migrations**: `alembic` (>=1.12), `psycopg[binary]` (>=3.1), built-in `sqlite3`
- **Numerical & ML**: `numpy` (==1.26.2), `pandas` (==2.1.3), `scikit-learn` (==1.3.2) (powers TF-IDF semantic layer)
- **Security & Utilities**: `python-jose[cryptography]` (==3.3.0), `passlib[bcrypt]` (==1.7.4), `python-dotenv` (==1.0.0), `aiofiles` (==23.2.1), `openpyxl` (==3.1.2)
- **Multilingual Support**: `langdetect` (==1.0.9), `deep-translator` (==1.11.4)
- **Copilot LLM Provider**: `groq` (>=0.9.0) using model `openai/gpt-oss-120b`

### Infrastructure & Database
- **SQLite**: Local development and zero-configuration demonstration (`backend/safety.db`)
- **PostgreSQL**: PostgreSQL 16 with pgvector 0.8.6 extension via Docker (`pgvector/pgvector:pg16`)
- **Containerization**: Docker, Docker Compose

---

## 6. Project Structure

```text
SafesenseAI/
├── backend/
│   ├── alembic/                      # Alembic migration environment
│   │   ├── versions/                 # Version scripts (52f4c7b68fb8, e5d4d8238ea9, 8124b0c262db)
│   │   └── env.py                    # Migration runner configured for PostgreSQL/SQLite
│   ├── routes/                       # FastAPI route controllers
│   │   ├── actions.py                # Action item creation, tracking, and close-out
│   │   ├── admin.py                  # Database info, vector status, and administrative endpoints
│   │   ├── copilot.py                # Grounded Copilot chat endpoint
│   │   ├── dashboard.py              # KPI aggregation, site metrics, risk distribution
│   │   ├── reports.py                # Report submission, listing, filtering, and export
│   │   ├── reviews.py                # HSE human-in-the-loop review workflow
│   │   └── semantic.py               # Advisory semantic candidate endpoints
│   ├── services/                     # Business logic and safety engines
│   │   ├── barrier_dictionary.py     # [AUTHORITATIVE] Safety control & barrier failure definitions
│   │   ├── concept_extractor.py      # [AUTHORITATIVE] NLP hazard & entity concept extraction
│   │   ├── pattern_engine.py         # [AUTHORITATIVE] Cross-site pattern & anomaly detection
│   │   ├── risk_engine.py            # [AUTHORITATIVE] Deterministic 0-100 risk scoring & SIF logic
│   │   ├── rule_classifier.py        # [AUTHORITATIVE] Life-Saving Rule classification
│   │   ├── copilot_service.py        # Safety Copilot synthesis & prompt construction
│   │   ├── embedding_provider.py     # Production HTTP provider & embedding abstractions
│   │   ├── pii_service.py            # Automatic detection and masking of names/phones/emails
│   │   ├── semantic_service.py       # Advisory TF-IDF semantic concept bank
│   │   └── vector_store.py           # pgvector similarity search & embedding storage
│   ├── config.py                     # Centralized settings & fail-fast production validation
│   ├── database.py                   # Engine configuration, connection pooling, and DB switch
│   ├── middleware.py                 # Security headers, rate limiting, and request ID tracing
│   ├── models.py                     # SQLAlchemy ORM models (Report, Action, Review, etc.)
│   ├── schemas.py                    # Pydantic input/output validation schemas
│   ├── utils/logging_config.py       # Structured JSON logging & credential scrubbing
│   ├── Dockerfile.prod               # Hardened multi-stage backend container (non-root)
│   ├── requirements.txt              # Python backend dependencies
│   └── test_*.py                     # Test suites (unit, regression, schema, vector, security)
├── frontend/
│   ├── src/
│   │   ├── components/               # Reusable UI widgets, cards, tables, badges
│   │   ├── context/                  # AppContext (global reports, filters, auth)
│   │   ├── data/                     # Synthetic demo dataset (250+ incidents)
│   │   ├── pages/                    # 14 application views (Dashboard, Copilot, Upload, etc.)
│   │   ├── types/                    # TypeScript interfaces for reports, actions, patterns
│   │   └── utils/                    # Client-side analytics, CSV formatting, color scales
│   ├── Dockerfile.prod               # Production multi-stage frontend container (Nginx)
│   ├── nginx.conf                    # Hardened Nginx reverse proxy configuration
│   ├── package.json                  # Node dependencies & build scripts
│   ├── tailwind.config.js            # Tailwind theme tokens and color palettes
│   └── vite.config.ts                # Vite build and proxy configuration
├── scripts/
│   ├── backup_postgres.py            # PostgreSQL logical backup/restore tool with SHA-256 checks
│   ├── migrate_sqlite_to_postgres.py # SQLite -> PostgreSQL migration with integrity verification
│   └── perf_baseline.py              # Performance & load benchmark baseline
├── docs/
│   ├── phase5-ml-semantic-layer.md   # Phase 5 architecture & benchmark documentation
│   ├── phase6-postgres-vector-architecture.md # Phase 6 database & vector documentation
│   └── phase7-production-security-deployment.md # Phase 7 security runbook & deployment guide
├── docker-compose.yml                # Development multi-container orchestration
├── docker-compose.prod.yml           # Production deployment stack (Postgres, Backend, Nginx Frontend)
└── README.md                         # Project documentation and onboarding guide
```

---

## 7. Phase History

| Phase | Title | Status | Description |
|---|---|:---:|---|
| **Phase 1** | NLP Robustness | ✅ COMPLETE | Deterministic concept extraction, negation handling, pre-exposure detection, and PII masking. |
| **Phase 2** | Pattern Intelligence | ✅ COMPLETE | Cross-site clustering, hazard recurrence algorithms, trend anomaly detection, and early warning indicators. |
| **Phase 3** | Grounded Safety Copilot | ✅ COMPLETE | Conversational HSE assistant backed by Groq (`openai/gpt-oss-120b`), enforcing citation grounding against verified report IDs. |
| **Phase 4** | Dashboard / UI | ✅ COMPLETE | Complete React 18 interface with 14 views, interactive risk matrix, site rankings, and human-in-the-loop reviews. |
| **Phase 5** | ML-Assisted Semantic Layer | ✅ COMPLETE | Advisory TF-IDF concept bank over curated safety dictionaries, constrained by a deterministic validation gate. |
| **Phase 6** | PostgreSQL / Vector Architecture | ✅ COMPLETE | Dual-database architecture, Alembic migrations, pgvector HNSW index schema, live SQLite → PostgreSQL migration, and schema hardening. |
| **Phase 7** | Production Security & Deployment | ✅ COMPLETE | Production configuration, bcrypt hashing & RBAC, security headers & rate limiting, fail-fast secrets, health/ready probes, PostgreSQL backup/restore tool, Docker production baseline, and performance benchmark. |

### Phase 7 Milestones Delivered
- **Centralized Configuration & Fail-Fast Validation**: Implemented `backend/config.py` enforcing production invariants (rejects weak/default secrets, default postgres passwords, wildcard CORS, and SQLite in production).
- **Hardened Authentication & RBAC**: Implemented bcrypt password hashing, UTC-based token lifecycle, and role-based access control (`services/auth.py`). Isolated local demo accounts behind `ALLOW_DEMO_AUTH`.
- **API Hardening & Abuse Protection**: Deployed `SecurityHeadersMiddleware` (X-Content-Type-Options, X-Frame-Options: DENY, X-XSS-Protection, HSTS) and IP sliding-window `RateLimiterMiddleware` (120 req/min general, 20 req/min sensitive).
- **Request Tracing & Observability**: Integrated `RequestIDMiddleware` (`X-Request-ID`), structured JSON logging, and automatic regex scrubbing of credentials, tokens, DB URLs, and sensitive PII (`utils/logging_config.py`).
- **Health & Readiness Probes**: Implemented `/api/health` (liveness) and `/api/ready` (validates live database connection ping and vector subsystem).
- **Upload Hardening**: Enforced 15 MB file size boundary (`HTTP 413`) and file extension whitelist (`.csv`, `.xlsx`, `.xls` only; `HTTP 422`).
- **Production Embedding Provider Interface**: Created `OpenAICompatibleEmbeddingProvider` supporting REST/HTTP endpoints with graceful fallback, preserving the strict advisory boundary.
- **Backup & Disaster Recovery Tooling**: Developed `scripts/backup_postgres.py` with gzip compression, foreign-key ordering, SHA-256 companion checksums, and dry-run restore validation.
- **Production Docker Baseline**: Created `backend/Dockerfile.prod` (non-root `safesense` user), `frontend/Dockerfile.prod` + `nginx.conf`, and `docker-compose.prod.yml` with health checks and volume persistence.
- **Performance Benchmark**: Benchmarked critical paths with `scripts/perf_baseline.py` (Report Analysis p50=59ms, Semantic Layer p50=170ms).
- **Security Regression Suite**: Added 26 automated unit & integration security tests in `backend/test_phase7_security.py`.

### Phase 6 Milestones Delivered
- **Configurable Persistence**: Configured `DATABASE_URL` supporting `postgresql+psycopg://` with automatic fallback to `sqlite:///backend/safety.db`.
- **Alembic Foundation**: Added linear migrations chain up to head `8124b0c262db`.
- **pgvector-Ready Architecture**: Designed `report_embeddings` schema featuring composite primary keys (`report_id`, `model_id`), 768-dimension vector support, and HNSW cosine index. *(Note: vector schema and retrieval abstractions exist; bulk embedding population is deferred).*
- **Vector Store Abstraction**: Implemented `VectorStore` class supporting cosine similarity retrieval, site/category filtering, and SQLite in-memory fallback.
- **Docker PostgreSQL Setup**: Configured `pgvector/pgvector:pg16` service in `docker-compose.yml` under the `postgres` profile.
- **Automated Migration Tooling**: Built `scripts/migrate_sqlite_to_postgres.py` with dry-run planning and table inspection for legacy schemas.
- **Verified Live Migration**:
  - Migrated **78 reports** and **3 uploaded files** from SQLite to PostgreSQL with 0 orphaned child rows.
  - Achieved **78/78 report ID parity** and **78/78 content hash parity**.
  - Verified exact preservation of safety semantics (`sif_potential`: 39 UNKNOWN, 33 YES, 6 NO).
  - Confirmed migration idempotency (second run exited 0, skipping all existing records).
- **SIF Potential Schema Hardening**: Widened `reports.sif_potential` to `VARCHAR(10)` to accommodate legitimate `UNKNOWN` risk classifications, protected by a guarded downgrade check.

---

## 8. Database Architecture

SafeSense AI supports both SQLite and PostgreSQL through SQLAlchemy 2.0:

- **SQLite (Development / Demonstration)**:
  - Default database when `DATABASE_URL` is omitted or empty.
  - Located at `backend/safety.db`.
  - Schema is bootstrapped automatically at startup with built-in demo data seeding.
- **PostgreSQL 16 + pgvector (Production Target)**:
  - Selected by setting `DATABASE_URL=postgresql+psycopg://user:password@host:port/dbname`.
  - Schema is managed strictly through Alembic revisions (currently at head `8124b0c262db`).
  - Includes pgvector extension for advisory cosine similarity search on `report_embeddings`.
  - **Infrastructure Status**: PostgreSQL + pgvector infrastructure validated locally; production deployment remains Phase 7 work. Phase 6 verified the PostgreSQL schema, pgvector extension/index architecture, vector store abstractions, SQLite → PostgreSQL migration, migration integrity, and idempotency. Production-scale embedding generation, load testing, operational infrastructure, and deployment are not yet completed.

### Alembic Migration Commands
Run all Alembic commands from the `backend/` directory:

```bash
cd backend

# View current database revision
alembic current

# Upgrade database to latest revision (head)
alembic upgrade head

# Check for schema drift against models.py
alembic check
```

### Data Migration Tooling
To migrate existing SQLite data into PostgreSQL:

```bash
# 1. Preview the migration plan without modifying target data
python scripts/migrate_sqlite_to_postgres.py --dry-run

# 2. Execute the live migration (requires DATABASE_URL pointing to PostgreSQL)
python scripts/migrate_sqlite_to_postgres.py

# 3. Specify a custom source database path if needed
python scripts/migrate_sqlite_to_postgres.py --source path/to/source.db
```

The migration preserves original IDs, content hashes, creation timestamps, and foreign key integrity. It safely skips already migrated records and verifies counts upon completion.

---

## 9. Local Development Setup

### Prerequisites
- **Node.js**: v18.0.0 or higher
- **npm**: v9.0.0 or higher
- **Python**: v3.10, v3.11, or v3.12
- **Docker**: (Optional) For running PostgreSQL + pgvector locally

### 1. Clone the Repository
```bash
git clone https://github.com/Sridevidd7/SafesenseAI.git
cd SafesenseAI
```

### 2. Backend Setup
```bash
cd backend

# Create and activate virtual environment (Windows PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
```

Edit `backend/.env` as needed:
- For SQLite local development: leave `DATABASE_URL` commented or empty.
- For Groq Copilot features: set `GROQ_API_KEY=your_key_here` and `GROQ_MODEL=openai/gpt-oss-120b`.

Start the FastAPI development server:
```bash
uvicorn main:app --reload --port 8000
```
- API Base: `http://localhost:8000`
- Swagger UI Documentation: `http://localhost:8000/api/docs`

### 3. Frontend Setup
Open a second terminal:
```bash
cd frontend

# Install Node dependencies
npm install

# Start Vite development server
npm run dev
```
Open **http://localhost:3000** in your browser.

### 4. Optional: Run PostgreSQL + pgvector via Docker
To run with PostgreSQL instead of SQLite:

```bash
# Start PostgreSQL container in background
docker compose --profile postgres up -d postgres

# Configure DATABASE_URL in backend/.env:
# DATABASE_URL=postgresql+psycopg://safesense:safesense@localhost:5432/safesense

# Run Alembic migrations to build PostgreSQL schema
cd backend
alembic upgrade head

# (Optional) Migrate SQLite seed data to PostgreSQL
python ../scripts/migrate_sqlite_to_postgres.py
```

### Demo Accounts
The frontend includes built-in authentication for local exploration:

> [!CAUTION]
> **DEMO-ONLY CREDENTIALS**: These credentials are for local/demo use only and MUST NOT be used in production. The accounts below are hardcoded for local evaluation and UI testing only.

| Role | Email | Password | Purpose |
|---|---|---|---|
| **Administrator** | `admin@safesense.ai` | `admin123` | Local UI testing & admin view |
| **HSE Officer** | `hse@safesense.ai` | `hse123` | Local UI testing & review flow |
| **Safety Manager** | `manager@safesense.ai` | `mgr123` | Local UI testing & pattern metrics |
| **Site Manager** | `site@safesense.ai` | `site123` | Local UI testing & site filters |

---

## 10. Testing

### Backend Test Suite
The backend contains 260+ tests covering deterministic safety engines, regression suites, schema widening, migration scripts, and vector storage.

```bash
cd backend

# Run the complete test suite
pytest -q
```

#### Test Suite Structure:
- **Unit & Safety Regression Tests**: Fast, in-memory tests verifying deterministic scoring, concept extraction, barrier logic, and PII masking. Run automatically without network or server dependencies.
- **Live Server Smoke Tests (`test_api.py`)**: End-to-end HTTP tests querying `http://localhost:8000/api`. These tests require a running backend server process (`uvicorn main:app --port 8000`); they will raise connection errors if the server is offline.
- **PostgreSQL Integration Tests (`test_batch3_migration_vector.py`)**: Dedicated PostgreSQL tests that run when `TEST_DATABASE_URL` is set in the environment, and automatically skip when unset.

### Frontend Production Build
To validate TypeScript types and build the production bundle:

```bash
cd frontend
npm run build
```
This runs `tsc && vite build`, creating optimized assets in `frontend/dist/`.

---

## 11. Git / Team Workflow

- **Authoritative Branch**: `main` is the authoritative integration branch. Feature work should be conducted on dedicated feature branches and merged into `main` via reviewed pull requests. (Phase 7 production hardening has not started).
- **Current HEAD**: `3369fb3 Harden PostgreSQL migration compatibility`.
- **Branch Naming**: Use descriptive prefixes: `feature/<name>`, `fix/<name>`, `phase-<num>-<name>`.
- **Pre-PR Quality Checklist**:
  1. Run `git diff --check` to ensure no whitespace or formatting errors.
  2. Run `pytest -q` in `backend/` to verify safety regressions pass.
  3. Run `npm run build` in `frontend/` to confirm zero TypeScript compilation errors.
- **Strictly Ignored Files**:
  - Never commit `backend/.env` or any file containing API keys or database passwords.
  - Never commit local database files (`*.db`, `*.sqlite`, `backend/safety.db`).
  - Never commit `frontend/dist/` build output.
  - Exclude temporary local directories (`.freebuff/`, `..SafesenseAI-phase3/`).
- **Safety-Authoritative Review**: Any modification to the five authoritative safety modules ([Section 4](#4-safety-decision-architecture)) requires explicit HSE peer review and regression verification.

---

## 12. Important Safety Boundaries

> [!CAUTION]
> ### Critical Engineering Constraints
> 1. **No LLM Risk Authority**: Large Language Models must **never** be given authority to assign risk scores, override SIF potential, or resolve barrier statuses. LLMs are restricted to explanation and synthesis.
> 2. **Semantic Similarity Is Not Causality**: TF-IDF semantic candidates and vector cosine similarity are advisory heuristics. They do not constitute evidence of a safety condition without deterministic validation.
> 3. **PII Masking Is Mandatory**: Incident narratives must pass through `pii_service.py` before display or storage to ensure names, phone numbers, and employee identifiers are redacted.
> 4. **Deterministic Reproducibility**: The exact same narrative input must always yield the exact same risk score and SIF determination across runs.
> 5. **Human Accountability**: SafeSense AI does not replace certified safety engineers. Final risk management decisions rest with qualified HSE professionals.

---

## 13. Known Limitations / Current State

- **Advisory Vector & Embeddings State**:
  - `report_embeddings` schema exists with composite primary keys (`report_id`, `model_id`) and 768-dimension vector column.
  - Production `OpenAICompatibleEmbeddingProvider` supports external embedding gateways, with graceful fallback to `UnavailableEmbeddingProvider`.
  - Vector similarity search is validated and functional; embeddings remain strictly advisory and never participate in authoritative safety logic.
- **PostgreSQL Workload Verification**: PostgreSQL + pgvector infrastructure has been validated locally and in Docker orchestration; enterprise high-availability clusters and cloud managed services (AWS RDS/Aurora, GCP Cloud SQL) require platform-specific provisioning.
- **Single-Node Rate Limiter**: The sliding-window rate limiter currently tracks client IP state in memory; multi-node scaled deployments should front the application with Redis or an API Gateway (Kong, Cloudflare, AWS WAF).
- **Synthetic Demonstration Data**: Default incident records are synthetically generated for demonstration and do not reflect proprietary data from any actual operating facility.

---

## 14. Phase 7 — Production Security & Deployment Baseline

> [!NOTE]
> **Status: ✅ COMPLETE** — Phase 7 security hardening, secrets management, deployment orchestration, health probes, backup tooling, and observability baseline are fully implemented and verified. For detailed architecture specifications, see [docs/phase7-production-security-deployment.md](docs/phase7-production-security-deployment.md).

### 1. Hardened Production Configuration
- **Fail-Fast Secrets Check**: `backend/config.py` validates `JWT_SECRET_KEY` (min 32 chars, non-default), `DATABASE_URL` (PostgreSQL required; SQLite rejected in production), dedicated DB credentials (rejects `safesense:safesense`), and forbids wildcard CORS (`*`).
- **Demo Mode Isolation**: Pre-configured demo accounts (`admin@safesense.ai`, etc.) are isolated behind `ALLOW_DEMO_AUTH`. In production (`SAFESENSE_ENV=production`), demo authentication is rejected with `HTTP 403 Forbidden` by default.

### 2. Authentication & Authorization (RBAC)
- **Bcrypt Password Hashing**: Passwords verified via direct `bcrypt` hashing with constant-time verification (`services/auth.py`).
- **Role-Based Access Control**: FastAPI dependency `require_role(["Administrator"])` protects sensitive operations (e.g. database maintenance).

### 3. API Security & Abuse Protection
- **Security Headers**: `SecurityHeadersMiddleware` injects `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection`, `Referrer-Policy`, and HSTS.
- **Rate Limiting**: `RateLimiterMiddleware` enforces sliding-window limits (120 req/min general, 20 req/min sensitive like login/copilot), exempting health probes.
- **Upload Validation**: Enforces 15 MB payload ceiling (`HTTP 413`) and whitelists file extensions (`.csv`, `.xlsx`, `.xls` only; `HTTP 422`).
- **Global Error Sanitization**: Unhandled 500 exceptions return sanitized JSON with `request_id` in production, preventing stack trace or SQL query leakage.

### 4. Health, Readiness & Observability
- **Liveness (`/api/health`)**: Lightweight probe verifying web service responsiveness.
- **Readiness (`/api/ready`)**: Active probe checking database connectivity (`ping_database()`) and vector subsystem state.
- **Structured JSON Logging**: Single-line JSON logging in production with automated regex scrubbing of JWTs, passwords, DB connection strings, SSNs, and credit cards (`utils/logging_config.py`).
- **Request Tracing**: `RequestIDMiddleware` generates and propagates `X-Request-ID` across inbound requests, responses, and log records.

### 5. Production Embedding Pipeline Interface
- **OpenAI-Compatible Provider**: `OpenAICompatibleEmbeddingProvider` in `services/embedding_provider.py` connects to standard HTTP/REST embedding endpoints (OpenAI, Azure, vLLM, Ollama) with configurable dimensions (default 768) and timeouts.
- **Safety Boundary Preserved**: Retrieval remains strictly advisory; failures degrade gracefully without affecting deterministic safety engines.

---

## 15. Operational Runbooks

### 1. Database Backup & Restore (`scripts/backup_postgres.py`)
- **Backup**: Exports PostgreSQL tables in FK order into a gzip-compressed JSON archive with companion SHA-256 checksum:
  ```bash
  python scripts/backup_postgres.py --backup --output-dir /var/backups/safesense
  ```
- **Integrity Verification**:
  ```bash
  python scripts/backup_postgres.py --verify-archive /var/backups/safesense/safesense_backup_YYYYMMDD_HHMMSSZ.json.gz
  ```
- **Restore (Dry-Run)**:
  ```bash
  python scripts/backup_postgres.py --restore /var/backups/safesense/safesense_backup_YYYYMMDD_HHMMSSZ.json.gz
  ```
- **Restore (Live)**:
  ```bash
  python scripts/backup_postgres.py --restore /var/backups/safesense/safesense_backup_YYYYMMDD_HHMMSSZ.json.gz --no-dry-run
  ```

### 2. Production Deployment via Docker (`docker-compose.prod.yml`)
- Launch full production stack (PostgreSQL with pgvector, backend running as non-root user, frontend served by Nginx):
  ```bash
  export POSTGRES_PASSWORD="YourSecureClusterPassword123!"
  export JWT_SECRET_KEY="YourSecureEntropyKeyAtLeast32CharsLong!"
  export SAFESENSE_ENV="production"
  docker compose -f docker-compose.prod.yml up --build -d
  ```

### 3. Applying Database Migrations in Production
```bash
python scripts/backup_postgres.py --backup
python -m alembic current
python -m alembic upgrade head
curl -f http://localhost:8000/api/ready
```

### 4. Running Performance Baseline
```bash
python scripts/perf_baseline.py
```

---

## 16. Handoff Notes

> **Notice to Incoming Engineers:**
> *"If you are taking over this project, start by reading this README, then inspect the latest `main` branch and the phase history before changing architecture."*

To get started effectively:
1. **Start from `main`**: Ensure your local branch is synchronized with `origin/main`.
2. **Read the Safety Boundaries**: Review [Section 4](#4-safety-decision-architecture) and [Section 12](#12-important-safety-boundaries) before writing code. Deterministic safety modules have strict regression requirements.
3. **Run the Application Locally**: Follow [Section 9](#9-local-development-setup) to start both the FastAPI backend and React frontend.
4. **Run the Test Suite**: Run `pytest -q` in `backend/` and `npm run build` in `frontend/` to confirm your local environment matches the baseline.
5. **Inspect PostgreSQL Configuration**: Inspect `docker-compose.prod.yml`, `backend/alembic/`, `backend/config.py`, and `backend/services/vector_store.py`.
6. **Do Not Touch Authoritative Safety Modules**: Avoid editing `risk_engine.py`, `rule_classifier.py`, `concept_extractor.py`, `barrier_dictionary.py`, or `pattern_engine.py` without explicit guidance and new regression tests.
7. **Rely on Documented Truth**: Treat this README, `docs/phase7-production-security-deployment.md`, and the code in `main` as the source of truth.

---

## License

MIT License — Distributed for demonstration, research, and educational purposes. See license file for details.

*SafeSense AI — Enterprise Safety Intelligence Platform*  
*AI assists HSE decision-making. Final safety authority remains with qualified personnel.*
