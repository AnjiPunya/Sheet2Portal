import io

import openpyxl
import pytest


@pytest.fixture
def related_workbook_xlsx(tmp_path):
    path = tmp_path / "portal.xlsx"
    wb = openpyxl.Workbook()

    projects = wb.active
    projects.title = "Projects"
    projects.append(["Project Name", "Status", "Budget", "Spent"])
    projects.append(["Alpha Tower", "In Progress", 100000, 40000])
    projects.append(["Beta Villas", "At Risk", 50000, 60000])

    tasks = wb.create_sheet("Tasks")
    tasks.append(["Task Name", "Project", "Status"])
    tasks.append(["Pour foundation", "Alpha Tower", "Open"])
    tasks.append(["Install facade", "Beta Villas", "Open"])
    tasks.append(["Final inspection", "Alpha Tower", "Done"])

    wb.save(path)
    return str(path)


def _upload(client, path, filename="portal.xlsx"):
    with open(path, "rb") as f:
        return client.post(
            "/api/workbooks",
            files={"file": (filename, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )


def test_portal_config_reflects_uploaded_data(client, related_workbook_xlsx):
    upload = _upload(client, related_workbook_xlsx)
    workbook_id = upload.json()["id"]

    response = client.get(f"/api/workbooks/{workbook_id}/portal")
    assert response.status_code == 200
    config = response.json()

    assert config["primary_entity"] == "Projects"
    entity_names = {e["worksheet"] for e in config["entities"]}
    assert entity_names == {"Projects", "Tasks"}

    rel = next(r for r in config["relationships"] if r["from_entity"] == "Tasks")
    assert rel["to_entity"] == "Projects"
    assert rel["confidence"] == "high"

    projects_entity = next(e for e in config["entities"] if e["worksheet"] == "Projects")
    kpi_labels = {k["label"] for k in projects_entity["kpis"]}
    assert "Budget Used" in kpi_labels
    over_budget = next(k for k in projects_entity["kpis"] if "Over Budget" in k["label"])
    assert over_budget["value"] == 1


def test_changing_the_workbook_changes_the_portal(client, related_workbook_xlsx, simple_csv):
    upload_a = _upload(client, related_workbook_xlsx)
    config_a = client.get(f"/api/workbooks/{upload_a.json()['id']}/portal").json()

    upload_b = _upload(client, simple_csv, filename="data.csv")
    config_b = client.get(f"/api/workbooks/{upload_b.json()['id']}/portal").json()

    assert {e["worksheet"] for e in config_a["entities"]} != {e["worksheet"] for e in config_b["entities"]}


def test_records_list_supports_search_and_status_filter(client, related_workbook_xlsx):
    upload = _upload(client, related_workbook_xlsx)
    workbook_id = upload.json()["id"]

    all_tasks = client.get(f"/api/workbooks/{workbook_id}/worksheets/Tasks/records")
    assert all_tasks.status_code == 200
    assert all_tasks.json()["total"] == 3

    open_tasks = client.get(f"/api/workbooks/{workbook_id}/worksheets/Tasks/records", params={"status": "Open"})
    assert open_tasks.json()["total"] == 2

    searched = client.get(
        f"/api/workbooks/{workbook_id}/worksheets/Tasks/records", params={"search": "foundation"}
    )
    assert searched.json()["total"] == 1
    assert searched.json()["records"][0]["data"]["Task Name"] == "Pour foundation"


def test_record_detail_includes_related_records(client, related_workbook_xlsx):
    upload = _upload(client, related_workbook_xlsx)
    workbook_id = upload.json()["id"]

    tasks_page = client.get(f"/api/workbooks/{workbook_id}/worksheets/Tasks/records").json()
    task_record = next(r for r in tasks_page["records"] if r["data"]["Task Name"] == "Pour foundation")

    detail = client.get(f"/api/workbooks/{workbook_id}/worksheets/Tasks/records/{task_record['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["data"]["Task Name"] == "Pour foundation"
    related_projects = next(r for r in body["related"] if r["entity"] == "Projects")
    assert related_projects["records"][0]["data"]["Project Name"] == "Alpha Tower"

    projects_page = client.get(f"/api/workbooks/{workbook_id}/worksheets/Projects/records").json()
    alpha_record = next(r for r in projects_page["records"] if r["data"]["Project Name"] == "Alpha Tower")
    project_detail = client.get(
        f"/api/workbooks/{workbook_id}/worksheets/Projects/records/{alpha_record['id']}"
    ).json()
    related_tasks = next(r for r in project_detail["related"] if r["entity"] == "Tasks")
    assert len(related_tasks["records"]) == 2


def test_portal_config_404_for_unknown_workbook(client):
    import uuid

    response = client.get(f"/api/workbooks/{uuid.uuid4()}/portal")
    assert response.status_code == 404
