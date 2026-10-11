import uuid

import pytest

from app.models.record import Record
from app.services.ai.tools import ChatContext, ToolValidationError, execute_tool
from app.services.analysis.engine import build_portal_config
from app.services.analysis.types import SheetData

MAX_PAGE_SIZE = 50


def _record(data: dict) -> Record:
    return Record(id=uuid.uuid4(), worksheet_id=uuid.uuid4(), row_index=0, data=data)


@pytest.fixture
def ctx() -> ChatContext:
    projects = SheetData(
        name="Projects",
        columns=[("Project Name", "string", 1.0), ("Status", "string", 1.0), ("Budget", "int", 1.0), ("Spent", "int", 1.0)],
        rows=[
            {"Project Name": "Alpha Tower", "Status": "In Progress", "Budget": 100000, "Spent": 40000},
            {"Project Name": "Beta Villas", "Status": "At Risk", "Budget": 50000, "Spent": 60000},
            {"Project Name": "Gamma Mall", "Status": "In Progress", "Budget": 200000, "Spent": 150000},
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
    config = build_portal_config("Test Portal", [projects, tasks])
    records_by_entity = {
        "Projects": [_record(r) for r in projects.rows],
        "Tasks": [_record(r) for r in tasks.rows],
    }
    return ChatContext(config=config, records_by_entity=records_by_entity)


def test_list_entities_exposes_schema(ctx):
    result = execute_tool("list_entities", {}, ctx, MAX_PAGE_SIZE)
    names = {e["worksheet"] for e in result["entities"]}
    assert names == {"Projects", "Tasks"}
    assert any(r["from_entity"] == "Tasks" and r["to_entity"] == "Projects" for r in result["relationships"])


def test_list_records_returns_all_rows(ctx):
    result = execute_tool("list_records", {"worksheet": "Projects"}, ctx, MAX_PAGE_SIZE)
    assert result["total"] == 3
    assert len(result["records"]) == 3
    assert all("id" in r and "data" in r for r in result["records"])


def test_list_records_search(ctx):
    result = execute_tool("list_records", {"worksheet": "Projects", "search": "Alpha"}, ctx, MAX_PAGE_SIZE)
    assert result["total"] == 1
    assert result["records"][0]["data"]["Project Name"] == "Alpha Tower"


def test_list_records_filter(ctx):
    result = execute_tool(
        "list_records",
        {"worksheet": "Projects", "filters": [{"field": "Status", "operator": "eq", "value": "In Progress"}]},
        ctx,
        MAX_PAGE_SIZE,
    )
    assert result["total"] == 2


def test_list_records_pagination(ctx):
    result = execute_tool("list_records", {"worksheet": "Projects", "page": 1, "page_size": 2}, ctx, MAX_PAGE_SIZE)
    assert len(result["records"]) == 2
    assert result["total"] == 3


def test_list_records_page_size_capped_server_side(ctx):
    result = execute_tool("list_records", {"worksheet": "Projects", "page_size": 9999}, ctx, max_page_size=2)
    assert result["page_size"] == 2
    assert len(result["records"]) == 2


def test_list_records_unknown_worksheet_rejected(ctx):
    with pytest.raises(ToolValidationError, match="Unknown worksheet"):
        execute_tool("list_records", {"worksheet": "DoesNotExist"}, ctx, MAX_PAGE_SIZE)


def test_list_records_unknown_field_in_filter_rejected(ctx):
    with pytest.raises(ToolValidationError, match="Unknown field"):
        execute_tool(
            "list_records",
            {"worksheet": "Projects", "filters": [{"field": "NotAColumn", "operator": "eq", "value": "x"}]},
            ctx,
            MAX_PAGE_SIZE,
        )


def test_list_records_unknown_operator_rejected(ctx):
    with pytest.raises(ToolValidationError, match="Unknown operator"):
        execute_tool(
            "list_records",
            {"worksheet": "Projects", "filters": [{"field": "Status", "operator": "DROP TABLE", "value": "x"}]},
            ctx,
            MAX_PAGE_SIZE,
        )


def test_get_record_returns_match(ctx):
    target = ctx.records_by_entity["Projects"][0]
    result = execute_tool("get_record", {"worksheet": "Projects", "record_id": str(target.id)}, ctx, MAX_PAGE_SIZE)
    assert result["data"]["Project Name"] == "Alpha Tower"


def test_get_record_unknown_id_rejected(ctx):
    with pytest.raises(ToolValidationError, match="not found"):
        execute_tool("get_record", {"worksheet": "Projects", "record_id": str(uuid.uuid4())}, ctx, MAX_PAGE_SIZE)


def test_get_record_cannot_cross_worksheets(ctx):
    task_record = ctx.records_by_entity["Tasks"][0]
    with pytest.raises(ToolValidationError, match="not found"):
        execute_tool("get_record", {"worksheet": "Projects", "record_id": str(task_record.id)}, ctx, MAX_PAGE_SIZE)


def test_aggregate_sum_is_deterministic(ctx):
    result = execute_tool("aggregate", {"worksheet": "Projects", "operation": "sum", "field": "Budget"}, ctx, MAX_PAGE_SIZE)
    assert result["value"] == 350000


def test_aggregate_count(ctx):
    result = execute_tool("aggregate", {"worksheet": "Projects", "operation": "count"}, ctx, MAX_PAGE_SIZE)
    assert result["value"] == 3


def test_aggregate_avg(ctx):
    result = execute_tool("aggregate", {"worksheet": "Projects", "operation": "avg", "field": "Budget"}, ctx, MAX_PAGE_SIZE)
    assert result["value"] == pytest.approx(350000 / 3, rel=1e-6)


def test_aggregate_with_filter(ctx):
    result = execute_tool(
        "aggregate",
        {
            "worksheet": "Projects",
            "operation": "sum",
            "field": "Spent",
            "filters": [{"field": "Status", "operator": "eq", "value": "In Progress"}],
        },
        ctx,
        MAX_PAGE_SIZE,
    )
    assert result["value"] == 190000  # 40000 + 150000, excludes the "At Risk" project


def test_aggregate_rejects_non_numeric_field(ctx):
    with pytest.raises(ToolValidationError, match="not numeric"):
        execute_tool("aggregate", {"worksheet": "Projects", "operation": "sum", "field": "Status"}, ctx, MAX_PAGE_SIZE)


def test_aggregate_requires_field_for_sum(ctx):
    with pytest.raises(ToolValidationError, match="'field' is required"):
        execute_tool("aggregate", {"worksheet": "Projects", "operation": "sum"}, ctx, MAX_PAGE_SIZE)


def test_aggregate_invalid_operation_rejected(ctx):
    with pytest.raises(ToolValidationError, match="operation"):
        execute_tool("aggregate", {"worksheet": "Projects", "operation": "median", "field": "Budget"}, ctx, MAX_PAGE_SIZE)


def test_traverse_relationship_finds_related_tasks(ctx):
    alpha = next(r for r in ctx.records_by_entity["Projects"] if r.data["Project Name"] == "Alpha Tower")
    result = execute_tool("traverse_relationship", {"worksheet": "Projects", "record_id": str(alpha.id)}, ctx, MAX_PAGE_SIZE)
    tasks_group = next(g for g in result["related"] if g["entity"] == "Tasks")
    task_names = {r["data"]["Task Name"] for r in tasks_group["records"]}
    assert task_names == {"Pour foundation", "Final inspection"}


def test_unknown_tool_name_rejected(ctx):
    with pytest.raises(ToolValidationError, match="Unknown tool"):
        execute_tool("delete_everything", {}, ctx, MAX_PAGE_SIZE)


def test_tool_args_must_be_object(ctx):
    with pytest.raises(ToolValidationError, match="JSON object"):
        execute_tool("list_entities", "not a dict", ctx, MAX_PAGE_SIZE)  # type: ignore[arg-type]


# Groq validates tool-call arguments against these schemas on its side, and
# models often send optional arguments as explicit nulls.


def test_count_with_null_field_counts_rows(ctx):
    result = execute_tool("aggregate", {"worksheet": "Projects", "operation": "count", "field": None}, ctx, MAX_PAGE_SIZE)
    assert result["value"] == 3


def test_count_with_null_field_and_null_filters(ctx):
    result = execute_tool(
        "aggregate", {"worksheet": "Projects", "operation": "count", "field": None, "filters": None}, ctx, MAX_PAGE_SIZE
    )
    assert result["value"] == 3


def test_sum_with_null_field_is_a_validation_error(ctx):
    with pytest.raises(ToolValidationError, match="'field' is required"):
        execute_tool("aggregate", {"worksheet": "Projects", "operation": "sum", "field": None}, ctx, MAX_PAGE_SIZE)


def test_list_records_accepts_null_optional_arguments(ctx):
    result = execute_tool(
        "list_records",
        {"worksheet": "Projects", "search": None, "filters": None, "page": None, "page_size": None},
        ctx,
        MAX_PAGE_SIZE,
    )
    assert result["total"] == 3
    assert result["page"] == 1


def test_optional_tool_arguments_allow_null_in_schema():
    from app.services.ai.tools import TOOL_SPECS

    def allows_null(prop: dict) -> bool:
        types = prop.get("type")
        return types == "null" or (isinstance(types, list) and "null" in types)

    for spec in TOOL_SPECS:
        properties = spec.parameters.get("properties", {})
        required = set(spec.parameters.get("required", []))
        for name, prop in properties.items():
            if name not in required:
                assert allows_null(prop), f"{spec.name}.{name} is optional but rejects null"
