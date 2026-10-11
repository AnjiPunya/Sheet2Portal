"""Regression tests for display-label formatting and the record list's
related-record filter (record detail -> "View all")."""

import importlib.util
import uuid
from pathlib import Path

import openpyxl
import pytest

from app.services.analysis.engine import build_portal_config
from app.services.analysis.text import humanize
from app.services.analysis.types import SheetData

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Project_Manager", "Project Manager"),
        ("project_manager", "Project Manager"),
        ("purchase-requests", "Purchase Requests"),
        ("projectName", "Project Name"),
        ("PR_ID", "PR ID"),
        ("PR ID", "PR ID"),
        ("SKU_code", "SKU Code"),
        ("PURCHASE_REQUESTS", "Purchase Requests"),
        ("Project__Manager ", "Project Manager"),
        ("Project Manager", "Project Manager"),
    ],
)
def test_humanize(raw, expected):
    assert humanize(raw) == expected


def test_humanize_is_idempotent():
    for raw in ("Project_Manager", "PR_ID", "unitCost", "PURCHASE_REQUESTS"):
        assert humanize(humanize(raw)) == humanize(raw)


def test_kpi_labels_are_humanized_but_keys_keep_raw_field_names():
    sheet = SheetData(
        name="project_list",
        columns=[("Project_Name", "string", 1.0), ("Total_Budget", "int", 1.0), ("Actual_Spent", "int", 1.0)],
        rows=[{"Project_Name": "A", "Total_Budget": 100, "Actual_Spent": 50}],
    )
    entity = build_portal_config("T", [sheet]).entities[0]
    assert entity.label == "Project List"
    labels = {k.label for k in entity.kpis}
    assert "Total Budget" in labels and "Total Actual Spent" in labels
    assert not any("_" in label for label in labels)
    # Internal identifiers stay untouched.
    assert {c.name for c in entity.columns} == {"Project_Name", "Total_Budget", "Actual_Spent"}
    assert any(k.key.endswith(":sum:Total_Budget") for k in entity.kpis)


# --- related-record filter -------------------------------------------------


def _upload_construction_demo(client, tmp_path) -> str:
    spec = importlib.util.spec_from_file_location("gen", _SCRIPTS / "generate_demo_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / "construction.xlsx"
    module.build_workbook().save(path)
    with open(path, "rb") as f:
        response = client.post("/api/workbooks", files={"file": (path.name, f, "application/octet-stream")})
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def _records(client, workbook_id, worksheet, **params):
    return client.get(f"/api/workbooks/{workbook_id}/worksheets/{worksheet}/records", params=params)


def _project_id(client, workbook_id, name):
    page = _records(client, workbook_id, "Projects", search=name).json()
    return next(r["id"] for r in page["records"] if r["data"]["Project Name"] == name)


def _task_names(response):
    assert response.status_code == 200, response.text
    return {r["data"]["Task Name"] for r in response.json()["records"]}


@pytest.fixture
def construction(client, tmp_path):
    return _upload_construction_demo(client, tmp_path)


def test_related_filter_shows_only_tasks_for_selected_project(client, construction):
    project_id = _project_id(client, construction, "Lakeview Luxury Villas")
    response = _records(client, construction, "Tasks", related_worksheet="Projects", related_record_id=project_id)
    assert _task_names(response) == {"MEP Rough-in Villa 4-8", "Landscaping Phase 1"}
    assert response.json()["total"] == 2


def test_related_filter_differs_per_project(client, construction):
    green = _project_id(client, construction, "Green Meadows Apartments")
    orchid = _project_id(client, construction, "Orchid Commercial Fit-out")
    green_tasks = _task_names(_records(client, construction, "Tasks", related_worksheet="Projects", related_record_id=green))
    orchid_tasks = _task_names(_records(client, construction, "Tasks", related_worksheet="Projects", related_record_id=orchid))
    assert green_tasks == {"Foundation Pouring - Tower A", "Structural Steel Fixing", "Final Plumbing Inspection"}
    assert orchid_tasks == {"Facade Glazing Install", "Interior Fit-out Floor 5"}


def test_related_filter_combines_with_status_filter(client, construction):
    green = _project_id(client, construction, "Green Meadows Apartments")
    response = _records(
        client, construction, "Tasks", related_worksheet="Projects", related_record_id=green, status="Open"
    )
    assert _task_names(response) == {"Final Plumbing Inspection"}


def test_clearing_related_filter_shows_all_records_again(client, construction):
    project_id = _project_id(client, construction, "Lakeview Luxury Villas")
    filtered = _records(client, construction, "Tasks", related_worksheet="Projects", related_record_id=project_id)
    cleared = _records(client, construction, "Tasks")
    assert filtered.json()["total"] == 2
    assert cleared.json()["total"] == 7


def test_related_filter_requires_both_parameters(client, construction):
    response = _records(client, construction, "Tasks", related_worksheet="Projects")
    assert response.status_code == 422
    assert response.json()["detail"]["error_code"] == "INVALID_RELATED_FILTER"


def test_related_filter_rejects_unrelated_worksheets(client, construction):
    project_id = _project_id(client, construction, "Lakeview Luxury Villas")
    # Tasks and Materials share no detected relationship.
    response = _records(client, construction, "Materials", related_worksheet="Tasks", related_record_id=project_id)
    assert response.status_code == 422
    assert response.json()["detail"]["error_code"] == "NO_RELATIONSHIP"


def test_related_filter_unknown_parent_record_is_404(client, construction):
    response = _records(client, construction, "Tasks", related_worksheet="Projects", related_record_id=str(uuid.uuid4()))
    assert response.status_code == 404


def test_related_filter_cannot_use_parent_from_another_workbook(client, construction, tmp_path):
    (tmp_path / "other").mkdir()
    other = _upload_construction_demo(client, tmp_path / "other")
    foreign_project = _project_id(client, other, "Lakeview Luxury Villas")
    response = _records(client, construction, "Tasks", related_worksheet="Projects", related_record_id=foreign_project)
    assert response.status_code == 404


def test_record_detail_labels_unaffected_by_display_formatting(client, tmp_path):
    path = tmp_path / "underscored.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Projects"
    ws.append(["Project_Name", "Project_Manager", "Budget"])
    ws.append(["Alpha", "Asha", 100])
    wb.save(path)
    with open(path, "rb") as f:
        workbook_id = client.post("/api/workbooks", files={"file": (path.name, f, "application/octet-stream")}).json()["id"]
    record = _records(client, workbook_id, "Projects").json()["records"][0]
    # Raw field names are preserved in the API; formatting is display-only.
    assert record["data"]["Project_Manager"] == "Asha"
