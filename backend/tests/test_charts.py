"""Dashboard charts: chosen from the data, consistent with KPI cards, never
meaningless, and updated after record changes and approvals."""

from datetime import date, timedelta

from app.services.analysis.charts import amount_over_time, build_charts
from app.services.analysis.engine import build_portal_config
from app.services.analysis.types import SheetData
from tests.test_records_crud import PR, VALID_PR, create, records_url, upload_demo


def _portal(client, workbook_id):
    return client.get(f"/api/workbooks/{workbook_id}/portal").json()


def _chart(config, kind, entity):
    return next((c for c in config["charts"] if c["kind"] == kind and c["entity"] == entity), None)


def _kpi(config, suffix):
    return next(k["value"] for k in config["kpis"] + config["alerts"] if k["key"].endswith(suffix))


def test_construction_demo_gets_the_expected_charts(client, tmp_path):
    config = _portal(client, upload_demo(client, tmp_path))
    kinds = {(c["kind"], c["entity"]) for c in config["charts"]}
    assert ("grouped_bar", "Projects") in kinds
    assert ("status_stack", PR) in kinds
    assert ("time_columns", "Expenses") in kinds
    assert ("status_bars", "Projects") in kinds
    assert ("status_bars", "Tasks") in kinds


def test_chart_totals_match_kpi_cards(client, tmp_path):
    config = _portal(client, upload_demo(client, tmp_path))
    budget = _chart(config, "grouped_bar", "Projects")
    assert sum(i["values"][0] for i in budget["items"]) == _kpi(config, "Projects:sum:Budget")
    assert sum(i["values"][1] for i in budget["items"]) == _kpi(config, "Projects:sum:Spent")
    expenses = _chart(config, "time_columns", "Expenses")
    assert sum(p["value"] for p in expenses["points"]) == expenses["total"] == _kpi(config, "Expenses:sum:Amount")
    approval = _chart(config, "status_stack", PR)
    assert sum(s["value"] for s in approval["segments"]) == _kpi(config, f"{PR}:count")


def test_approval_chart_uses_status_semantics(client, tmp_path):
    approval = _chart(_portal(client, upload_demo(client, tmp_path)), "status_stack", PR)
    assert {s["label"]: s["status"] for s in approval["segments"]} == {
        "Approved": "good", "Pending Approval": "warning", "Rejected": "critical",
    }
    assert {s["label"]: s["value"] for s in approval["segments"]} == {"Approved": 1, "Pending Approval": 4, "Rejected": 1}


def test_charts_update_after_create_and_approve(client, tmp_path):
    workbook_id = upload_demo(client, tmp_path)
    record_id = create(client, workbook_id, PR, VALID_PR).json()["id"]
    approval = _chart(_portal(client, workbook_id), "status_stack", PR)
    assert next(s["value"] for s in approval["segments"] if s["label"] == "Pending Approval") == 5
    client.post(f"{records_url(workbook_id, PR)}/{record_id}/decision", json={"action": "approve"})
    approval = _chart(_portal(client, workbook_id), "status_stack", PR)
    values = {s["label"]: s["value"] for s in approval["segments"]}
    assert (values["Pending Approval"], values["Approved"]) == (4, 2)


def test_budget_chart_updates_after_edit(client, tmp_path):
    workbook_id = upload_demo(client, tmp_path)
    page = client.get(records_url(workbook_id, "Projects")).json()["records"]
    orchid = next(r for r in page if r["data"]["Project Name"] == "Orchid Commercial Fit-out")
    client.patch(f"{records_url(workbook_id, 'Projects')}/{orchid['id']}", json={"data": {"Spent": 19000000}})
    budget = _chart(_portal(client, workbook_id), "grouped_bar", "Projects")
    item = next(i for i in budget["items"] if i["label"] == "Orchid Commercial Fit-out")
    assert item["values"] == [18500000, 19000000] and item["flag"] == "over"


def test_retail_demo_skips_meaningless_charts(client, tmp_path):
    config = _portal(client, upload_demo(client, tmp_path, "generate_demo_data_retail.py"))
    kinds = {(c["kind"], c["entity"]) for c in config["charts"]}
    assert ("time_columns", "Orders") in kinds
    assert not any(kind == "grouped_bar" for kind, _ in kinds)  # no budget/actual columns
    assert ("time_columns", "Customers") not in kinds  # lifetime "Total Spent" by signup date says nothing


def _sheet(rows, columns):
    return SheetData(name="Payments", columns=columns, rows=rows)


def test_time_chart_needs_several_dated_rows_and_periods():
    columns = [("Payee", "string", 1.0), ("Amount", "int", 1.0), ("Date", "date", 1.0)]
    today = date(2026, 10, 1)
    one_period = [{"Payee": f"P{i}", "Amount": 10, "Date": today.isoformat()} for i in range(3)]
    config = build_portal_config("T", [_sheet(one_period, columns)])
    assert amount_over_time(config.entities[0], one_period) is None
    spread = [{"Payee": f"P{i}", "Amount": 10 * (i + 1), "Date": (today + timedelta(days=i * 3)).isoformat()} for i in range(4)]
    config = build_portal_config("T", [_sheet(spread, columns)])
    chart = amount_over_time(config.entities[0], spread)
    assert chart["unit"] == "day" and chart["total"] == 100
    assert len(chart["points"]) == 10  # continuous axis includes empty days


def test_bucket_size_follows_date_span():
    columns = [("Payee", "string", 1.0), ("Amount", "int", 1.0), ("Date", "date", 1.0)]
    start = date(2024, 1, 15)
    rows = [{"Payee": f"P{i}", "Amount": 5, "Date": (start + timedelta(days=i * 90)).isoformat()} for i in range(4)]
    config = build_portal_config("T", [_sheet(rows, columns)])
    assert amount_over_time(config.entities[0], rows)["unit"] == "month"


def test_no_charts_for_a_bare_sheet():
    rows = [{"Name": "A", "Notes": "x"}, {"Name": "B", "Notes": "y"}]
    config = build_portal_config("T", [SheetData(name="S", columns=[("Name", "string", 1.0), ("Notes", "string", 1.0)], rows=rows)])
    assert build_charts(config, {"S": rows}) == []
