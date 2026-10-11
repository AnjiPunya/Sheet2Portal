"""Chat references use record names, link to the right record, and offer
related-record actions -- for every entity type, in text chat and voice."""

import json
import uuid

import pytest

from app.models.record import Record
from app.models.worksheet import Worksheet
from app.services.ai.base import ChatMessage, ChatResult, ToolCall
from app.services.ai.orchestrator import extract_references
from app.services.ai.references import build_index, name_records_in_text, resolve_references
from app.services.ai.tools import ChatContext, execute_tool
from app.services.analysis.engine import build_portal_config
from app.services.analysis.types import SheetData
from tests.test_business_rules import farm  # noqa: F401  (fixture)
from tests.test_records_crud import records_url, upload_demo

# --- unit: names, duplicates, missing records -----------------------------------


def _ctx(sheets: list[SheetData]) -> ChatContext:
    config = build_portal_config("T", sheets)
    records = {s.name: [Record(id=uuid.uuid4(), worksheet_id=uuid.uuid4(), row_index=i, data=row) for i, row in enumerate(s.rows)] for s in sheets}
    return ChatContext(config=config, records_by_entity=records)


PROJECTS = SheetData(
    name="Projects",
    columns=[("Project_ID", "string", 1.0), ("Project_Name", "string", 1.0), ("Location", "string", 1.0), ("Status", "string", 1.0)],
    rows=[
        {"Project_ID": "PRJ-001", "Project_Name": "Green Meadows Apartments", "Location": "Kompally", "Status": "In Progress"},
        {"Project_ID": "PRJ-002", "Project_Name": "Lakeview Villas", "Location": "Shamirpet", "Status": "At Risk"},
        {"Project_ID": "PRJ-003", "Project_Name": "Lakeview Villas", "Location": "Madhapur", "Status": "In Progress"},
    ],
)
TASKS = SheetData(
    name="Tasks",
    columns=[("Task_ID", "string", 1.0), ("Project_ID", "string", 1.0), ("Task_Name", "string", 1.0), ("Status", "string", 1.0)],
    rows=[
        {"Task_ID": "TSK-001", "Project_ID": "PRJ-001", "Task_Name": "Site clearing", "Status": "Completed"},
        {"Task_ID": "TSK-002", "Project_ID": "PRJ-001", "Task_Name": "Foundation", "Status": "In Progress"},
        {"Task_ID": "TSK-003", "Project_ID": "PRJ-002", "Task_Name": "Villa framing", "Status": "Not Started"},
    ],
)


def _id_of(ctx: ChatContext, sheet: str, column: str, value: str) -> str:
    return str(next(r.id for r in ctx.records_by_entity[sheet] if r.data[column] == value))


def test_records_are_named_by_their_name_column():
    ctx = _ctx([PROJECTS, TASKS])
    assert ctx.name(_id_of(ctx, "Projects", "Project_ID", "PRJ-001")) == "Green Meadows Apartments"
    assert ctx.name(_id_of(ctx, "Tasks", "Task_ID", "TSK-002")) == "Foundation"


def test_duplicate_names_are_disambiguated_by_id_code():
    ctx = _ctx([PROJECTS, TASKS])
    assert ctx.name(_id_of(ctx, "Projects", "Project_ID", "PRJ-002")) == "Lakeview Villas (PRJ-002)"
    assert ctx.name(_id_of(ctx, "Projects", "Project_ID", "PRJ-003")) == "Lakeview Villas (PRJ-003)"


def test_references_to_missing_or_mismatched_records_are_dropped():
    ctx = _ctx([PROJECTS, TASKS])
    real = _id_of(ctx, "Projects", "Project_ID", "PRJ-001")
    refs = [
        {"worksheet": "Projects", "record_id": real},
        {"worksheet": "Projects", "record_id": str(uuid.uuid4())},  # deleted
        {"worksheet": "Tasks", "record_id": real},  # wrong sheet: never relinked
    ]
    resolved = resolve_references(ctx.index, refs)
    assert [r["label"] for r in resolved] == ["Green Meadows Apartments"]


def test_related_actions_with_counts():
    ctx = _ctx([PROJECTS, TASKS])
    ref = resolve_references(ctx.index, [{"worksheet": "Projects", "record_id": _id_of(ctx, "Projects", "Project_ID", "PRJ-001")}])[0]
    assert ref["entity_label"] == "Project"
    assert ref["actions"][0] == {"kind": "details", "label": "View details", "worksheet": "Projects"}
    assert {"kind": "related", "label": "View Tasks", "worksheet": "Tasks", "count": 2} in ref["actions"]
    # A project with no tasks gets no "View Tasks" action.
    lone = resolve_references(ctx.index, [{"worksheet": "Projects", "record_id": _id_of(ctx, "Projects", "Project_ID", "PRJ-003")}])[0]
    assert [a["kind"] for a in lone["actions"]] == ["details"]


def test_tool_results_carry_names_for_records_and_references():
    ctx = _ctx([PROJECTS, TASKS])
    result = execute_tool("list_records", {"worksheet": "Tasks"}, ctx, 50)
    task = next(r for r in result["records"] if r["data"]["Task_ID"] == "TSK-001")
    assert task["label"] == "Site clearing"
    assert task["references"]["Project_ID"] == "Green Meadows Apartments · Kompally"
    count = execute_tool("aggregate", {"worksheet": "Tasks", "operation": "count", "filters": [{"field": "Project_ID", "operator": "eq", "value": "PRJ-001"}]}, ctx, 50)
    assert set(count["matched_records"]) == {"Site clearing", "Foundation"}


# --- unit: answer text ----------------------------------------------------------------


def test_answer_text_uses_names_not_ids():
    ctx = _ctx([PROJECTS, TASKS])
    rid = _id_of(ctx, "Projects", "Project_ID", "PRJ-001")
    index = ctx.index
    assert name_records_in_text(f"See record {rid}.", index) == "See record Green Meadows Apartments."
    assert name_records_in_text(f"Projects #{rid[:6]} is on track.", index) == "Green Meadows Apartments is on track."
    assert name_records_in_text(f"Check #{rid[:6]}", index) == "Check Green Meadows Apartments"
    assert name_records_in_text("PRJ-001 has 2 tasks.", index) == "Green Meadows Apartments has 2 tasks."


def test_codes_kept_when_name_given_or_ids_requested():
    index = _ctx([PROJECTS, TASKS]).index
    assert name_records_in_text("Green Meadows Apartments (PRJ-001) has 2 tasks.", index) == "Green Meadows Apartments (PRJ-001) has 2 tasks."
    assert name_records_in_text("PRJ-001", index, question="What is the project ID?") == "PRJ-001"


def test_unknown_hex_and_codes_left_alone():
    index = _ctx([PROJECTS, TASKS]).index
    assert name_records_in_text("Colour #abcdef and PRJ-999.", index) == "Colour #abcdef and PRJ-999."


# --- API: text chat (voice uses the same extract_references(ctx=...)) -----------------


class ScriptedProvider:
    name = "fake"

    def __init__(self, tool: str, args: dict, answer):
        self.tool, self.args, self.answer = tool, args, answer
        self.seen: list[list[ChatMessage]] = []

    async def chat(self, messages, tools=None):
        self.seen.append(list(messages))
        if not any(m.role == "tool" for m in messages):
            return ChatResult(message=ChatMessage(role="assistant", tool_calls=[ToolCall(id="c1", name=self.tool, arguments=self.args)]), finish_reason="tool_calls")
        tool_result = json.loads(next(m.content for m in reversed(messages) if m.role == "tool"))
        return ChatResult(message=ChatMessage(role="assistant", content=self.answer(tool_result)), finish_reason="stop")


def _chat(client, monkeypatch, workbook_id, provider, messages):
    from app.api.routes import chat as chat_route

    monkeypatch.setattr(chat_route, "get_provider", lambda settings, requested=None: provider)
    response = client.post(f"/api/workbooks/{workbook_id}/chat", json={"messages": messages})
    assert response.status_code == 200, response.text
    return response.json()


def test_chat_references_are_named_and_actionable(client, monkeypatch, tmp_path):
    workbook_id = upload_demo(client, tmp_path)
    # The "model" lazily cites the record by its internal id -- the answer must still read by name.
    provider = ScriptedProvider(
        "list_records",
        {"worksheet": "Projects", "filters": [{"field": "Project Name", "operator": "eq", "value": "Lakeview Luxury Villas"}]},
        lambda result: f"Found Projects #{result['records'][0]['id'][:6]} ({result['records'][0]['id']}).",
    )
    body = _chat(client, monkeypatch, workbook_id, provider, [{"role": "user", "content": "Show Lakeview"}])
    assert body["message"] == "Found Lakeview Luxury Villas (Lakeview Luxury Villas)."
    ref = body["references"][0]
    assert ref["label"] == "Lakeview Luxury Villas" and ref["entity_label"] == "Project"
    labels = {a["label"]: a.get("count") for a in ref["actions"]}
    assert labels["View details"] is None
    assert labels["View Tasks"] == 2 and labels["View Purchase Requests"] == 2
    assert {"View Materials", "View Expenses", "View Issues"} <= set(labels)

    # The link is the real record: opening it returns that project.
    detail = client.get(f"{records_url(workbook_id, 'Projects')}/{ref['record_id']}").json()
    assert detail["data"]["Project Name"] == "Lakeview Luxury Villas"
    # "View Tasks" opens exactly that project's tasks.
    tasks = client.get(records_url(workbook_id, "Tasks"), params={"related_worksheet": "Projects", "related_record_id": ref["record_id"]}).json()
    assert tasks["total"] == 2


def test_follow_up_question_keeps_using_names(client, monkeypatch, tmp_path):
    workbook_id = upload_demo(client, tmp_path)
    provider = ScriptedProvider(
        "list_records",
        {"worksheet": "Tasks", "search": "Lakeview"},
        lambda result: "Tasks: " + ", ".join(r["label"] for r in result["records"]),
    )
    history = [
        {"role": "user", "content": "Which project is at risk?"},
        {"role": "assistant", "content": "Lakeview Luxury Villas is at risk."},
        {"role": "user", "content": "What are its tasks?"},
    ]
    body = _chat(client, monkeypatch, workbook_id, provider, history)
    assert "Tasks:" in body["message"]
    sent = provider.seen[0]
    assert any("Lakeview Luxury Villas" in (m.content or "") for m in sent)  # prior answer reached the model by name


def test_references_never_cross_workbooks(client, make_client, monkeypatch, tmp_path):
    mine = upload_demo(client, tmp_path)
    provider = ScriptedProvider("list_records", {"worksheet": "Projects"}, lambda r: "ok")
    ref = _chat(client, monkeypatch, mine, provider, [{"role": "user", "content": "projects"}])["references"][0]
    other = make_client("other@example.com")
    assert other.get(f"{records_url(mine, 'Projects')}/{ref['record_id']}").status_code == 404


def test_deleted_record_reference_returns_404_not_another_record(client, monkeypatch, tmp_path):
    workbook_id = upload_demo(client, tmp_path)
    provider = ScriptedProvider("list_records", {"worksheet": "Issues"}, lambda r: "ok")
    ref = _chat(client, monkeypatch, workbook_id, provider, [{"role": "user", "content": "issues"}])["references"][0]
    url = f"{records_url(workbook_id, 'Issues')}/{ref['record_id']}"
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404


@pytest.mark.parametrize(
    ("sheet", "id_column", "id_value", "expected"),
    [
        ("Ponds", "Pond_ID", "POND-001", "North Pond"),
        ("Feed_Inventory", "Feed_Item_ID", "FEED-002", "Shrimp Grower 35"),
        ("Feed_Logs", "Feed_Log_ID", "FD-001", "FD-001"),  # logs have no name: their code is the name
        ("Suppliers_Buyers", "Party_ID", "SUP-001", "Bluewater Feeds"),
        ("Materials", "Material_ID", "MAT-002", "TMT Steel 12mm"),
        ("Purchase_Requests", "Request_ID", "REQ-001", "OPC Cement 50kg"),
        ("Tasks_Operations", "Task_ID", "TSK-002", "Retest oxygen"),
        ("Water_Quality", "Reading_ID", "WQ-001", "WQ-001"),  # a reading is named by its code, not its time
    ],
)
def test_every_entity_type_resolves_to_a_name(client, farm, sheet, id_column, id_value, expected):  # noqa: F811
    with client.test_sessionmaker() as db:
        from app.api.routes.chat import _load_chat_context
        from app.api.routes.portal import _load_workbook_for_portal
        from app.models.user import User

        user = db.query(User).filter(User.email == "owner@example.com").one()
        workbook = _load_workbook_for_portal(db, uuid.UUID(farm), user.tenant_id)
        ctx = _load_chat_context(db, workbook)
        rid = next(str(r.id) for r in ctx.records_by_entity[sheet] if r.data[id_column] == id_value)
        refs = extract_references([{"result": {"worksheet": sheet, "id": rid}}], ctx=ctx)
        assert refs[0]["label"] == expected


def test_value_link_related_action_opens_the_right_records(client, farm):  # noqa: F811
    rows = client.get(records_url(farm, "Feed_Inventory")).json()["records"]
    grower = next(r for r in rows if r["data"]["Feed_Item_ID"] == "FEED-002")
    logs = client.get(records_url(farm, "Feed_Logs"), params={"related_worksheet": "Feed_Inventory", "related_record_id": grower["id"]}).json()
    assert {r["data"]["Feed_Log_ID"] for r in logs["records"]} == {"FD-001", "FD-002"}
    with client.test_sessionmaker() as db:
        assert db.query(Worksheet).filter(Worksheet.name == "Feed_Logs").count() == 1
