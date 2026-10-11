"""Status choices cover the whole lifecycle; references show readable names."""

import pytest

from app.services.records.statuses import detect_family, status_options
from tests.test_business_rules import create, farm, field, find, url  # noqa: F401  (farm is a fixture)
from tests.test_records_crud import records_url, upload_demo


@pytest.mark.parametrize(
    ("values", "sheet", "column", "must_include"),
    [
        (["Not Started", "In Progress"], "Tasks_Operations", "Status", {"Completed", "On Hold", "Cancelled"}),
        (["Open", "Investigating"], "Issues_Risks", "Status", {"Resolved", "Closed"}),
        (["Active"], "Workers", "Status", {"Inactive", "On Hold"}),
        (["Paid", "Pending"], "Expenses_Payments", "Payment_Status", {"Overdue", "Cancelled"}),
        (["Delivered", "Pending", "Shipped", "Cancelled"], "Orders", "Status", {"Processing", "Returned"}),
    ],
)
def test_status_options_cover_the_lifecycle(values, sheet, column, must_include):
    options = status_options(values, sheet, column)
    assert set(values) <= set(options)  # the workbook's own values are always kept
    assert must_include <= set(options)


def test_workbook_wording_is_kept_and_synonyms_not_added():
    options = status_options(["Open", "In Progress", "Done"], "Tasks", "Status")
    assert "Done" in options and "Completed" not in options
    assert options.index("Open") < options.index("In Progress") < options.index("Done")  # lifecycle order


def test_unrecognised_categories_are_left_alone():
    assert status_options(["Gold", "Silver"], "Customers", "Tier") == ["Gold", "Silver"]
    assert detect_family(["Gold"], "Customers", "Tier") is None


def test_ambiguous_values_use_the_sheet_name():
    assert detect_family(["Pending"], "Expenses_Payments", "Payment_Status") == "payment"
    assert detect_family(["Pending"], "Orders", "Status") == "order"
    assert detect_family(["Open"], "Issues_Risks", "Status") == "issue"
    assert detect_family(["Open"], "Tasks", "Status") == "work"


def test_form_offers_and_server_accepts_new_lifecycle_statuses(client, farm):  # noqa: F811
    options = field(client, farm, "Tasks_Operations", "Status")["options"]
    assert {"Not Started", "In Progress", "Done", "On Hold", "Cancelled"} <= set(options)
    task = find(client, farm, "Tasks_Operations", "Task_ID", "TSK-002")
    response = client.patch(f"{url(farm, 'Tasks_Operations')}/{task['id']}", json={"data": {"Status": "on hold"}})
    assert response.status_code == 200 and response.json()["data"]["Status"] == "On Hold"
    assert client.patch(f"{url(farm, 'Tasks_Operations')}/{task['id']}", json={"data": {"Status": "Sleeping"}}).status_code == 422


def test_done_statuses_include_lifecycle_completion(client, tmp_path):
    workbook_id = upload_demo(client, tmp_path)
    schema = client.get(f"/api/workbooks/{workbook_id}/worksheets/Issues/schema").json()
    assert {"Resolved", "Closed"} <= set(schema["done_statuses"])


def test_approval_workflow_status_is_not_extended(client, tmp_path):
    workbook_id = upload_demo(client, tmp_path)
    status = next(f for f in client.get(f"/api/workbooks/{workbook_id}/worksheets/Purchase Requests/schema").json()["fields"] if f["name"] == "Status")
    assert status["readonly"] and status.get("workflow")


# --- readable references --------------------------------------------------------


def test_records_show_related_names_and_keep_ids(client, farm):  # noqa: F811
    rows = client.get(url(farm, "Feed_Logs"), params={"page_size": 50}).json()["records"]
    log = next(r for r in rows if r["data"]["Feed_Log_ID"] == "FD-001")
    assert log["data"]["Pond_ID"] == "POND-001"  # raw ID unchanged
    assert log["display"]["Pond_ID"] == "North Pond"
    assert log["display"]["Feed_Item_ID"] == "Shrimp Grower 35"
    detail = client.get(f"{url(farm, 'Feed_Logs')}/{log['id']}").json()
    assert detail["display"]["Pond_ID"] == "North Pond"


def test_reference_label_includes_location_when_available(client, tmp_path):
    import openpyxl

    path = tmp_path / "sites.xlsx"
    wb = openpyxl.Workbook()
    projects = wb.active
    projects.title = "Projects"
    projects.append(["Project_ID", "Project_Name", "Location", "Status"])
    projects.append(["PRJ-001", "Green Meadows", "Kompally, Hyderabad", "In Progress"])
    projects.append(["PRJ-002", "Lakeview Villas", "Shamirpet", "At Risk"])
    issues = wb.create_sheet("Issues_Risks")
    issues.append(["Issue_ID", "Project_ID", "Description", "Status"])
    issues.append(["ISS-001", "PRJ-001", "Rain delay", "Open"])
    issues.append(["ISS-002", "PRJ-002", "Vendor delay", "Closed"])
    wb.save(path)
    with open(path, "rb") as f:
        workbook_id = client.post("/api/workbooks", files={"file": (path.name, f, "application/octet-stream")}).json()["id"]
    rows = client.get(records_url(workbook_id, "Issues_Risks")).json()["records"]
    labels = {r["data"]["Issue_ID"]: r["display"].get("Project_ID") for r in rows}
    assert labels == {"ISS-001": "Green Meadows · Kompally, Hyderabad", "ISS-002": "Lakeview Villas · Shamirpet"}


def test_status_alerts_name_their_sheet_in_the_api_detail(client, farm):  # noqa: F811
    alerts = client.get(f"/api/workbooks/{farm}/portal").json()["alerts"]
    status_alerts = [a for a in alerts if ":status:" in a["key"]]
    assert status_alerts and all(a["entity"] and a["detail"] for a in status_alerts)
