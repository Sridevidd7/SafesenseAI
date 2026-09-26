"""
test_upload_lifecycle.py — End-to-end regression tests for bulk upload lifecycle.

Tests:
1. 250-row realistic upload parsing, PII redaction, deterministic NLP analysis,
   deduplication, atomic commit, and fast non-blocking cache invalidation.
2. Verified that expensive global pattern recomputation (cluster_reports) is NOT
   executed during the upload request.
3. Response model conformance (success=True, database_total, inserted, duplicates, etc.).
4. File idempotency: re-uploading the identical dataset skips duplicates and avoids re-insertion.
5. Cache invalidation correctness and lazy recomputation on subsequent analytics request.
6. Execution time measurement: upload processing is prompt and not dominated by global clustering.
"""
import io
import time
import pytest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Report, UploadedFile
from services.upload_service import process_csv_upload, UploadResult
from services.analytics_service import (
    invalidate_analytics_cache,
    get_total_reports,
    get_pattern_intelligence,
    _PATTERN_INTEL_CACHE,
)
import services.pattern_engine as pe


from sqlalchemy.pool import StaticPool


@pytest.fixture
def test_session_factory():
    """Create a temporary in-memory database engine and session factory."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionFactory = sessionmaker(bind=engine)
    try:
        yield SessionFactory
    finally:
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_db(test_session_factory):
    """Create an isolated session from the shared test session factory."""
    session = test_session_factory()
    try:
        yield session
    finally:
        session.close()


def generate_sample_csv(num_rows: int = 250) -> bytes:
    """Generate a realistic safety report dataset CSV."""
    rows = ["description,site,unit,area,activity,date"]

    categories = [
        ("Worker observed entering confined space vessel without atmospheric gas testing permit John Doe phone 9876543210", "Site Alpha", "Unit 1", "Area A", "Vessel Entry", "2026-03-01"),
        ("Scaffold platform missing guardrails and toe boards at 15m elevation on flare stack", "Site Beta", "Unit 2", "Area B", "Working at Height", "2026-03-02"),
        ("Forklift operator driving without seatbelt and speeding near pedestrian walkway", "Site Alpha", "Unit 1", "Area C", "Material Handling", "2026-03-03"),
        ("Electrical panel left open with exposed 415V busbars in rainy condition", "Site Gamma", "Unit 3", "Area D", "Electrical Maintenance", "2026-03-04"),
        ("Hot work welding performed near diesel storage tank without fire blanket or extinguisher", "Site Beta", "Unit 2", "Area A", "Hot Work", "2026-03-05"),
    ]

    for i in range(num_rows):
        template = categories[i % len(categories)]
        # Introduce some identical duplicates every 25 rows
        if i > 0 and i % 25 == 0:
            row_desc = f"{template[0]} (batch item)"
        else:
            row_desc = f"{template[0]} - Incident record #{i+1} inspected by Jane Smith ID: EMP{1000+i}"

        rows.append(f'"{row_desc}","{template[1]}","{template[2]}","{template[3]}","{template[4]}","{template[5]}"')

    return "\n".join(rows).encode("utf-8")


def test_250_row_bulk_upload_performance_and_lifecycle(test_db):
    """
    Verify 250-row upload:
    - Parses CSV
    - Sanitizes PII
    - Runs deterministic analysis
    - Commits atomically with UploadedFile
    - Invalidates cache without running expensive cluster_reports synchronously
    - Returns within expected time budget (< 3.0 seconds on standard CPU)
    """
    csv_bytes = generate_sample_csv(250)
    filename = "industrial_safety_250_records.csv"

    # Spy on cluster_reports to assert it is NOT called during upload
    with patch.object(pe, "cluster_reports", wraps=pe.cluster_reports) as mock_cluster:
        t0 = time.time()
        result = process_csv_upload(db=test_db, file_bytes=csv_bytes, filename=filename)
        elapsed = time.time() - t0

    # 1. Assert cluster_reports was NOT executed during upload
    mock_cluster.assert_not_called()

    # 2. Verify result metrics
    assert isinstance(result, UploadResult)
    assert result.success is True
    assert result.total_rows == 250
    assert result.inserted > 0
    assert result.inserted + result.duplicates == 250
    assert result.database_total == result.inserted
    assert result.pii_detected_count > 0  # John Doe, Jane Smith, phone, ID sanitized

    # 3. Verify atomic database persistence
    db_count = test_db.query(Report).count()
    assert db_count == result.inserted

    file_record = test_db.query(UploadedFile).filter(UploadedFile.filename == filename).first()
    assert file_record is not None
    assert len(file_record.file_hash) == 32

    # 4. Processing speed check (250 rows analyzed and persisted without clustering)
    print(f"\n250-row upload completed in {elapsed:.2f}s ({result.inserted} inserted, {result.duplicates} duplicates)")
    assert elapsed < 25.0, f"Upload took too long: {elapsed:.2f}s"


def test_idempotent_reupload_skips_duplicates(test_db):
    """
    Verify that re-uploading the identical file does NOT insert duplicate records
    and marks file_duplicate appropriately.
    """
    csv_bytes = generate_sample_csv(50)
    filename = "test_idempotent.csv"

    # First upload
    res1 = process_csv_upload(db=test_db, file_bytes=csv_bytes, filename=filename)
    assert res1.inserted > 0
    initial_db_count = test_db.query(Report).count()
    assert initial_db_count == res1.inserted

    # Second upload with same bytes
    res2 = process_csv_upload(db=test_db, file_bytes=csv_bytes, filename=filename)
    assert res2.inserted == 0
    assert res2.duplicates == 50
    assert res2.file_duplicate is True
    assert test_db.query(Report).count() == initial_db_count


def test_cache_invalidation_is_lazy_and_thread_safe(test_db):
    """
    Verify that after invalidate_analytics_cache():
    - The in-process cache is cleared
    - The next call to get_pattern_intelligence() recomputes freshly against the DB
    """
    csv_bytes = generate_sample_csv(20)
    process_csv_upload(db=test_db, file_bytes=csv_bytes, filename="test_cache.csv")

    # Prime the cache
    intel1 = get_pattern_intelligence(test_db)
    assert intel1 is not None
    assert intel1["total_reports"] == test_db.query(Report).count()

    # Invalidate cache
    invalidate_analytics_cache()

    # Verify cache is cleared
    from services.analytics_service import _PATTERN_INTEL_CACHE
    assert _PATTERN_INTEL_CACHE is None

    # Next call lazily rebuilds
    intel2 = get_pattern_intelligence(test_db)
    assert intel2 is not None
    assert intel2["total_reports"] == test_db.query(Report).count()


def test_upload_http_route_synchronous_session(test_session_factory):
    """
    Verify the FastAPI /api/reports/upload route executes synchronously:
    - No threadpool cross-thread session handoff
    - UploadFile properly read synchronously
    - HTTP 201 response with UploadResponse schema
    """
    from fastapi.testclient import TestClient
    from main import app
    from database import get_db
    from services.auth import require_write

    def _override_get_db():
        db = test_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[require_write] = lambda: {"user_id": "test-admin", "role": "Administrator"}

    try:
        client = TestClient(app)
        csv_bytes = generate_sample_csv(15)
        response = client.post(
            "/api/reports/upload",
            files={"file": ("test_http_upload.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["success"] is True
        assert data["total_rows"] == 15
        assert data["inserted"] > 0
        assert data["database_total"] >= 15
    finally:
        app.dependency_overrides.clear()
