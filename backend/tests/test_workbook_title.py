def _upload(client, path, filename):
    with open(path, "rb") as f:
        return client.post("/api/workbooks", files={"file": (filename, f, "text/csv")})


def test_portal_title_defaults_to_generated_title_from_filename(client, simple_csv):
    upload = _upload(client, simple_csv, "sales_pipeline_q3.csv")
    workbook_id = upload.json()["id"]

    config = client.get(f"/api/workbooks/{workbook_id}/portal").json()
    assert config["title"] == "Sales Management Portal"


def test_workbook_response_includes_null_display_title_by_default(client, simple_csv):
    upload = _upload(client, simple_csv, "sales_pipeline_q3.csv")
    assert upload.json()["display_title"] is None


def test_patch_sets_custom_title_and_portal_config_reflects_it(client, simple_csv):
    upload = _upload(client, simple_csv, "sales_pipeline_q3.csv")
    workbook_id = upload.json()["id"]

    patched = client.patch(f"/api/workbooks/{workbook_id}", json={"title": "My Custom Portal Name"})
    assert patched.status_code == 200
    assert patched.json()["display_title"] == "My Custom Portal Name"

    config = client.get(f"/api/workbooks/{workbook_id}/portal").json()
    assert config["title"] == "My Custom Portal Name"


def test_patch_with_blank_title_resets_to_generated_default(client, simple_csv):
    upload = _upload(client, simple_csv, "sales_pipeline_q3.csv")
    workbook_id = upload.json()["id"]

    client.patch(f"/api/workbooks/{workbook_id}", json={"title": "Custom Name"})
    reset = client.patch(f"/api/workbooks/{workbook_id}", json={"title": "   "})
    assert reset.json()["display_title"] is None

    config = client.get(f"/api/workbooks/{workbook_id}/portal").json()
    assert config["title"] == "Sales Management Portal"


def test_patch_trims_whitespace_around_custom_title(client, simple_csv):
    upload = _upload(client, simple_csv, "sales_pipeline_q3.csv")
    workbook_id = upload.json()["id"]

    patched = client.patch(f"/api/workbooks/{workbook_id}", json={"title": "  Spaced Title  "})
    assert patched.json()["display_title"] == "Spaced Title"


def test_patch_unknown_workbook_404s(client):
    import uuid

    response = client.patch(f"/api/workbooks/{uuid.uuid4()}", json={"title": "x"})
    assert response.status_code == 404


def test_original_filename_preserved_through_custom_title_edit(client, simple_csv):
    upload = _upload(client, simple_csv, "sales_pipeline_q3.csv")
    workbook_id = upload.json()["id"]

    client.patch(f"/api/workbooks/{workbook_id}", json={"title": "Renamed Portal"})
    workbook = client.get(f"/api/workbooks/{workbook_id}").json()
    assert workbook["original_filename"] == "sales_pipeline_q3.csv"
    assert workbook["display_title"] == "Renamed Portal"
