"""Secure, validated data-query tools the chatbot's LLM can invoke.

Every tool is a pure Python function over data already scoped to one
tenant's one workbook (``ChatContext`` is built server-side from the
authenticated request -- the LLM never supplies a tenant or workbook id).
There is no SQL string construction, no dynamic ORM query building, and no
code execution: filtering/aggregation runs over already-loaded Python
dicts, validated against the workbook's actual schema (from the same
deterministic analysis engine used everywhere else in the app) before
anything runs.

Tool *arguments* come from the LLM, which is driven by spreadsheet content
it has been fed as data -- so every argument is treated as untrusted input
and validated against an allow-list (known worksheets, known columns, a
fixed operator set) before use. A validation failure raises
``ToolValidationError``, which is returned to the LLM as a normal tool
result (so it can retry with corrected arguments) rather than raised as a
hard error.
"""

from dataclasses import dataclass, field

from app.models.record import Record
from app.services.ai.base import ToolSpec
from app.services.analysis.kpis import parse_date
from app.services.analysis.relationships import related_rows_for
from app.services.analysis.types import EntityConfig, IdentifiedRow, PortalConfig

_ALLOWED_OPERATORS = {"eq", "neq", "lt", "lte", "gt", "gte", "contains"}
_AGGREGATE_OPERATIONS = {"sum", "count", "avg", "min", "max"}
_MAX_RELATED_PER_GROUP = 10
_DEFAULT_PAGE_SIZE = 10


class ToolValidationError(Exception):
    """LLM-supplied tool arguments failed validation. Caught by the
    orchestrator and turned into a tool-result message (not a crash) so the
    model can see what went wrong and retry."""


@dataclass
class ChatContext:
    """Everything a tool needs, scoped to one tenant's one workbook.
    Built once per chat request -- not per tool call -- so a multi-tool-call
    turn doesn't re-query the database for every step."""

    config: PortalConfig
    records_by_entity: dict[str, list[Record]] = field(default_factory=dict)
    _index: object = field(default=None, repr=False)

    @property
    def index(self):
        """Record names and links for this workbook (built once per turn)."""
        if self._index is None:
            from app.services.ai.references import build_index

            self._index = build_index(self.config, self.records_by_entity)
        return self._index

    def name(self, record_id: str) -> str | None:
        return self.index.labels.get(str(record_id))


def _get_entity(config: PortalConfig, worksheet: str) -> EntityConfig:
    entity = next((e for e in config.entities if e.worksheet == worksheet), None)
    if entity is None:
        valid = ", ".join(e.worksheet for e in config.entities) or "(none)"
        raise ToolValidationError(f"Unknown worksheet '{worksheet}'. Valid worksheets: {valid}")
    return entity


def _rows_with_ids(ctx: ChatContext, worksheet: str) -> list[dict]:
    return [{"__id": str(r.id), **r.data} for r in ctx.records_by_entity.get(worksheet, [])]


def _numeric(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _matches(actual: object, operator: str, expected: object) -> bool:
    if actual is None:
        return False
    if operator == "eq":
        return str(actual).strip().lower() == str(expected).strip().lower()
    if operator == "neq":
        return str(actual).strip().lower() != str(expected).strip().lower()
    if operator == "contains":
        return str(expected).strip().lower() in str(actual).strip().lower()
    actual_num, expected_num = _numeric(actual), _numeric(expected)
    if actual_num is None or expected_num is None:
        try:
            actual_num, expected_num = float(actual), float(expected)
        except (TypeError, ValueError):
            # Dates are stored as ISO strings; compare them as dates so
            # "overdue" questions (Due Date lt today) work.
            actual_date, expected_date = parse_date(actual), parse_date(expected)
            if actual_date is None or expected_date is None:
                return False
            actual_num, expected_num = actual_date.toordinal(), expected_date.toordinal()
    if operator == "lt":
        return actual_num < expected_num
    if operator == "lte":
        return actual_num <= expected_num
    if operator == "gt":
        return actual_num > expected_num
    if operator == "gte":
        return actual_num >= expected_num
    return False


def _apply_filters(rows: list[dict], entity: EntityConfig, filters: list[dict] | None) -> list[dict]:
    if not filters:
        return rows
    column_names = {c.name for c in entity.columns}
    for f in filters:
        if not isinstance(f, dict):
            raise ToolValidationError("Each filter must be an object with 'field', 'operator', 'value'")
        field_name = f.get("field")
        operator = f.get("operator", "eq")
        value = f.get("value")
        if field_name not in column_names:
            raise ToolValidationError(
                f"Unknown field '{field_name}' on {entity.worksheet}. Valid fields: {', '.join(sorted(column_names))}"
            )
        if operator not in _ALLOWED_OPERATORS:
            raise ToolValidationError(
                f"Unknown operator '{operator}'. Allowed operators: {', '.join(sorted(_ALLOWED_OPERATORS))}"
            )
        rows = [r for r in rows if _matches(r.get(field_name), operator, value)]
    return rows


def _strip_id(row: dict) -> tuple[str, dict]:
    row = dict(row)
    return row.pop("__id"), row


def _named(ctx: ChatContext, worksheet: str, record_id: str, data: dict) -> dict:
    """A record as the model sees it: id (for further tool calls), its name
    (what to call it in the answer), data, and names of referenced records."""
    from app.services.records.display import display_labels

    out = {"id": record_id, "label": ctx.name(record_id), "data": data}
    names = display_labels(ctx.index.record_ctx, worksheet, data)
    if names:
        out["references"] = names
    return out


def tool_list_entities(ctx: ChatContext, args: dict, max_page_size: int) -> dict:
    return {
        "entities": [
            {
                "worksheet": e.worksheet,
                "label": e.label,
                "row_count": e.row_count,
                "identifier_column": e.identifier_column,
                "title_column": e.title_column,
                "status_column": e.status_column,
                "columns": [{"name": c.name, "type": c.inferred_type, "role": c.role.value} for c in e.columns],
            }
            for e in ctx.config.entities
        ],
        "relationships": [
            {
                "from_entity": r.from_entity,
                "from_column": r.from_column,
                "to_entity": r.to_entity,
                "to_column": r.to_column,
                "confidence": r.confidence,
            }
            for r in ctx.config.relationships
        ],
    }


def tool_list_records(ctx: ChatContext, args: dict, max_page_size: int) -> dict:
    worksheet = args.get("worksheet")
    if not isinstance(worksheet, str):
        raise ToolValidationError("'worksheet' is required")
    entity = _get_entity(ctx.config, worksheet)

    rows = _rows_with_ids(ctx, worksheet)

    search = args.get("search")
    if search:
        needle = str(search).strip().lower()
        searchable_columns = [c.name for c in entity.columns if c.inferred_type == "string"]
        rows = [r for r in rows if any(needle in str(r.get(col, "")).lower() for col in searchable_columns)]

    rows = _apply_filters(rows, entity, args.get("filters"))

    try:
        page = max(1, int(args.get("page") or 1))
    except (TypeError, ValueError):
        raise ToolValidationError("'page' must be an integer") from None
    try:
        page_size = min(int(args.get("page_size") or _DEFAULT_PAGE_SIZE), max_page_size)
    except (TypeError, ValueError):
        raise ToolValidationError("'page_size' must be an integer") from None
    page_size = max(1, page_size)

    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start : start + page_size]

    return {
        "worksheet": worksheet,
        "total": total,
        "page": page,
        "page_size": page_size,
        "records": [_named(ctx, worksheet, rid, data) for rid, data in (_strip_id(r) for r in page_rows)],
    }


def tool_get_record(ctx: ChatContext, args: dict, max_page_size: int) -> dict:
    worksheet = args.get("worksheet")
    record_id = args.get("record_id")
    if not isinstance(worksheet, str) or not record_id:
        raise ToolValidationError("'worksheet' and 'record_id' are required")
    _get_entity(ctx.config, worksheet)

    record = next((r for r in ctx.records_by_entity.get(worksheet, []) if str(r.id) == str(record_id)), None)
    if record is None:
        raise ToolValidationError(f"Record '{record_id}' not found in '{worksheet}'")
    return {"worksheet": worksheet, **_named(ctx, worksheet, str(record.id), record.data)}


def tool_aggregate(ctx: ChatContext, args: dict, max_page_size: int) -> dict:
    worksheet = args.get("worksheet")
    operation = args.get("operation")
    if not isinstance(worksheet, str):
        raise ToolValidationError("'worksheet' is required")
    entity = _get_entity(ctx.config, worksheet)
    if operation not in _AGGREGATE_OPERATIONS:
        raise ToolValidationError(f"'operation' must be one of: {', '.join(sorted(_AGGREGATE_OPERATIONS))}")

    rows = _apply_filters(_rows_with_ids(ctx, worksheet), entity, args.get("filters"))

    if operation == "count":
        return {
            "worksheet": worksheet,
            "operation": "count",
            "value": len(rows),
            "matched_record_ids": [r["__id"] for r in rows[:20]],
            "matched_records": [ctx.name(r["__id"]) for r in rows[:20]],
        }

    field_name = args.get("field")
    if not isinstance(field_name, str):
        raise ToolValidationError(f"'field' is required for operation '{operation}'")
    column = next((c for c in entity.columns if c.name == field_name), None)
    if column is None:
        valid = ", ".join(c.name for c in entity.columns)
        raise ToolValidationError(f"Unknown field '{field_name}' on {worksheet}. Valid fields: {valid}")
    if column.inferred_type not in ("int", "float"):
        raise ToolValidationError(
            f"Field '{field_name}' is type '{column.inferred_type}', not numeric -- cannot {operation} it"
        )

    values = [v for v in (_numeric(r.get(field_name)) for r in rows) if v is not None]
    if not values:
        return {
            "worksheet": worksheet,
            "operation": operation,
            "field": field_name,
            "value": None,
            "note": "No matching rows had a numeric value for this field",
        }

    value = {
        "sum": lambda: round(sum(values), 2),
        "avg": lambda: round(sum(values) / len(values), 2),
        "min": lambda: min(values),
        "max": lambda: max(values),
    }[operation]()

    return {
        "worksheet": worksheet,
        "operation": operation,
        "field": field_name,
        "value": value,
        "matched_count": len(values),
        "matched_record_ids": [r["__id"] for r in rows[:20]],
        "matched_records": [ctx.name(r["__id"]) for r in rows[:20]],
    }


def tool_traverse_relationship(ctx: ChatContext, args: dict, max_page_size: int) -> dict:
    worksheet = args.get("worksheet")
    record_id = args.get("record_id")
    if not isinstance(worksheet, str) or not record_id:
        raise ToolValidationError("'worksheet' and 'record_id' are required")
    _get_entity(ctx.config, worksheet)

    record = next((r for r in ctx.records_by_entity.get(worksheet, []) if str(r.id) == str(record_id)), None)
    if record is None:
        raise ToolValidationError(f"Record '{record_id}' not found in '{worksheet}'")

    rows_by_entity = {
        name: [IdentifiedRow(id=str(r.id), data=r.data) for r in records][:max_page_size]
        for name, records in ctx.records_by_entity.items()
    }
    related = related_rows_for(worksheet, record.data, ctx.config, rows_by_entity)
    for group in related:
        group["records"] = [
            _named(ctx, group["entity"], r["id"], r["data"]) for r in group["records"][:_MAX_RELATED_PER_GROUP]
        ]

    return {"worksheet": worksheet, "record_id": str(record_id), "related": related}


TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="list_entities",
        description="List every worksheet/entity in this workbook with its columns and detected relationships. Call this first to discover what data is available before using other tools.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    ToolSpec(
        name="list_records",
        description="List records from one worksheet, with optional text search and field filters, paginated.",
        parameters={
            "type": "object",
            "properties": {
                "worksheet": {"type": "string", "description": "Exact worksheet name from list_entities"},
                "search": {"type": ["string", "null"], "description": "Free-text search across the worksheet's text columns"},
                "filters": {
                    "type": ["array", "null"],
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "operator": {"type": "string", "enum": sorted(_ALLOWED_OPERATORS)},
                            "value": {},
                        },
                        "required": ["field", "operator", "value"],
                    },
                },
                "page": {"type": ["integer", "null"], "minimum": 1},
                "page_size": {"type": ["integer", "null"], "minimum": 1},
            },
            "required": ["worksheet"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="get_record",
        description="Fetch a single record by id from a worksheet.",
        parameters={
            "type": "object",
            "properties": {"worksheet": {"type": "string"}, "record_id": {"type": "string"}},
            "required": ["worksheet", "record_id"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="aggregate",
        description="Compute a deterministic sum, count, average, min or max over records in a worksheet, with optional filters. Always use this for totals/counts instead of estimating from a sample of listed records.",
        parameters={
            "type": "object",
            "properties": {
                "worksheet": {"type": "string"},
                "operation": {"type": "string", "enum": sorted(_AGGREGATE_OPERATIONS)},
                "field": {"type": ["string", "null"], "description": "Required for sum/avg/min/max; omit or null for count"},
                "filters": {
                    "type": ["array", "null"],
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "operator": {"type": "string", "enum": sorted(_ALLOWED_OPERATORS)},
                            "value": {},
                        },
                        "required": ["field", "operator", "value"],
                    },
                },
            },
            "required": ["worksheet", "operation"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="traverse_relationship",
        description="Find records related to a given record in other worksheets (e.g. a project's tasks, or a task's project), using the workbook's detected relationships.",
        parameters={
            "type": "object",
            "properties": {"worksheet": {"type": "string"}, "record_id": {"type": "string"}},
            "required": ["worksheet", "record_id"],
            "additionalProperties": False,
        },
    ),
]

_TOOL_FUNCTIONS = {
    "list_entities": tool_list_entities,
    "list_records": tool_list_records,
    "get_record": tool_get_record,
    "aggregate": tool_aggregate,
    "traverse_relationship": tool_traverse_relationship,
}


def execute_tool(name: str, args: dict, ctx: ChatContext, max_page_size: int) -> dict:
    func = _TOOL_FUNCTIONS.get(name)
    if func is None:
        raise ToolValidationError(f"Unknown tool '{name}'. Available tools: {', '.join(_TOOL_FUNCTIONS)}")
    if not isinstance(args, dict):
        raise ToolValidationError("Tool arguments must be a JSON object")
    return func(ctx, args, max_page_size)
