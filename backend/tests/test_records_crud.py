"""Create / edit / delete records: validation, calculations, live KPI
refresh, audit trail, tenant isolation and permissions."""

import importlib.util
from pathlib import Path

import pytest

from app.models.worksheet import Worksheet

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

PR = "Purchase Requests"
VALID_PR = {
    "Item": "TMT Steel Bars 12mm",
    "Project": "Green Meadows Apartments",
    "Requested By": "Asha Rao",
    "Quantity": 5,
    "Requested Date": "2026-10-11",
}


def upload_demo(client, tmp_path, script="generate_demo_data.py") -> str:
    spec = importlib.util.spec_from_file_location(script, _SCRIPTS / script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / script.replace(".py", ".xlsx")
    module.build_workbook().save(path)
    with open(path, "rb") as f:
        response = client.post("/api/workbooks", files={"file": (path.name, f, "application/octet-stream")})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def records_url(workbook_id: str, worksheet: str) -> str:
    return f"/api/workbooks/{workbook_id}/worksheets/{worksheet}/records"


def create(client, workbook_id, worksheet, data):
    return client.post(records_url(workbook_id, worksheet), json={"data": data})


def find(client, workbook_id, worksheet, column, value) -> dict:
    page = client.get(records_url(workbook_id, worksheet), params={"page_size": 200}).json()
    return next(r for r in page["records"] if r["data"].get(column) == value)


def kpi(client, workbook_id, key_suffix):
    config = client.get(f"/api/workbooks/{workbook_id}/portal").json()
    every = config["kpis"] + config["alerts"]
    return next(k["value"] for k in every if k["key"].endswith(key_suffix))


@pytest.fixture
def construction(client, tmp_path):
    return upload_demo(client, tmp_path)


# --- schema ------------------------------------------------------------------


def test_purchase_request_form_schema(client, construction):
    schema = client.get(f"/api/workbooks/{construction}/worksheets/{PR}/schema").json()
    fields = {f["name"]: f for f in schema["fields"]}
    assert schema["can_create"] is True
    assert fields["Item"]["input"] == "select" and "TMT Steel Bars 12mm" in fields["Item"]["options"]
    assert fields["Project"]["options"] == sorted(["Green Meadows Apartments", "Lakeview Luxury Villas", "Orchid Commercial Fit-out"])
    assert fields["Unit Cost"]["lookup"]["defaults"]["TMT Steel Bars 12mm"] == 42000
    assert fields["Amount"]["readonly"] and "Quantity" in fields["Amount"]["computed"]
    assert fields["PR ID"]["auto"] == "next_id" and fields["PR ID"]["placeholder"] == "PR-1007"
    assert fields["Status"]["readonly"] and fields["Status"]["default"] == "Pending Approval"
    required = {name for name, f in fields.items() if f["required"]}
    assert {"Item", "Project", "Requested By", "Quantity", "Requested Date"} <= required
    assert schema["workflow"]["approved"] == "Approved"
    # Field order: Unit Cost appears right after the field it's looked up from.
    names = [f["name"] for f in schema["fields"]]
    assert names.index("Unit Cost") == names.index("Item") + 1


# --- create ------------------------------------------------------------------


def test_create_purchase_request_calculates_total(client, construction):
    response = create(client, construction, PR, VALID_PR)
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["PR ID"] == "PR-1007"
    assert data["Status"] == "Pending Approval"
    assert data["Unit Cost"] == 42000
    assert data["Amount"] == 5 * 42000
    assert response.json()["actions"]["approve"] is True


def test_entered_unit_cost_overrides_the_lookup(client, construction):
    data = create(client, construction, PR, {**VALID_PR, "Unit Cost": 40000}).json()["data"]
    assert data["Amount"] == 200000


def test_client_cannot_set_calculated_amount(client, construction):
    data = create(client, construction, PR, {**VALID_PR, "Amount": 1}).json()["data"]
    assert data["Amount"] == 210000


def test_kpis_and_alerts_refresh_after_create(client, construction):
    pending_before = kpi(client, construction, f"{PR}:status:Pending Approval")
    amount_before = kpi(client, construction, f"{PR}:sum:Amount")
    create(client, construction, PR, VALID_PR)
    assert kpi(client, construction, f"{PR}:status:Pending Approval") == pending_before + 1
    assert kpi(client, construction, f"{PR}:sum:Amount") == amount_before + 210000


def test_ids_keep_incrementing(client, construction):
    first = create(client, construction, PR, VALID_PR).json()["data"]["PR ID"]
    second = create(client, construction, PR, VALID_PR).json()["data"]["PR ID"]
    assert (first, second) == ("PR-1007", "PR-1008")


@pytest.mark.parametrize(
    ("overrides", "field", "message"),
    [
        ({"Quantity": None}, "Quantity", "required"),
        ({"Quantity": "lots"}, "Quantity", "Enter a number"),
        ({"Quantity": 2.5}, "Quantity", "whole number"),
        ({"Quantity": -3}, "Quantity", "zero or more"),
        ({"Requested Date": "31/31/2026"}, "Requested Date", "valid date"),
        ({"Item": "Gold Bars"}, "Item", "existing materials"),
        ({"Project": "Moon Base"}, "Project", "existing projects"),
        ({"Status": "Approved"}, "Status", "approve / reject"),
        ({"Hacked": "x"}, "Hacked", "Unknown field"),
        ({"PR ID": "PR-1001"}, "PR ID", "already exists"),
        ({"Unit Cost": -1}, "Unit Cost", "zero or more"),
    ],
)
def test_create_validation(client, construction, overrides, field, message):
    response = create(client, construction, PR, {**VALID_PR, **overrides})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error_code"] == "VALIDATION_FAILED"
    assert message.lower() in detail["fields"][field].lower()


def test_missing_required_fields_are_all_reported(client, construction):
    detail = create(client, construction, PR, {}).json()["detail"]
    assert {"Item", "Project", "Requested By", "Quantity", "Requested Date"} <= set(detail["fields"])


def test_references_are_stored_with_canonical_spelling(client, construction):
    data = create(client, construction, PR, {**VALID_PR, "Project": "  green meadows apartments "}).json()["data"]
    assert data["Project"] == "Green Meadows Apartments"


def test_generic_entity_status_must_be_a_known_value(client, construction):
    task = {"Task Name": "Pour slab", "Project": "Lakeview Luxury Villas", "Assigned To": "Ravi", "Due Date": "2026-11-01", "Priority": "High"}
    assert create(client, construction, "Tasks", {**task, "Status": "Sleeping"}).status_code == 422
    created = create(client, construction, "Tasks", {**task, "Status": "open"})
    assert created.status_code == 201
    assert created.json()["data"]["Status"] == "Open"


def test_retail_order_total_uses_product_price(client, tmp_path):
    retail = upload_demo(client, tmp_path, "generate_demo_data_retail.py")
    response = create(
        client,
        retail,
        "Orders",
        {"Customer Name": "Sara Thomas", "Product Name": "Laptop Stand", "Quantity": 2, "Order Date": "2026-10-11", "Status": "Pending"},
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["Order ID"] == "ORD-1007"
    assert data["Total Amount"] == 2 * 1899


# --- update ------------------------------------------------------------------


def test_update_recalculates_and_refreshes_unit_cost(client, construction):
    record = create(client, construction, PR, VALID_PR).json()
    url = f"{records_url(construction, PR)}/{record['id']}"
    updated = client.patch(url, json={"data": {"Quantity": 10}}).json()["data"]
    assert updated["Amount"] == 420000
    # Changing the material re-looks-up its unit cost.
    updated = client.patch(url, json={"data": {"Item": "Red Clay Bricks"}}).json()["data"]
    assert updated["Unit Cost"] == 8 and updated["Amount"] == 80


def test_update_validates_only_what_changed(client, construction):
    record = create(client, construction, PR, VALID_PR).json()
    url = f"{records_url(construction, PR)}/{record['id']}"
    response = client.patch(url, json={"data": {"Quantity": "x"}})
    assert response.status_code == 422 and set(response.json()["detail"]["fields"]) == {"Quantity"}


def test_update_writes_audit_history(client, construction):
    record = create(client, construction, PR, VALID_PR).json()
    url = f"{records_url(construction, PR)}/{record['id']}"
    client.patch(url, json={"data": {"Quantity": 7}})
    history = client.get(f"{url}/activity").json()["history"]
    assert [e["action"] for e in history] == ["updated", "created"]
    assert history[0]["changes"]["Quantity"] == [5, 7]
    assert history[0]["user_name"] == "owner"


# --- delete ------------------------------------------------------------------


def test_delete_record_and_refresh_kpis(client, construction):
    record = create(client, construction, PR, VALID_PR).json()
    url = f"{records_url(construction, PR)}/{record['id']}"
    before = kpi(client, construction, f"{PR}:count")
    assert client.delete(url).status_code == 204
    assert kpi(client, construction, f"{PR}:count") == before - 1
    assert client.get(url).status_code == 404


def test_deleting_every_record_does_not_resurrect_original_rows(client, construction):
    issues = client.get(records_url(construction, "Issues")).json()["records"]
    for issue in issues:
        assert client.delete(f"{records_url(construction, 'Issues')}/{issue['id']}").status_code == 204
    client.get(f"/api/workbooks/{construction}/portal")  # triggers the self-heal check
    assert client.get(records_url(construction, "Issues")).json()["total"] == 0
    with client.test_sessionmaker() as db:
        assert db.query(Worksheet).filter(Worksheet.name == "Issues").one().row_count == 0


def test_cannot_delete_a_record_others_depend_on(client, construction):
    project = find(client, construction, "Projects", "Project Name", "Lakeview Luxury Villas")
    response = client.delete(f"{records_url(construction, 'Projects')}/{project['id']}")
    assert response.status_code == 409
    assert response.json()["detail"]["error_code"] == "RECORD_IN_USE"
    assert "tasks" in response.json()["detail"]["message"]


# --- isolation & permissions -------------------------------------------------


def test_other_user_cannot_touch_my_records(client, make_client, construction):
    record = create(client, construction, PR, VALID_PR).json()
    other = make_client("other@example.com")
    url = f"{records_url(construction, PR)}/{record['id']}"
    assert create(other, construction, PR, VALID_PR).status_code == 404
    assert other.patch(url, json={"data": {"Quantity": 1}}).status_code == 404
    assert other.delete(url).status_code == 404
    assert other.get(f"/api/workbooks/{construction}/worksheets/{PR}/schema").status_code == 404
    assert other.get(f"{url}/activity").status_code == 404
    assert client.get(f"{url}/activity").json()["history"][0]["action"] == "created"


def test_record_ids_from_another_worksheet_are_404(client, construction):
    task = find(client, construction, "Tasks", "Task Name", "Landscaping Phase 1")
    assert client.patch(f"{records_url(construction, PR)}/{task['id']}", json={"data": {"Quantity": 1}}).status_code == 404


def test_viewer_cannot_create_edit_or_delete(client, make_client, construction):
    record = create(client, construction, PR, VALID_PR).json()
    viewer = make_client("viewer@example.com", role="viewer")
    # Same tenant as the owner, so the role is what's being tested.
    with client.test_sessionmaker() as db:
        from app.models.user import User

        owner = db.query(User).filter(User.email == "owner@example.com").one()
        db.query(User).filter(User.email == "viewer@example.com").update({"tenant_id": owner.tenant_id})
        db.commit()
    url = f"{records_url(construction, PR)}/{record['id']}"
    assert create(viewer, construction, PR, VALID_PR).status_code == 403
    assert viewer.patch(url, json={"data": {"Quantity": 1}}).status_code == 403
    assert viewer.delete(url).status_code == 403
    assert viewer.get(f"/api/workbooks/{construction}/worksheets/{PR}/schema").json()["can_create"] is False
    assert viewer.get(f"{url}/activity").json()["actions"] == {
        "edit": False, "delete": False, "approve": False, "reject": False, "resubmit": False,
    }


# --- contextual actions on other entities ------------------------------------


def test_completing_an_overdue_task_clears_it_from_the_alert(client, construction):
    overdue = kpi(client, construction, "Tasks:overdue")
    task = find(client, construction, "Tasks", "Task Name", "Final Plumbing Inspection")
    response = client.patch(f"{records_url(construction, 'Tasks')}/{task['id']}", json={"data": {"Status": "Done"}})
    assert response.status_code == 200
    assert kpi(client, construction, "Tasks:overdue") == overdue - 1


def test_resolving_an_issue_updates_the_open_issues_alert(client, construction):
    open_before = kpi(client, construction, "Issues:status:Open")
    issue = find(client, construction, "Issues", "Title", "Vendor delay on precast panels")
    client.patch(f"{records_url(construction, 'Issues')}/{issue['id']}", json={"data": {"Status": "Resolved"}})
    assert kpi(client, construction, "Issues:status:Open") == open_before - 1
    schema = client.get(f"/api/workbooks/{construction}/worksheets/Issues/schema").json()
    assert "Resolved" in schema["done_statuses"]  # drives the "Mark resolved" action


def test_updating_material_stock_clears_low_stock_alert(client, construction):
    low_before = kpi(client, construction, "Materials:low_stock")
    cement = find(client, construction, "Materials", "Material Name", "Cement (OPC 53 Grade)")
    client.patch(f"{records_url(construction, 'Materials')}/{cement['id']}", json={"data": {"Quantity On Hand": 900}})
    assert kpi(client, construction, "Materials:low_stock") == low_before - 1


def test_recording_an_expense_updates_totals_and_charts(client, construction):
    total = kpi(client, construction, "Expenses:sum:Amount")
    response = create(
        client, construction, "Expenses",
        {"Project": "Orchid Commercial Fit-out", "Category": "Labor", "Amount": 125000, "Date": "2026-10-10", "Status": "Pending"},
    )
    assert response.status_code == 201, response.text
    assert kpi(client, construction, "Expenses:sum:Amount") == total + 125000


def test_entities_without_workflow_offer_no_decisions_in_actions(client, construction):
    task = find(client, construction, "Tasks", "Task Name", "Landscaping Phase 1")
    actions = client.get(f"{records_url(construction, 'Tasks')}/{task['id']}/activity").json()["actions"]
    assert actions["edit"] and actions["delete"]
    assert not (actions["approve"] or actions["reject"] or actions["resubmit"])
