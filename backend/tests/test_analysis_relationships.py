from app.services.analysis.engine import build_portal_config
from app.services.analysis.types import SheetData


def _config():
    projects = SheetData(
        name="Projects",
        columns=[("Project Name", "string", 1.0), ("Status", "string", 1.0)],
        rows=[
            {"Project Name": "Alpha Tower", "Status": "In Progress"},
            {"Project Name": "Beta Villas", "Status": "At Risk"},
        ],
    )
    tasks = SheetData(
        name="Tasks",
        columns=[("Task Name", "string", 1.0), ("Project", "string", 1.0), ("Status", "string", 1.0)],
        rows=[
            {"Task Name": "Pour foundation", "Project": "Alpha Tower", "Status": "Open"},
            {"Task Name": "Install facade", "Project": "Beta Villas", "Status": "Open"},
            {"Task Name": "Final inspection", "Project": "Alpha Tower", "Status": "Done"},
        ],
    )
    return build_portal_config("Test Portal", [projects, tasks])


def test_relationship_detected_between_matching_entities():
    config = _config()
    assert len(config.relationships) == 1
    rel = config.relationships[0]
    assert rel.from_entity == "Tasks"
    assert rel.from_column == "Project"
    assert rel.to_entity == "Projects"
    assert rel.confidence == "high"
    assert rel.match_rate == 1.0


def test_foreign_key_column_is_not_used_as_status_or_identifier():
    config = _config()
    tasks_entity = next(e for e in config.entities if e.worksheet == "Tasks")
    assert tasks_entity.status_column == "Status"  # not the "Project" FK column
    project_col = next(c for c in tasks_entity.columns if c.name == "Project")
    assert project_col.role.value == "foreign_key"


def test_unrelated_sheets_produce_no_relationships():
    a = SheetData(name="Colors", columns=[("Name", "string", 1.0)], rows=[{"Name": "Red"}, {"Name": "Blue"}])
    b = SheetData(name="Sizes", columns=[("Name", "string", 1.0)], rows=[{"Name": "Small"}, {"Name": "Large"}])
    config = build_portal_config("Test", [a, b])
    assert config.relationships == []


def test_name_match_without_value_overlap_is_not_asserted():
    # Column is named like a match but its values never resolve in the
    # target sheet -- must not be reported as a relationship.
    projects = SheetData(
        name="Projects",
        columns=[("Project Name", "string", 1.0)],
        rows=[{"Project Name": "Alpha Tower"}, {"Project Name": "Beta Villas"}],
    )
    notes = SheetData(
        name="Notes",
        columns=[("Project", "string", 1.0)],
        rows=[{"Project": "Unrelated Thing"}, {"Project": "Another Unrelated Thing"}],
    )
    config = build_portal_config("Test", [projects, notes])
    assert config.relationships == []
