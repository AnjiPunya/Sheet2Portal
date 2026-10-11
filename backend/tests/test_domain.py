"""Deterministic business-domain detection (drives the dashboard banner image)."""

import importlib.util
from pathlib import Path

import pytest

from app.services.analysis.domain import DOMAIN_KEYWORDS, GENERIC, detect_domain, domain_scores
from app.services.analysis.engine import build_portal_config
from app.services.analysis.types import SheetData

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _demo_workbook(script: str):
    spec = importlib.util.spec_from_file_location(script, _SCRIPTS / script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    wb = module.build_workbook()
    sheets = [ws.title for ws in wb.worksheets]
    columns = [cell.value for ws in wb.worksheets for cell in ws[1] if cell.value]
    return sheets, columns


@pytest.mark.parametrize(
    ("script", "expected"),
    [("generate_demo_data.py", "construction"), ("generate_demo_data_retail.py", "retail")],
)
def test_demo_workbooks(script, expected):
    sheets, columns = _demo_workbook(script)
    assert detect_domain("Portal", sheets, columns) == expected


@pytest.mark.parametrize(
    ("expected", "title", "sheets", "columns"),
    [
        (
            "aquaculture",
            "Farm Ops",
            ["Ponds", "Stocking", "Water Quality", "Harvests"],
            ["Pond ID", "Species", "Fingerlings Stocked", "Dissolved Oxygen", "pH", "Biomass (kg)", "FCR"],
        ),
        (
            "agriculture",
            "Kharif 2026",
            ["Fields", "Crops", "Inputs"],
            ["Field Name", "Acres", "Crop", "Seed Variety", "Fertilizer (kg)", "Yield"],
        ),
        (
            "healthcare",
            "City Clinic",
            ["Patients", "Appointments", "Prescriptions"],
            ["Patient Name", "Doctor", "Appointment Date", "Diagnosis", "Medication"],
        ),
        (
            "construction",
            "Lakeview Developers",
            ["Properties", "Tenants", "Leases"],
            ["Property Name", "Unit", "Tenant Name", "Lease Start", "Monthly Rent"],
        ),
        (
            "retail",
            "Shop",
            ["Products", "Orders"],
            ["SKU", "Product Name", "Price", "Stock Qty", "Customer Name"],
        ),
    ],
)
def test_each_supported_domain(expected, title, sheets, columns):
    assert detect_domain(title, sheets, columns) == expected


def test_unknown_workbook_is_generic():
    assert detect_domain("Book1", ["Sheet1"], ["Name", "Value", "Date", "Notes"]) == GENERIC


def test_empty_workbook_is_generic():
    assert detect_domain("", [], []) == GENERIC


def test_thin_evidence_is_generic():
    # A single column mention isn't enough to theme a whole portal.
    assert detect_domain("Book1", ["Sheet1"], ["Name", "Price"]) == GENERIC


def test_tie_between_domains_is_generic():
    scores = domain_scores("", ["Patients", "Products"], [])
    assert scores["healthcare"] == scores["retail"]
    assert detect_domain("", ["Patients", "Products"], []) == GENERIC


def test_header_styles_are_normalised():
    for columns in (["pond_id", "dissolved_oxygen", "fish_count"], ["pondId", "dissolvedOxygen", "fishCount"]):
        assert detect_domain("", ["Data"], columns) == "aquaculture", columns


def test_keywords_match_whole_words_not_substrings():
    # "fryer" must not count as aquaculture "fry"; "bedrock" not healthcare "bed".
    assert domain_scores("", [], ["Fryer Model", "Bedrock Depth", "Wardrobe"])["aquaculture"] == 0
    assert domain_scores("", [], ["Fryer Model", "Bedrock Depth", "Wardrobe"])["healthcare"] == 0


def test_detection_is_deterministic():
    sheets, columns = _demo_workbook("generate_demo_data.py")
    assert len({detect_domain("Portal", sheets, columns) for _ in range(20)}) == 1


def test_every_domain_has_keywords():
    assert DOMAIN_KEYWORDS and all(DOMAIN_KEYWORDS.values())
    assert GENERIC not in DOMAIN_KEYWORDS


def test_portal_config_carries_domain_without_touching_kpis():
    sheet = SheetData(
        name="Patients",
        columns=[("Patient Name", "string", 1.0), ("Doctor", "string", 1.0), ("Bill Amount", "int", 1.0)],
        rows=[{"Patient Name": "A", "Doctor": "X", "Bill Amount": 100}, {"Patient Name": "B", "Doctor": "Y", "Bill Amount": 50}],
    )
    config = build_portal_config("City Clinic", [sheet])
    assert config.domain == "healthcare"
    assert {k.label: k.value for k in config.entities[0].kpis}["Total Bill Amount"] == 150


def test_portal_api_exposes_domain(client, tmp_path):
    spec = importlib.util.spec_from_file_location("retail", _SCRIPTS / "generate_demo_data_retail.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / "retail.xlsx"
    module.build_workbook().save(path)
    with open(path, "rb") as f:
        workbook_id = client.post("/api/workbooks", files={"file": (path.name, f, "application/octet-stream")}).json()["id"]
    config = client.get(f"/api/workbooks/{workbook_id}/portal").json()
    assert config["domain"] == "retail"
