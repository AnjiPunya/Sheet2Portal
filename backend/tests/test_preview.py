def test_get_workbook_roundtrip(client, multi_sheet_xlsx):
    with open(multi_sheet_xlsx, "rb") as f:
        upload = client.post(
            "/api/workbooks",
            files={"file": ("workbook.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    workbook_id = upload.json()["id"]

    response = client.get(f"/api/workbooks/{workbook_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["original_filename"] == "workbook.xlsx"
    assert len(body["worksheets"]) == 2
    projects = body["worksheets"][0]
    assert projects["sample_rows"][0]["Project"] == "Website Revamp"
    assert {c["name"] for c in projects["columns"]} == {"Project", "Budget", "Spent", "Start Date"}


def test_get_unknown_workbook_returns_404(client):
    import uuid

    response = client.get(f"/api/workbooks/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"]["error_code"] == "NOT_FOUND"
