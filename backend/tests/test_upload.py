def test_upload_multi_sheet_xlsx(client, multi_sheet_xlsx):
    with open(multi_sheet_xlsx, "rb") as f:
        response = client.post(
            "/api/workbooks",
            files={"file": ("workbook.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ready"
    assert [s["name"] for s in body["worksheets"]] == ["Projects", "Tasks"]
    assert body["worksheets"][0]["row_count"] == 2
    assert body["worksheets"][0]["columns"][1]["inferred_type"] == "int"


def test_upload_csv(client, simple_csv):
    with open(simple_csv, "rb") as f:
        response = client.post("/api/workbooks", files={"file": ("data.csv", f, "text/csv")})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ready"
    assert body["worksheets"][0]["row_count"] == 2


def test_upload_rejects_unsupported_extension(client, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hello")
    with open(path, "rb") as f:
        response = client.post("/api/workbooks", files={"file": ("notes.txt", f, "text/plain")})
    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "UNSUPPORTED_FILE_TYPE"


def test_upload_rejects_oversized_file(client, tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_upload_size_bytes", 10)
    path = tmp_path / "big.csv"
    path.write_text("Name,Age\n" + "\n".join(f"row{i},{i}" for i in range(50)))
    with open(path, "rb") as f:
        response = client.post("/api/workbooks", files={"file": ("big.csv", f, "text/csv")})
    assert response.status_code == 413
    assert response.json()["detail"]["error_code"] == "FILE_TOO_LARGE"


def test_upload_rejects_empty_file(client, tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")
    with open(path, "rb") as f:
        response = client.post("/api/workbooks", files={"file": ("empty.csv", f, "text/csv")})
    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "EMPTY_WORKBOOK"


def test_upload_corrupt_xlsx_stores_error_status(client, tmp_path):
    path = tmp_path / "bad.xlsx"
    path.write_bytes(b"not a real xlsx file")
    with open(path, "rb") as f:
        response = client.post(
            "/api/workbooks",
            files={"file": ("bad.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "error"
    assert body["error_code"] == "CORRUPT_FILE"


def test_upload_is_isolated_per_tenant(client, simple_csv):
    with open(simple_csv, "rb") as f:
        upload = client.post(
            "/api/workbooks",
            files={"file": ("data.csv", f, "text/csv")},
            headers={"X-Tenant-Id": "tenant-a"},
        )
    workbook_id = upload.json()["id"]

    same_tenant = client.get(f"/api/workbooks/{workbook_id}", headers={"X-Tenant-Id": "tenant-a"})
    assert same_tenant.status_code == 200

    other_tenant = client.get(f"/api/workbooks/{workbook_id}", headers={"X-Tenant-Id": "tenant-b"})
    assert other_tenant.status_code == 404
