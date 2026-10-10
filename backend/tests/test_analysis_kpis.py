from datetime import date, timedelta

from app.services.analysis.engine import build_portal_config
from app.services.analysis.types import SheetData


def test_budget_vs_actual_kpis():
    sheet = SheetData(
        name="Projects",
        columns=[("Project Name", "string", 1.0), ("Budget", "int", 1.0), ("Spent", "int", 1.0)],
        rows=[
            {"Project Name": "A", "Budget": 1000, "Spent": 800},
            {"Project Name": "B", "Budget": 2000, "Spent": 2500},
        ],
    )
    config = build_portal_config("Test", [sheet])
    entity = config.entities[0]
    kpi_by_label = {k.label: k for k in entity.kpis}

    assert kpi_by_label["Total Budget"].value == 3000
    assert kpi_by_label["Total Spent"].value == 3300
    assert kpi_by_label["Budget Used"].value == 110.0
    assert kpi_by_label["Projects Over Budget"].value == 1
    assert kpi_by_label["Projects Over Budget"].severity == "warning"


def test_low_stock_alert_requires_quantity_and_threshold():
    sheet = SheetData(
        name="Materials",
        columns=[
            ("Material Name", "string", 1.0),
            ("Quantity On Hand", "int", 1.0),
            ("Reorder Level", "int", 1.0),
        ],
        rows=[
            {"Material Name": "Cement", "Quantity On Hand": 10, "Reorder Level": 50},
            {"Material Name": "Steel", "Quantity On Hand": 100, "Reorder Level": 20},
        ],
    )
    config = build_portal_config("Test", [sheet])
    alert = next(a for a in config.alerts if a.key.endswith("low_stock"))
    assert alert.value == 1
    assert alert.severity == "critical"


def test_sum_kpi_label_avoids_double_total_when_column_already_says_total():
    sheet = SheetData(
        name="Customers",
        columns=[("Customer Name", "string", 1.0), ("Total Spent", "int", 1.0)],
        rows=[{"Customer Name": "A", "Total Spent": 100}, {"Customer Name": "B", "Total Spent": 200}],
    )
    config = build_portal_config("Test", [sheet])
    labels = [k.label for k in config.entities[0].kpis]
    assert "Total Spent" in labels
    assert "Total Total Spent" not in labels


def test_low_stock_derives_current_quantity_from_opening_received_used_flow():
    # No single "on-hand quantity" column exists -- only an opening balance
    # plus inbound/outbound movement, as in real inventory sheets. Picking
    # "Opening_Stock" alone (the first quantity-role column by position)
    # would silently misclassify this row: 500 opening is well above the
    # 200 reorder level, but net current stock (500 + 300 - 620 = 180) is
    # actually below it.
    sheet = SheetData(
        name="Materials",
        columns=[
            ("Material Name", "string", 1.0),
            ("Opening_Stock", "int", 1.0),
            ("Received_Qty", "int", 1.0),
            ("Used_Qty", "int", 1.0),
            ("Reorder_Level", "int", 1.0),
        ],
        rows=[
            {
                "Material Name": "Cement",
                "Opening_Stock": 500,
                "Received_Qty": 300,
                "Used_Qty": 620,
                "Reorder_Level": 200,
            },
            {
                "Material Name": "Steel",
                "Opening_Stock": 100,
                "Received_Qty": 50,
                "Used_Qty": 20,
                "Reorder_Level": 30,
            },
        ],
    )
    config = build_portal_config("Test", [sheet])
    entity = config.entities[0]

    assert entity.low_stock_strategy.type == "flow"
    assert entity.low_stock_strategy.opening_column == "Opening_Stock"

    alert = next(a for a in config.alerts if a.key.endswith("low_stock"))
    assert alert.value == 1


def test_no_low_stock_kpi_without_threshold_column():
    sheet = SheetData(
        name="Materials",
        columns=[("Material Name", "string", 1.0), ("Quantity On Hand", "int", 1.0)],
        rows=[{"Material Name": "Cement", "Quantity On Hand": 10}],
    )
    config = build_portal_config("Test", [sheet])
    assert not any("low_stock" in k.key for k in config.entities[0].kpis)


def test_overdue_excludes_completed_rows():
    past = (date.today() - timedelta(days=5)).isoformat()
    future = (date.today() + timedelta(days=5)).isoformat()
    sheet = SheetData(
        name="Tasks",
        columns=[
            ("Task Name", "string", 1.0),
            ("Due Date", "date", 1.0),
            ("Done", "bool", 1.0),
        ],
        rows=[
            {"Task Name": "Overdue and open", "Due Date": past, "Done": False},
            {"Task Name": "Overdue but done", "Due Date": past, "Done": True},
            {"Task Name": "Not due yet", "Due Date": future, "Done": False},
        ],
    )
    config = build_portal_config("Test", [sheet])
    alert = next(a for a in config.alerts if "overdue" in a.key)
    assert alert.value == 1


def test_risk_status_values_become_alerts():
    sheet = SheetData(
        name="Purchase Requests",
        columns=[("Item", "string", 1.0), ("Approval_Status", "string", 1.0)],
        rows=[
            {"Item": "Cement", "Approval_Status": "Pending Approval"},
            {"Item": "Steel", "Approval_Status": "Pending Approval"},
            {"Item": "Bricks", "Approval_Status": "Approved"},
        ],
    )
    config = build_portal_config("Test", [sheet])
    alert = next(a for a in config.alerts if a.label == "Pending Approval")
    assert alert.value == 2
    assert alert.severity == "warning"
    # "Approved" isn't a risk status -- it must not also produce an alert.
    assert not any(a.label == "Approved" for a in config.alerts)


def test_weak_status_guess_does_not_generate_alerts():
    # No name hint at all -- "Category" only looks like a status because it
    # happens to have low cardinality. That weak a signal shouldn't be
    # confident enough to raise an alert banner.
    sheet = SheetData(
        name="Items",
        columns=[("Name", "string", 1.0), ("Category", "string", 1.0)],
        rows=[
            {"Name": "A", "Category": "Open"},
            {"Name": "B", "Category": "Open"},
            {"Name": "C", "Category": "Closed"},
        ],
    )
    config = build_portal_config("Test", [sheet])
    assert config.alerts == []


def test_status_breakdown_flags_risk_values():
    sheet = SheetData(
        name="Issues",
        columns=[("Title", "string", 1.0), ("Status", "string", 1.0)],
        rows=[
            {"Title": "A", "Status": "Open"},
            {"Title": "B", "Status": "Resolved"},
            {"Title": "C", "Status": "Open"},
        ],
    )
    config = build_portal_config("Test", [sheet])
    breakdown = {item.value: item for item in config.entities[0].status_breakdown}
    assert breakdown["Open"].count == 2
    assert breakdown["Open"].is_risk is True
    assert breakdown["Resolved"].is_risk is False
