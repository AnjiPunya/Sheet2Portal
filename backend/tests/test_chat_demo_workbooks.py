"""End-to-end chatbot checks against the construction and retail demo
workbooks: real upload -> real portal analysis -> /chat endpoint -> real
tools. Only the LLM is scripted (no API keys in tests), and it echoes the
tool result back so the deterministic numbers can be asserted exactly.
"""

import importlib.util
import json
import uuid
from datetime import date
from pathlib import Path

import pytest

from app.services.ai.base import ChatMessage, ChatResult, ToolCall

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load_generator(filename: str):
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), _SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EchoToolProvider:
    """Calls one tool, then answers with that tool's raw JSON result."""

    name = "fake"

    def __init__(self, tool_name: str, arguments: dict):
        self._call = ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name=tool_name, arguments=arguments)
        self.seen_messages: list[ChatMessage] = []

    async def chat(self, messages, tools=None):
        self.seen_messages = list(messages)
        tool_messages = [m for m in messages if m.role == "tool"]
        if not tool_messages:
            return ChatResult(message=ChatMessage(role="assistant", tool_calls=[self._call]), finish_reason="tool_calls")
        return ChatResult(message=ChatMessage(role="assistant", content=tool_messages[-1].content), finish_reason="stop")


def _upload_demo(client, tmp_path, generator_file: str) -> str:
    path = tmp_path / generator_file.replace(".py", ".xlsx")
    _load_generator(generator_file).build_workbook().save(path)
    with open(path, "rb") as f:
        response = client.post(
            "/api/workbooks",
            files={"file": (path.name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def _ask_tool(client, monkeypatch, workbook_id: str, tool_name: str, arguments: dict) -> tuple[dict, dict]:
    from app.api.routes import chat as chat_route

    provider = EchoToolProvider(tool_name, arguments)
    monkeypatch.setattr(chat_route, "get_provider", lambda settings, requested=None: provider)
    response = client.post(
        f"/api/workbooks/{workbook_id}/chat", json={"messages": [{"role": "user", "content": "question"}]}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return json.loads(body["message"]), body


@pytest.fixture
def construction_id(client, tmp_path):
    return _upload_demo(client, tmp_path, "generate_demo_data.py")


@pytest.fixture
def retail_id(client, tmp_path):
    return _upload_demo(client, tmp_path, "generate_demo_data_retail.py")


def test_construction_total_budget(client, monkeypatch, construction_id):
    result, body = _ask_tool(
        client, monkeypatch, construction_id, "aggregate", {"worksheet": "Projects", "operation": "sum", "field": "Budget"}
    )
    assert result["value"] == 49_700_000 + 32_000_000 + 18_500_000
    assert len(body["references"]) == 3


def test_construction_pending_approvals(client, monkeypatch, construction_id):
    pending = [{"field": "Status", "operator": "eq", "value": "Pending Approval"}]
    count, _ = _ask_tool(
        client, monkeypatch, construction_id, "aggregate",
        {"worksheet": "Purchase Requests", "operation": "count", "filters": pending},
    )
    total, _ = _ask_tool(
        client, monkeypatch, construction_id, "aggregate",
        {"worksheet": "Purchase Requests", "operation": "sum", "field": "Amount", "filters": pending},
    )
    assert count["value"] == 4
    assert total["value"] == 840_000 + 348_000 + 32_000 + 80_000


def test_construction_pending_expenses(client, monkeypatch, construction_id):
    result, _ = _ask_tool(
        client, monkeypatch, construction_id, "aggregate",
        {"worksheet": "Expenses", "operation": "sum", "field": "Amount",
         "filters": [{"field": "Status", "operator": "eq", "value": "Pending"}]},
    )
    assert result["value"] == 980_000 + 610_000


def test_construction_overdue_tasks_by_date_filter(client, monkeypatch, construction_id):
    result, _ = _ask_tool(
        client, monkeypatch, construction_id, "list_records",
        {"worksheet": "Tasks", "filters": [
            {"field": "Status", "operator": "neq", "value": "Done"},
            {"field": "Due Date", "operator": "lt", "value": date.today().isoformat()},
        ]},
    )
    names = {r["data"]["Task Name"] for r in result["records"]}
    assert names == {"MEP Rough-in Villa 4-8", "Final Plumbing Inspection"}


def test_construction_project_to_tasks_relationship(client, monkeypatch, construction_id):
    projects, _ = _ask_tool(
        client, monkeypatch, construction_id, "list_records",
        {"worksheet": "Projects", "filters": [{"field": "Project Name", "operator": "eq", "value": "Lakeview Luxury Villas"}]},
    )
    project_id = projects["records"][0]["id"]
    related, _ = _ask_tool(
        client, monkeypatch, construction_id, "traverse_relationship", {"worksheet": "Projects", "record_id": project_id}
    )
    tasks = next(g for g in related["related"] if g["entity"] == "Tasks")
    assert {r["data"]["Task Name"] for r in tasks["records"]} == {"MEP Rough-in Villa 4-8", "Landscaping Phase 1"}


def test_retail_pending_order_value(client, monkeypatch, retail_id):
    result, _ = _ask_tool(
        client, monkeypatch, retail_id, "aggregate",
        {"worksheet": "Orders", "operation": "sum", "field": "Total Amount",
         "filters": [{"field": "Status", "operator": "eq", "value": "Pending"}]},
    )
    assert result["value"] == 3897 + 799


def test_retail_average_rating(client, monkeypatch, retail_id):
    result, _ = _ask_tool(
        client, monkeypatch, retail_id, "aggregate", {"worksheet": "Reviews", "operation": "avg", "field": "Rating"}
    )
    assert result["value"] == round((5 + 4 + 5) / 3, 2)


def test_retail_unknown_field_returns_validation_error_to_model(client, monkeypatch, retail_id):
    result, _ = _ask_tool(
        client, monkeypatch, retail_id, "aggregate", {"worksheet": "Orders", "operation": "sum", "field": "Budget"}
    )
    assert "Unknown field 'Budget'" in result["error"]


def test_construction_worksheet_from_other_workbook_is_rejected(client, monkeypatch, construction_id, retail_id):
    result, _ = _ask_tool(client, monkeypatch, retail_id, "list_records", {"worksheet": "Projects"})
    assert "Unknown worksheet 'Projects'" in result["error"]


def test_suggestions_differ_by_domain(client, construction_id, retail_id):
    construction = client.get(f"/api/workbooks/{construction_id}/chat/suggestions").json()["suggestions"]
    retail = client.get(f"/api/workbooks/{retail_id}/chat/suggestions").json()["suggestions"]
    assert construction and retail
    assert construction != retail
