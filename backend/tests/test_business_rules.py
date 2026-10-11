"""Application-wide review regressions: display labels, IDs, data types,
relationships, stock limits, calculations and business rules -- on a
workbook shaped like real customer files (underscore headers, ID codes,
documentation sheets)."""

from datetime import date

import openpyxl
import pytest

from app.services.ai.orchestrator import humanize_identifiers
from app.services.analysis.engine import build_portal_config
from app.services.analysis.types import SheetData

FARM = "aqua_farm.xlsx"


def _book(path):
    wb = openpyxl.Workbook()
    readme = wb.active
    readme.title = "README"
    readme.append(["About this workbook", "Details"])
    readme.append(["Purpose", "Sample data"])
    readme.append(["Note", "Fictional"])

    def sheet(name, header, rows):
        ws = wb.create_sheet(name)
        ws.append(header)
        for row in rows:
            ws.append(row)

    d = date
    sheet("Ponds", ["Pond_ID", "Farm_ID", "Pond_Name", "Species", "Stocking_Date", "Planned_Harvest_Date", "Area_Acres", "Status", "Manager"], [
        ["POND-001", "FARM-001", "North Pond", "Shrimp", d(2026, 7, 1), d(2026, 11, 15), 2.5, "Active", "Ravi Kumar"],
        ["POND-002", "FARM-001", "East Pond", "Shrimp", d(2026, 7, 10), d(2026, 11, 25), 3.0, "Active", "Suresh Reddy"],
        ["POND-003", "FARM-001", "South Pond", "Tilapia", d(2026, 6, 1), d(2026, 10, 1), 1.8, "Harvested", "Lakshmi Devi"],
    ])
    sheet("Feed_Inventory", ["Feed_Item_ID", "Feed_Name", "Stock_Kg", "Reorder_Level_Kg", "Unit_Cost_INR_Per_Kg", "Protein_Percent"], [
        ["FEED-001", "Shrimp Starter 40", 180, 200, 92, 40],
        ["FEED-002", "Shrimp Grower 35", 620, 250, 76, 35],
        ["FEED-003", "Tilapia Grower 30", 400, 100, 48, 30],
    ])
    sheet("Feed_Logs", ["Feed_Log_ID", "Pond_ID", "Feed_Date", "Feed_Item_ID", "Quantity_Kg", "Unit_Cost_INR_Per_Kg", "Total_Cost_INR", "Recorded_By", "Notes"], [
        ["FD-001", "POND-001", d(2026, 10, 9), "FEED-002", 42, 76, 3192, "Ravi Kumar", "Normal"],
        ["FD-002", "POND-002", d(2026, 10, 9), "FEED-002", 48, 76, 3648, "Suresh Reddy", "Reduced evening feed"],
        ["FD-003", "POND-003", d(2026, 10, 9), "FEED-003", 30, 48, 1440, "Lakshmi Devi", "Normal"],
    ])
    sheet("Suppliers_Buyers", ["Party_ID", "Party_Type", "Party_Name", "Phone", "Email", "Rating"], [
        ["SUP-001", "Supplier", "Bluewater Feeds", 9000000001, "kiran@example.com", 4.5],
        ["SUP-002", "Supplier", "Delta Aquafeed", 9000000002, "meena@example.com", 4.2],
        ["BUY-001", "Buyer", "Coastal Seafood", 9000000003, "buyer@example.com", 4.8],
    ])
    sheet("Water_Quality", ["Reading_ID", "Pond_ID", "Reading_Date", "Reading_Time", "Temperature_C", "Dissolved_Oxygen_mg_L"], [
        ["WQ-001", "POND-001", d(2026, 10, 10), "06:00", 29.1, 5.2],
        ["WQ-002", "POND-001", d(2026, 10, 10), "18:00", 30.0, 4.1],
        ["WQ-003", "POND-002", d(2026, 10, 10), "06:00", 28.7, 4.9],
    ])
    sheet("Materials", ["Material_ID", "Material_Name", "Opening_Stock", "Received_Qty", "Used_Qty", "Reorder_Level", "Unit_Cost_INR"], [
        ["MAT-001", "OPC Cement 50kg", 500, 300, 620, 200, 390],
        ["MAT-002", "TMT Steel 12mm", 8, 12, 15, 6, 62000],
        ["MAT-003", "River Sand", 40, 20, 35, 10, 1500],
    ])
    sheet("Purchase_Requests", ["Request_ID", "Material_ID", "Material_or_Service", "Quantity", "Request_Date", "Needed_By", "Approval_Status"], [
        ["REQ-001", "MAT-001", "OPC Cement 50kg", 200, d(2026, 10, 8), d(2026, 10, 12), "Pending Approval"],
        ["REQ-002", "MAT-002", "TMT Steel 12mm", 3, d(2026, 10, 7), d(2026, 10, 15), "Approved"],
        ["REQ-003", "MAT-003", "River Sand", 10, d(2026, 10, 6), d(2026, 10, 9), "Rejected"],
    ])
    sheet("Tasks_Operations", ["Task_ID", "Task_Name", "Assigned_To", "Start_Date", "Due_Date", "Progress_Percent", "Status"], [
        ["TSK-001", "Water check", "Ravi Kumar", d(2026, 10, 11), d(2026, 10, 11), 50, "In Progress"],
        ["TSK-002", "Retest oxygen", "Suresh Reddy", d(2026, 10, 11), d(2026, 10, 12), 0, "Not Started"],
        ["TSK-003", "Harvest prep", "Lakshmi Devi", d(2026, 10, 1), d(2026, 10, 5), 100, "Done"],
    ])
    sheet("Access_Levels", ["Level_Name", "View_Financials"], [["Owner", "Yes"], ["Manager", "Limited"], ["Worker", "No"]])
    wb.save(path)


@pytest.fixture
def farm(client, tmp_path):
    path = tmp_path / FARM
    _book(path)
    with open(path, "rb") as f:
        response = client.post("/api/workbooks", files={"file": (FARM, f, "application/octet-stream")})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def url(workbook_id, sheet):
    return f"/api/workbooks/{workbook_id}/worksheets/{sheet}/records"


def create(client, workbook_id, sheet, data):
    return client.post(url(workbook_id, sheet), json={"data": data})


def schema(client, workbook_id, sheet):
    return client.get(f"/api/workbooks/{workbook_id}/worksheets/{sheet}/schema")


def field(client, workbook_id, sheet, name):
    return next(f for f in schema(client, workbook_id, sheet).json()["fields"] if f["name"] == name)


def find(client, workbook_id, sheet, column, value):
    rows = client.get(url(workbook_id, sheet), params={"page_size": 200}).json()["records"]
    return next(r for r in rows if r["data"].get(column) == value)


def errors(response):
    assert response.status_code == 422, response.text
    return response.json()["detail"]["fields"]


# --- display labels ----------------------------------------------------------


def test_no_underscores_in_portal_labels(client, farm):
    config = client.get(f"/api/workbooks/{farm}/portal").json()
    labels = [e["label"] for e in config["entities"]] + [k["label"] for k in config["kpis"] + config["alerts"]]
    labels += [c["title"] for c in config["charts"]]
    assert labels and not [label for label in labels if "_" in label]


def test_form_labels_are_readable_but_names_stay_raw(client, farm):
    fields = schema(client, farm, "Water_Quality").json()["fields"]
    by_name = {f["name"]: f["label"] for f in fields}
    assert by_name["Dissolved_Oxygen_mg_L"] == "Dissolved Oxygen (mg/L)"
    assert by_name["Temperature_C"] == "Temperature (°C)"
    assert not any("_" in label for label in by_name.values())
    assert "Pond_ID" in by_name  # identifiers unchanged internally


def test_chat_answers_get_readable_names():
    sheet = SheetData(name="Feed_Logs", columns=[("Feed_Log_ID", "string", 1.0), ("Quantity_Kg", "int", 1.0)], rows=[{"Feed_Log_ID": "FD-1", "Quantity_Kg": 4}])
    config = build_portal_config("T", [sheet])
    text = "Total Quantity_Kg in Feed_Logs is 4 (status In_Progress)."
    assert humanize_identifiers(text, config) == "Total Quantity (kg) in Feed Logs is 4 (status In_Progress)."


# --- reference sheets ----------------------------------------------------------


def test_readme_is_read_only_reference(client, farm):
    config = client.get(f"/api/workbooks/{farm}/portal").json()
    readme = next(e for e in config["entities"] if e["worksheet"] == "README")
    assert readme["reference"] is True and readme["kpis"] == []
    assert not any(k["entity"] == "README" for k in config["kpis"] + config["alerts"])
    assert schema(client, farm, "README").status_code == 422
    assert create(client, farm, "README", {"Details": "x"}).json()["detail"]["error_code"] == "NOT_EDITABLE"


# --- calculations / KPIs --------------------------------------------------------


def test_unit_prices_and_percentages_are_never_summed(client, farm):
    labels = [k["label"] for k in client.get(f"/api/workbooks/{farm}/portal").json()["kpis"]]
    assert "Total Cost (INR)" in labels  # a real total is still summed
    assert not [label for label in labels if "Unit Cost" in label or "%" in label or "Rating" in label or "Phone" in label]


def test_over_time_chart_uses_totals_not_unit_prices(client, farm):
    charts = client.get(f"/api/workbooks/{farm}/portal").json()["charts"]
    titles = [c["title"] for c in charts if c["kind"] == "time_columns"]
    assert not [t for t in titles if "unit cost" in t.lower()]


# --- relationships --------------------------------------------------------------


def test_id_references_become_dropdowns_with_names(client, farm):
    item = field(client, farm, "Feed_Logs", "Feed_Item_ID")
    assert item["input"] == "select"
    assert item["option_labels"]["FEED-002"] == "FEED-002 · Shrimp Grower 35"
    assert create(client, farm, "Feed_Logs", {"Pond_ID": "POND-001", "Feed_Date": "2026-10-11", "Feed_Item_ID": "FEED-999", "Quantity_Kg": 1, "Recorded_By": "Ravi Kumar"}).status_code == 422


def test_people_are_free_text_not_fake_links(client, farm):
    for sheet, column in (("Ponds", "Manager"), ("Tasks_Operations", "Assigned_To"), ("Feed_Logs", "Recorded_By")):
        assert field(client, farm, sheet, column)["input"] != "select", f"{sheet}.{column}"
    response = create(client, farm, "Feed_Logs", {"Pond_ID": "POND-001", "Feed_Date": "2026-10-11", "Feed_Item_ID": "FEED-002", "Quantity_Kg": 5, "Recorded_By": "New Hire"})
    assert response.status_code == 201, response.text


def test_name_copied_from_reference_is_filled_in_not_typed(client, farm):
    spec = field(client, farm, "Purchase_Requests", "Material_or_Service")
    assert spec["readonly"] and spec["lookup"]["from"] == "Material_ID"
    data = create(client, farm, "Purchase_Requests", {"Material_ID": "MAT-002", "Material_or_Service": "Wrong", "Quantity": 2, "Request_Date": "2026-10-11", "Needed_By": "2026-10-20"}).json()["data"]
    assert data["Material_or_Service"] == "TMT Steel 12mm"


def test_unit_cost_defaults_from_the_selected_item(client, farm):
    data = create(client, farm, "Feed_Logs", {"Pond_ID": "POND-002", "Feed_Date": "2026-10-11", "Feed_Item_ID": "FEED-002", "Quantity_Kg": 10, "Recorded_By": "Suresh Reddy"}).json()["data"]
    assert data["Unit_Cost_INR_Per_Kg"] == 76 and data["Total_Cost_INR"] == 760


# --- identifiers -----------------------------------------------------------------


def test_system_ids_are_generated(client, farm):
    assert field(client, farm, "Ponds", "Pond_ID")["auto"] == "next_id"
    data = create(client, farm, "Ponds", {"Pond_Name": "West Pond", "Species": "Shrimp", "Stocking_Date": "2026-10-01", "Planned_Harvest_Date": "2027-02-01", "Area_Acres": 2, "Status": "Active", "Manager": "Ravi Kumar"}).json()["data"]
    assert data["Pond_ID"] == "POND-004"


def test_constant_farm_id_is_prefilled_not_required(client, farm):
    spec = field(client, farm, "Ponds", "Farm_ID")
    assert spec["default"] == "FARM-001"
    data = create(client, farm, "Ponds", {"Pond_Name": "West Pond", "Species": "Shrimp", "Stocking_Date": "2026-10-01", "Planned_Harvest_Date": "2027-02-01", "Area_Acres": 2, "Status": "Active", "Manager": "Ravi Kumar"}).json()["data"]
    assert data["Farm_ID"] == "FARM-001"


def test_ids_with_several_prefixes_follow_the_type(client, farm):
    spec = field(client, farm, "Suppliers_Buyers", "Party_ID")
    assert spec["auto_by"]["next"] == {"Supplier": "SUP-003", "Buyer": "BUY-002"}
    base = {"Party_Name": "New Co", "Phone": "9000000009", "Email": "new@example.com", "Rating": 4}
    assert create(client, farm, "Suppliers_Buyers", {**base, "Party_Type": "Buyer"}).json()["data"]["Party_ID"] == "BUY-002"
    assert create(client, farm, "Suppliers_Buyers", {**base, "Party_Type": "Supplier"}).json()["data"]["Party_ID"] == "SUP-003"


# --- data types ------------------------------------------------------------------

POND = {"Pond_Name": "West", "Species": "Shrimp", "Stocking_Date": "2026-10-01", "Planned_Harvest_Date": "2027-02-01", "Area_Acres": 2, "Status": "Active", "Manager": "Ravi Kumar"}
PARTY = {"Party_Type": "Supplier", "Party_Name": "New Co", "Phone": "9000000009", "Email": "new@example.com", "Rating": 4}


@pytest.mark.parametrize(
    ("sheet", "base", "overrides", "column", "message"),
    [
        ("Ponds", POND, {"Area_Acres": "big"}, "Area_Acres", "Enter a number"),
        ("Ponds", POND, {"Area_Acres": -1}, "Area_Acres", "zero or more"),
        ("Ponds", POND, {"Stocking_Date": "31/31/2026"}, "Stocking_Date", "valid date"),
        ("Suppliers_Buyers", PARTY, {"Phone": "call me"}, "Phone", "valid phone"),
        ("Suppliers_Buyers", PARTY, {"Email": "not-an-email"}, "Email", "valid email"),
        ("Suppliers_Buyers", PARTY, {"Rating": 6}, "Rating", "between 0 and 5"),
        ("Tasks_Operations", {"Task_Name": "x", "Assigned_To": "R", "Start_Date": "2026-10-11", "Due_Date": "2026-10-12", "Status": "Done"}, {"Progress_Percent": 150}, "Progress_Percent", "between 0 and 100"),
        ("Tasks_Operations", {"Task_Name": "x", "Assigned_To": "R", "Start_Date": "2026-10-11", "Due_Date": "2026-10-12", "Status": "Done"}, {"Progress_Percent": -5}, "Progress_Percent", "zero or more"),
        ("Water_Quality", {"Pond_ID": "POND-001", "Reading_Date": "2026-10-11", "Temperature_C": 28, "Dissolved_Oxygen_mg_L": 5}, {"Reading_Time": "25:00"}, "Reading_Time", "valid time"),
    ],
)
def test_field_types_are_enforced(client, farm, sheet, base, overrides, column, message):
    assert message.lower() in errors(create(client, farm, sheet, {**base, **overrides}))[column].lower()


def test_phone_is_stored_as_text_and_time_is_normalised(client, farm):
    party = create(client, farm, "Suppliers_Buyers", {**PARTY, "Phone": "+91 90000 00009"}).json()["data"]
    assert party["Phone"] == "+91 90000 00009"
    reading = create(client, farm, "Water_Quality", {"Pond_ID": "POND-001", "Reading_Date": "2026-10-11", "Reading_Time": "6:30", "Temperature_C": -1, "Dissolved_Oxygen_mg_L": 5}).json()
    assert reading["data"]["Reading_Time"] == "06:30"
    assert reading["data"]["Temperature_C"] == -1  # temperatures may go below zero


def test_form_input_types(client, farm):
    assert field(client, farm, "Suppliers_Buyers", "Phone")["input"] == "tel"
    assert field(client, farm, "Suppliers_Buyers", "Email")["input"] == "email"
    assert field(client, farm, "Water_Quality", "Reading_Time")["input"] == "time"
    assert field(client, farm, "Ponds", "Stocking_Date")["input"] == "date"
    progress = field(client, farm, "Tasks_Operations", "Progress_Percent")
    assert (progress["input"], progress["min"], progress["max"]) == ("number", 0, 100)


def test_notes_are_optional(client, farm):
    assert not field(client, farm, "Feed_Logs", "Notes")["required"]


def test_yes_no_columns_keep_other_workbook_values(client, farm):
    manager = find(client, farm, "Access_Levels", "Level_Name", "Manager")
    response = client.patch(f"{url(farm, 'Access_Levels')}/{manager['id']}", json={"data": {"Level_Name": "Supervisor"}})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["View_Financials"] == "Limited"


# --- business rules ----------------------------------------------------------------


def test_end_date_cannot_be_before_start(client, farm):
    assert "can't be before" in errors(create(client, farm, "Ponds", {**POND, "Planned_Harvest_Date": "2026-09-01"}))["Planned_Harvest_Date"]
    task = {"Task_Name": "x", "Assigned_To": "R", "Start_Date": "2026-10-11", "Due_Date": "2026-10-01", "Status": "Done", "Progress_Percent": 0}
    assert "Due Date can't be before Start Date" in errors(create(client, farm, "Tasks_Operations", task))["Due_Date"]


def test_used_quantity_cannot_exceed_opening_plus_received(client, farm):
    material = {"Material_Name": "Bricks", "Opening_Stock": 100, "Received_Qty": 50, "Reorder_Level": 20, "Unit_Cost_INR": 8}
    message = errors(create(client, farm, "Materials", {**material, "Used_Qty": 151}))["Used_Qty"]
    assert "can't exceed Opening Stock + Received QTY (150)" in message
    assert create(client, farm, "Materials", {**material, "Used_Qty": 150}).status_code == 201
    # Editing an existing row is checked too, including when supply is lowered.
    cement = find(client, farm, "Materials", "Material_ID", "MAT-001")
    assert errors(client.patch(f"{url(farm, 'Materials')}/{cement['id']}", json={"data": {"Received_Qty": 100}}))["Used_Qty"]


def _stock(client, farm, item):
    return find(client, farm, "Feed_Inventory", "Feed_Item_ID", item)["data"]["Stock_Kg"]


FEED = {"Pond_ID": "POND-001", "Feed_Date": "2026-10-11", "Recorded_By": "Ravi Kumar"}


def test_feed_log_cannot_use_more_than_stock(client, farm):
    message = errors(create(client, farm, "Feed_Logs", {**FEED, "Feed_Item_ID": "FEED-002", "Quantity_Kg": 621}))["Quantity_Kg"]
    assert "Only 620 available for FEED-002" in message
    assert _stock(client, farm, "FEED-002") == 620  # nothing changed


def test_feed_logs_keep_inventory_in_step(client, farm):
    log = create(client, farm, "Feed_Logs", {**FEED, "Feed_Item_ID": "FEED-002", "Quantity_Kg": 100}).json()
    assert _stock(client, farm, "FEED-002") == 520
    log_url = f"{url(farm, 'Feed_Logs')}/{log['id']}"
    client.patch(log_url, json={"data": {"Quantity_Kg": 150}})
    assert _stock(client, farm, "FEED-002") == 470
    # Its own earlier usage counts as available when editing: 470 + 150 = 620.
    assert client.patch(log_url, json={"data": {"Quantity_Kg": 620}}).status_code == 200
    assert _stock(client, farm, "FEED-002") == 0
    assert client.patch(log_url, json={"data": {"Quantity_Kg": 621}}).status_code == 422
    # Moving the log to another item gives the stock back.
    client.patch(log_url, json={"data": {"Feed_Item_ID": "FEED-003", "Quantity_Kg": 50}})
    assert (_stock(client, farm, "FEED-002"), _stock(client, farm, "FEED-003")) == (620, 350)
    assert client.delete(log_url).status_code == 204
    assert _stock(client, farm, "FEED-003") == 400
    item = find(client, farm, "Feed_Inventory", "Feed_Item_ID", "FEED-003")
    history = client.get(f"{url(farm, 'Feed_Inventory')}/{item['id']}/activity").json()["history"]
    assert any(e["comment"] and e["comment"].startswith("Stock adjusted by feed log") for e in history)


def test_stock_rule_drives_the_form_limit(client, farm):
    spec = field(client, farm, "Feed_Logs", "Quantity_Kg")
    assert spec["max_from"]["from"] == "Feed_Item_ID" and spec["max_from"]["available"]["FEED-002"] == 620
    assert field(client, farm, "Materials", "Used_Qty")["max_sum"] == ["Opening_Stock", "Received_Qty"]


def test_calculated_field_hints_and_chart_titles_are_readable(client, farm):
    total = field(client, farm, "Feed_Logs", "Total_Cost_INR")
    assert total["computed"] == "Total Cost (INR) = Quantity (kg) × Unit Cost (INR per kg)"
    titles = [c["title"] for c in client.get(f"/api/workbooks/{farm}/portal").json()["charts"]]
    assert titles and not [t for t in titles if "_" in t or "(inr)" in t]
