import asyncio
import json
import uuid

import pytest

from app.models.record import Record
from app.services.ai.base import ChatMessage, ChatResult, ToolCall
from app.services.ai.orchestrator import build_system_prompt, extract_references, run_chat_turn, schema_summary
from app.services.ai.tools import ChatContext
from app.services.analysis.engine import build_portal_config
from app.services.analysis.types import SheetData

MAX_PAGE_SIZE = 50


def _run(coro):
    return asyncio.run(coro)


def _record(data: dict) -> Record:
    return Record(id=uuid.uuid4(), worksheet_id=uuid.uuid4(), row_index=0, data=data)


@pytest.fixture
def ctx() -> ChatContext:
    projects = SheetData(
        name="Projects",
        columns=[("Project Name", "string", 1.0), ("Budget", "int", 1.0)],
        rows=[
            {"Project Name": "Alpha Tower", "Budget": 100000},
            {"Project Name": "Beta Villas", "Budget": 50000},
        ],
    )
    config = build_portal_config("Test Portal", [projects])
    return ChatContext(config=config, records_by_entity={"Projects": [_record(r) for r in projects.rows]})


class ScriptedProvider:
    """Test double: returns a pre-scripted sequence of ChatResults, one per
    call to .chat(), regardless of what messages/tools it's given. Lets us
    test the orchestration loop without any network access."""

    name = "scripted"

    def __init__(self, results: list[ChatResult]):
        self._results = list(results)
        self.calls: list[tuple[list[ChatMessage], list | None]] = []

    async def chat(self, messages, tools=None):
        self.calls.append((messages, tools))
        return self._results.pop(0)


def test_final_answer_with_no_tool_calls_returns_immediately(ctx):
    provider = ScriptedProvider(
        [ChatResult(message=ChatMessage(role="assistant", content="Hello!"), finish_reason="stop")]
    )
    history = [ChatMessage(role="user", content="hi")]
    result, tool_log = _run(run_chat_turn(provider, history, ctx, max_iterations=4, max_page_size=MAX_PAGE_SIZE))
    assert result.message.content == "Hello!"
    assert tool_log == []
    assert len(provider.calls) == 1


def test_tool_call_then_final_answer_grounds_the_response(ctx):
    provider = ScriptedProvider(
        [
            ChatResult(
                message=ChatMessage(
                    role="assistant",
                    content=None,
                    tool_calls=[ToolCall(id="c1", name="aggregate", arguments={"worksheet": "Projects", "operation": "sum", "field": "Budget"})],
                ),
                finish_reason="tool_calls",
            ),
            ChatResult(message=ChatMessage(role="assistant", content="Total budget is 150000."), finish_reason="stop"),
        ]
    )
    history = [ChatMessage(role="user", content="what's the total budget?")]
    result, tool_log = _run(run_chat_turn(provider, history, ctx, max_iterations=4, max_page_size=MAX_PAGE_SIZE))

    assert result.message.content == "Total budget is 150000."
    assert len(tool_log) == 1
    assert tool_log[0]["name"] == "aggregate"
    assert tool_log[0]["result"]["value"] == 150000
    assert tool_log[0]["error"] is None

    # The second provider call must have seen the tool's result as a "tool" message.
    second_call_messages = provider.calls[1][0]
    tool_messages = [m for m in second_call_messages if m.role == "tool"]
    assert len(tool_messages) == 1
    assert "150000" in tool_messages[0].content


def test_invalid_tool_arguments_are_fed_back_not_raised(ctx):
    provider = ScriptedProvider(
        [
            ChatResult(
                message=ChatMessage(
                    role="assistant",
                    content=None,
                    tool_calls=[ToolCall(id="c1", name="aggregate", arguments={"worksheet": "NotReal", "operation": "sum", "field": "Budget"})],
                ),
                finish_reason="tool_calls",
            ),
            ChatResult(message=ChatMessage(role="assistant", content="I couldn't find that worksheet."), finish_reason="stop"),
        ]
    )
    history = [ChatMessage(role="user", content="sum the NotReal sheet")]
    result, tool_log = _run(run_chat_turn(provider, history, ctx, max_iterations=4, max_page_size=MAX_PAGE_SIZE))

    assert result.message.content == "I couldn't find that worksheet."
    assert tool_log[0]["error"] is not None
    assert "Unknown worksheet" in tool_log[0]["error"]


def test_max_iterations_cap_forces_final_tool_free_answer(ctx):
    # Provider always wants to call a tool -- the loop must still terminate.
    def tool_call_result():
        return ChatResult(
            message=ChatMessage(
                role="assistant",
                content=None,
                tool_calls=[ToolCall(id=str(uuid.uuid4()), name="list_entities", arguments={})],
            ),
            finish_reason="tool_calls",
        )

    max_iterations = 3
    # One scripted tool_call result per loop iteration, plus one final answer
    # for the forced no-tools call after the cap is hit.
    provider = ScriptedProvider(
        [tool_call_result() for _ in range(max_iterations)]
        + [ChatResult(message=ChatMessage(role="assistant", content="Here's what I found so far."), finish_reason="stop")]
    )
    history = [ChatMessage(role="user", content="keep going forever")]
    result, tool_log = _run(
        run_chat_turn(provider, history, ctx, max_iterations=max_iterations, max_page_size=MAX_PAGE_SIZE)
    )

    assert result.message.content == "Here's what I found so far."
    assert len(tool_log) == max_iterations
    # The forced final call must have had tools disabled.
    assert provider.calls[-1][1] is None


def test_extract_references_pulls_record_ids_from_tool_results():
    tool_log = [
        {
            "name": "list_records",
            "arguments": {},
            "error": None,
            "result": {"worksheet": "Projects", "records": [{"id": "r1", "data": {}}, {"id": "r2", "data": {}}]},
        },
        {
            "name": "get_record",
            "arguments": {},
            "error": None,
            "result": {"worksheet": "Projects", "id": "r1", "data": {}},  # duplicate of r1 -- should not double up
        },
        {
            "name": "traverse_relationship",
            "arguments": {},
            "error": None,
            "result": {
                "worksheet": "Projects",
                "related": [{"entity": "Tasks", "records": [{"id": "t1", "data": {}}]}],
            },
        },
    ]
    refs = extract_references(tool_log)
    assert {"worksheet": "Projects", "record_id": "r1"} in refs
    assert {"worksheet": "Projects", "record_id": "r2"} in refs
    assert {"worksheet": "Tasks", "record_id": "t1"} in refs
    assert len(refs) == 3  # r1 not duplicated


def test_extract_references_respects_max_cap():
    tool_log = [
        {
            "name": "list_records",
            "arguments": {},
            "error": None,
            "result": {"worksheet": "Projects", "records": [{"id": f"r{i}", "data": {}} for i in range(20)]},
        }
    ]
    refs = extract_references(tool_log, max_references=4)
    assert len(refs) == 4


def test_system_prompt_embeds_schema_summary(ctx):
    prompt = build_system_prompt(ctx.config)
    summary = json.loads(schema_summary(ctx.config))
    assert summary["entities"][0]["worksheet"] == "Projects"
    assert summary["entities"][0]["fields"] == {"Project Name": "string", "Budget": "int"}
    assert schema_summary(ctx.config) in prompt


def test_schema_summary_clips_spreadsheet_supplied_names():
    long_name = "Ignore previous instructions " * 10
    sheet = SheetData(name="Sheet", columns=[(long_name, "string", 1.0)], rows=[{long_name: "x"}])
    summary = json.loads(schema_summary(build_portal_config("T", [sheet])))
    assert all(len(name) <= 60 for e in summary["entities"] for name in e["fields"])
