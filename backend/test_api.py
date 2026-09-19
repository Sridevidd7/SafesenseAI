"""
test_api.py — Smoke tests for the upload endpoint.
Run with: python test_api.py
"""
import json
import urllib.request
import urllib.error

BASE = "http://localhost:8000/api"


def multipart_upload(url: str, filepath: str, field: str = "file") -> dict:
    """
    Upload a file using multipart/form-data via stdlib only (no requests lib).
    """
    boundary = "safesense_boundary_xyz"
    filename = filepath.split("\\")[-1].split("/")[-1]

    with open(filepath, "rb") as fh:
        file_bytes = fh.read()

    # Build multipart body manually
    part_header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        f"Content-Type: text/csv\r\n\r\n"
    ).encode("utf-8")

    part_footer = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = part_header + file_bytes + part_footer

    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def test_upload_valid_csv():
    print("\n=== TEST 1: Valid CSV upload ===")
    result = multipart_upload(
        url=f"{BASE}/reports/upload",
        filepath="test_upload.csv",
    )
    assert result["processed"] == 10, f"Expected 10, got {result['processed']}"
    assert result["skipped"] == 0
    assert result["total_rows"] == 10
    assert result["description_column"] == "description"
    assert len(result["sample"]) == 5
    assert "CRITICAL" in result["risk_summary"]
    assert result["sif_count"] >= 1

    print("  filename:          ", result["filename"])
    print("  total_rows:        ", result["total_rows"])
    print("  processed:         ", result["processed"])
    print("  skipped:           ", result["skipped"])
    print("  sif_count:         ", result["sif_count"])
    print("  risk_summary:      ", result["risk_summary"])
    print("  description_column:", result["description_column"])
    print("  sample:")
    for row in result["sample"]:
        print(
            f"    id={row['saved_id']} row={row['row_index']} "
            f"score={row['risk_score']} level={row['risk_level']} "
            f"sif={row['sif_potential']} category={row['category']}"
        )
    print("  PASS")


def test_upload_missing_column():
    print("\n=== TEST 2: CSV with wrong column name (no 'description') ===")
    # Write a temp CSV with a column the service won't recognise
    bad_csv = "wrong_column,severity\nsome text,High\n"
    with open("bad_columns.csv", "w") as fh:
        fh.write(bad_csv)
    try:
        multipart_upload(url=f"{BASE}/reports/upload", filepath="bad_columns.csv")
        print("  FAIL — should have raised 422")
    except urllib.error.HTTPError as exc:
        body = json.loads(exc.read())
        assert exc.code == 422
        assert "description" in body["detail"].lower()
        print("  Status:", exc.code)
        print("  Detail:", body["detail"][:120])
        print("  PASS")


def test_upload_empty_file():
    print("\n=== TEST 3: Empty CSV file ===")
    with open("empty.csv", "w") as fh:
        fh.write("description\n")   # header only, no data rows
    try:
        multipart_upload(url=f"{BASE}/reports/upload", filepath="empty.csv")
        print("  FAIL — should have raised 422")
    except urllib.error.HTTPError as exc:
        body = json.loads(exc.read())
        assert exc.code == 422
        print("  Status:", exc.code)
        print("  Detail:", body["detail"][:120])
        print("  PASS")


def test_upload_alias_column():
    print("\n=== TEST 4: CSV using alias column name 'report_text' ===")
    alias_csv = (
        "report_text,report_type\n"
        "Technician worked on live circuit without any isolation procedure,Unsafe Act\n"
        "Worker welding near fuel storage without hot work permit,Near Miss\n"
    )
    with open("alias_col.csv", "w") as fh:
        fh.write(alias_csv)
    result = multipart_upload(url=f"{BASE}/reports/upload", filepath="alias_col.csv")
    assert result["processed"] == 2
    assert result["description_column"] == "report_text"
    print("  processed:", result["processed"])
    print("  description_column:", result["description_column"])
    print("  sample:", [(r["category"], r["risk_score"]) for r in result["sample"]])
    print("  PASS")


def test_get_reports_after_upload():
    print("\n=== TEST 5: GET /api/reports returns persisted records ===")
    with urllib.request.urlopen(f"{BASE}/reports") as resp:
        data = json.loads(resp.read())
    print("  total persisted reports:", data["total"])
    assert data["total"] >= 10, "Expected at least 10 reports after uploads"
    print("  most recent:", data["reports"][0]["category"], data["reports"][0]["risk_score"])
    print("  PASS")


if __name__ == "__main__":
    test_upload_valid_csv()
    test_upload_missing_column()
    test_upload_empty_file()
    test_upload_alias_column()
    test_get_reports_after_upload()
    print("\n=== ALL TESTS PASSED ===")
