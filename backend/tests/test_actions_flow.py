"""Business actions through chat and voice: draft -> confirm -> execute.

The model is scripted (no real provider). What's under test is that the
model can only ever *prepare* drafts, and that execution happens only after
an explicit confirmation of the exact draft, re-checked on the server.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.action_draft import ActionDraft
from app.models.user import User
from app.services.ai.base import ChatMessage, ChatResult, ToolCall
from tests.conftest import DEFAULT_EMAIL
from tests.test_records_crud import find, records_url, upload_demo

PROJECT = {
    "Project Name": "Green Valley Apartments",
    "Type": "Residential High-Rise",
    "Manager": "Kiran Rao",
    "Location": "Kokapet, Hyderabad",
    "Status": "In Progress",
    "Budget": "5 crore",
    "Spent": 0,
    "Start Date": "2026-11-01",
    "End Date": "2028-03-31",
}
PR_FIELDS = {"Item": "TMT Steel Bars 12mm", "Project": "Green Meadows Apartments", "Requested By": "Asha Rao", "Quantity": 5, "Requested Date": "2026-10-11"}


class ScriptedProvider:
    """Returns the scripted results in order and records every message it was sent."""

    name = "fake"

    def __init__(self, results):
        self._results = list(results)
        self.seen: list[list[ChatMessage]] = []

    async def chat(self, messages, tools=None):
        self.seen.append(list(messages))
        self.tools = [t.name for t in tools or []]
        return self._results.pop(0)


class NoModel:
    """Fails the test if the model is called (yes/no must be deterministic)."""

    name = "none"

    async def chat(self, messages, tools=None):
        raise AssertionError("the model must not be called for a plain confirmation")


def propose(**args) -> ChatResult:
    return ChatResult(
        message=ChatMessage(role="assistant", content=None, tool_calls=[ToolCall(id=uuid.uuid4().hex[:8], name="propose_action", arguments=args)]),
        finish_reason="tool_calls",
    )


def say(text: str) -> ChatResult:
    return ChatResult(message=ChatMessage(role="assistant", content=text), finish_reason="stop")


@pytest.fixture
def wb(client, tmp_path):
    return upload_demo(client, tmp_path)


@pytest.fixture
def use_model(monkeypatch):
    from app.api.routes import chat as chat_route
    from app.api.routes import voice as voice_route

    def install(provider):
        monkeypatch.setattr(chat_route, "get_provider", lambda settings, requested=None: provider)
        monkeypatch.setattr(chat_route, "fallback_providers", lambda settings, name: [])
        monkeypatch.setattr(voice_route, "get_provider", lambda settings, requested=None: provider)
        monkeypatch.setattr(voice_route, "fallback_providers", lambda primary_name: [])
        return provider

    return install


def chat(client, wb, text, conv="conv-0001", pending=None, history=()):
    body = {"messages": [*history, {"role": "user", "content": text}], "conversation_id": conv}
    if pending:
        body["pending_action"] = {"draft_id": pending["draft_id"], "token": pending["token"]}
    response = client.post(f"/api/workbooks/{wb}/chat", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def confirm(client, wb, action, conv="conv-0001", token=None):
    return client.post(
        f"/api/workbooks/{wb}/actions/{action['draft_id']}/confirm",
        json={"token": token or action["token"], "conversation_id": conv},
    )


def project_names(client, wb):
    page = client.get(records_url(wb, "Projects"), params={"page_size": 200}).json()
    return [r["data"]["Project Name"] for r in page["records"]]


def set_role(client, role, email=DEFAULT_EMAIL):
    with client.test_sessionmaker() as db:
        db.query(User).filter(User.email == email).update({"role": role})
        db.commit()


def draft_project(client, wb, use_model, conv="conv-0001", fields=None):
    use_model(ScriptedProvider([propose(action="create", worksheet="Projects", fields=fields or PROJECT), say("Here's the draft. Shall I create it?")]))
    out = chat(client, wb, "Create a project called Green Valley Apartments with a budget of 5 crore", conv)
    assert out["action"]["state"] == "awaiting_confirmation", out["action"]
    return out["action"]


# --- Create Project ------------------------------------------------------------


def test_missing_fields_ask_for_clarification_and_nothing_is_created(client, wb, use_model):
    use_model(ScriptedProvider([propose(action="create", worksheet="Projects", fields={"Project Name": "Green Valley Apartments", "Budget": "5 crore"}), say("Which manager, location…?")]))
    out = chat(client, wb, "Create a project called Green Valley Apartments with a budget of 5 crore")
    action = out["action"]
    assert action["state"] == "clarification_required"
    assert action["token"] is None and action["draft_id"] is None
    missing = {m["name"] for m in action["missing"]}
    assert {"Manager", "Location", "Start Date"} <= missing
    assert "Green Valley Apartments" not in project_names(client, wb)


def test_answering_the_clarification_completes_the_same_draft(client, wb, use_model):
    use_model(ScriptedProvider([propose(action="create", worksheet="Projects", fields={"Project Name": "Green Valley Apartments", "Budget": "5 crore"}), say("Need more")]))
    chat(client, wb, "Create a project called Green Valley Apartments with a budget of 5 crore")
    rest = {k: v for k, v in PROJECT.items() if k not in ("Project Name", "Budget")}
    use_model(ScriptedProvider([propose(action="create", worksheet="Projects", fields=rest), say("Ready")]))
    action = chat(client, wb, "Manager Kiran Rao, Kokapet Hyderabad, …")["action"]
    assert action["state"] == "awaiting_confirmation"
    values = {f["name"]: f["value"] for f in action["preview"]["fields"]}
    assert values["Project Name"] == "Green Valley Apartments"  # kept from the first turn
    assert values["Budget"] == 50_000_000  # "5 crore" converted before the user confirms


def test_create_project_draft_then_spoken_yes_executes(client, wb, use_model):
    action = draft_project(client, wb, use_model)
    assert action["preview"]["action"] == "create" and action["preview"]["worksheet"] == "Projects"
    assert "Green Valley Apartments" not in project_names(client, wb), "a draft must not change data"
    use_model(NoModel())
    out = chat(client, wb, "Yes, go ahead", pending=action)
    assert out["action"]["state"] == "completed"
    assert out["provider"] == "actions"
    assert "Created project" in out["message"]
    assert "Green Valley Apartments" in project_names(client, wb)
    project = find(client, wb, "Projects", "Project Name", "Green Valley Apartments")
    assert project["data"]["Budget"] == 50_000_000


def test_completed_action_is_visible_in_dashboard_data(client, wb, use_model):
    before = client.get(f"/api/workbooks/{wb}/portal").json()
    action = draft_project(client, wb, use_model)
    assert confirm(client, wb, action).json()["action"]["state"] == "completed"
    after = client.get(f"/api/workbooks/{wb}/portal").json()
    count = lambda cfg: next(e["row_count"] for e in cfg["entities"] if e["worksheet"] == "Projects")  # noqa: E731
    assert count(after) == count(before) + 1


def test_model_never_sees_the_confirmation_token_and_has_no_execute_tool(client, wb, use_model):
    provider = ScriptedProvider([propose(action="create", worksheet="Projects", fields=PROJECT), say("Confirm?")])
    use_model(provider)
    action = chat(client, wb, "Create the Green Valley project")["action"]
    sent = json.dumps([[m.content for m in msgs] for msgs in provider.seen], default=str)
    assert action["token"] not in sent and action["draft_id"] not in sent
    assert "propose_action" in provider.tools and "cancel_action" in provider.tools
    assert not any("execute" in name or "confirm" in name for name in provider.tools)


# --- Create Purchase Request -----------------------------------------------------


def test_purchase_request_draft_shows_calculated_values_and_confirm_button_creates_it(client, wb, use_model):
    use_model(ScriptedProvider([propose(action="create", worksheet="Purchase Requests", fields=PR_FIELDS), say("Draft ready")]))
    action = chat(client, wb, "Raise a PR for 5 tonnes of TMT steel for Green Meadows")["action"]
    assert action["state"] == "awaiting_confirmation"
    values = {f["name"]: f for f in action["preview"]["fields"]}
    assert values["Amount"]["value"] == 5 * 42000 and values["Amount"]["computed"] is True
    assert values["PR ID"]["value"] == "PR-1007"
    assert values["Status"]["value"] == "Pending Approval"
    result = confirm(client, wb, action).json()
    assert result["action"]["state"] == "completed", result
    created = find(client, wb, "Purchase Requests", "PR ID", "PR-1007")
    assert created["data"]["Amount"] == 210000 and created["data"]["Status"] == "Pending Approval"


def test_unknown_reference_asks_again(client, wb, use_model):
    fields = {**PR_FIELDS, "Project": "Nowhere Towers"}
    use_model(ScriptedProvider([propose(action="create", worksheet="Purchase Requests", fields=fields), say("Which project?")]))
    action = chat(client, wb, "PR for steel for Nowhere Towers")["action"]
    assert action["state"] == "clarification_required"
    assert "Project" in action["errors"]


def test_unknown_field_goes_back_to_the_model_not_the_user(client, wb, use_model):
    provider = ScriptedProvider(
        [
            propose(action="create", worksheet="Purchase Requests", fields={**PR_FIELDS, "Colour": "red"}),
            propose(action="create", worksheet="Purchase Requests", fields=PR_FIELDS),
            say("Draft ready"),
        ]
    )
    use_model(provider)
    action = chat(client, wb, "PR for steel")["action"]
    assert action["state"] == "awaiting_confirmation"
    tool_results = [m.content for m in provider.seen[1] if m.role == "tool"]
    assert any("Unknown field" in (c or "") and "Valid fields" in (c or "") for c in tool_results)


# --- Telugu / mixed ---------------------------------------------------------------


def test_telugu_request_and_telugu_confirmation(client, wb, use_model):
    use_model(ScriptedProvider([propose(action="create", worksheet="Projects", fields={**PROJECT, "Budget": "5 కోట్లు"}), say("డ్రాఫ్ట్ సిద్ధం. సృష్టించమంటారా?")]))
    action = chat(client, wb, "గ్రీన్ వ్యాలీ అపార్ట్‌మెంట్స్ అనే ప్రాజెక్ట్ 5 కోట్ల బడ్జెట్‌తో సృష్టించు")["action"]
    assert {f["name"]: f["value"] for f in action["preview"]["fields"]}["Budget"] == 50_000_000
    use_model(NoModel())
    out = chat(client, wb, "అవును", pending=action)
    assert out["action"]["state"] == "completed"
    assert "పూర్తయింది" in out["message"]


def test_mixed_language_confirmation(client, wb, use_model):
    action = draft_project(client, wb, use_model)
    use_model(NoModel())
    out = chat(client, wb, "సరే, confirm", pending=action)
    assert out["action"]["state"] == "completed"


# --- correction / cancellation -----------------------------------------------------


def test_correction_creates_a_new_draft_and_the_old_confirmation_is_rejected(client, wb, use_model):
    first = draft_project(client, wb, use_model)
    use_model(ScriptedProvider([propose(action="create", worksheet="Projects", fields={"Budget": "6 crore"}), say("Updated. Confirm?")]))
    out = chat(client, wb, "Yes but make the budget 6 crore", pending=first)  # not a plain yes -> model
    second = out["action"]
    assert second["state"] == "awaiting_confirmation" and second["draft_id"] != first["draft_id"]
    assert {f["name"]: f["value"] for f in second["preview"]["fields"]}["Budget"] == 60_000_000
    stale = confirm(client, wb, first).json()["action"]
    assert stale["state"] == "failed" and stale["code"] == "DRAFT_SUPERSEDED"
    assert confirm(client, wb, second).json()["action"]["state"] == "completed"
    assert find(client, wb, "Projects", "Project Name", "Green Valley Apartments")["data"]["Budget"] == 60_000_000


def test_spoken_cancel_discards_the_draft(client, wb, use_model):
    action = draft_project(client, wb, use_model)
    use_model(NoModel())
    out = chat(client, wb, "వద్దు", pending=action)
    assert out["action"]["state"] == "cancelled"
    assert "Green Valley Apartments" not in project_names(client, wb)
    again = confirm(client, wb, action).json()["action"]
    assert again["state"] == "failed" and again["code"] == "DRAFT_CANCELLED"


def test_model_can_cancel_on_a_longer_request(client, wb, use_model):
    action = draft_project(client, wb, use_model)
    cancel_call = ChatResult(
        message=ChatMessage(role="assistant", content=None, tool_calls=[ToolCall(id="x1", name="cancel_action", arguments={})]),
        finish_reason="tool_calls",
    )
    use_model(ScriptedProvider([cancel_call, say("Cancelled.")]))
    out = chat(client, wb, "Actually forget about that project for now", pending=action)
    assert out["action"]["state"] == "cancelled"
    assert confirm(client, wb, action).json()["action"]["code"] == "DRAFT_CANCELLED"


# --- replay / expiry / binding ------------------------------------------------------


def test_replayed_confirmation_runs_only_once(client, wb, use_model):
    action = draft_project(client, wb, use_model)
    assert confirm(client, wb, action).json()["action"]["state"] == "completed"
    again = confirm(client, wb, action).json()["action"]
    assert again["state"] == "failed" and again["code"] == "ALREADY_EXECUTED"
    use_model(NoModel())
    spoken = chat(client, wb, "yes", pending=action)["action"]
    assert spoken["code"] == "ALREADY_EXECUTED"
    assert project_names(client, wb).count("Green Valley Apartments") == 1


def test_expired_draft_cannot_be_confirmed(client, wb, use_model):
    action = draft_project(client, wb, use_model)
    with client.test_sessionmaker() as db:
        db.query(ActionDraft).filter(ActionDraft.id == uuid.UUID(action["draft_id"])).update(
            {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}
        )
        db.commit()
    result = confirm(client, wb, action).json()["action"]
    assert result["state"] == "failed" and result["code"] == "DRAFT_EXPIRED"
    assert "Green Valley Apartments" not in project_names(client, wb)


def test_wrong_token_and_wrong_conversation_are_rejected(client, wb, use_model):
    action = draft_project(client, wb, use_model)
    assert confirm(client, wb, action, token="not-the-token").json()["action"]["code"] == "INVALID_CONFIRMATION"
    assert confirm(client, wb, action, conv="conv-other").json()["action"]["code"] == "DRAFT_MISMATCH"
    assert "Green Valley Apartments" not in project_names(client, wb)
    assert confirm(client, wb, action).json()["action"]["state"] == "completed"  # the real one still works


def test_another_user_cannot_confirm_my_draft(client, wb, use_model, make_client, tmp_path):
    action = draft_project(client, wb, use_model)
    other = make_client("other@example.com")
    assert confirm(other, wb, action).status_code == 404  # my workbook isn't visible to them
    (tmp_path / "other").mkdir()
    their_wb = upload_demo(other, tmp_path / "other")
    result = other.post(f"/api/workbooks/{their_wb}/actions/{action['draft_id']}/confirm", json={"token": action["token"]})
    assert result.json()["action"]["code"] == "DRAFT_NOT_FOUND"
    assert "Green Valley Apartments" not in project_names(client, wb)


def test_yes_without_a_pending_draft_goes_to_the_model(client, wb, use_model):
    use_model(ScriptedProvider([say("There's nothing waiting for confirmation.")]))
    out = chat(client, wb, "yes")
    assert out["action"] is None and out["provider"] == "fake"


# --- permissions / approvals ---------------------------------------------------------


def test_viewer_cannot_draft_a_create(client, wb, use_model):
    set_role(client, "viewer")
    use_model(ScriptedProvider([propose(action="create", worksheet="Projects", fields=PROJECT), say("You can't.")]))
    action = chat(client, wb, "Create a project")["action"]
    assert action["state"] == "failed" and action["code"] == "FORBIDDEN"
    with client.test_sessionmaker() as db:
        assert db.query(ActionDraft).filter(ActionDraft.status == "pending").count() == 0


def test_permission_is_rechecked_at_execution(client, wb, use_model):
    action = draft_project(client, wb, use_model)
    set_role(client, "viewer")
    result = confirm(client, wb, action).json()["action"]
    assert result["state"] == "failed" and result["code"] == "FORBIDDEN"
    set_role(client, "owner")
    assert "Green Valley Apartments" not in project_names(client, wb)


def test_approve_pending_purchase_request(client, wb, use_model):
    use_model(ScriptedProvider([propose(action="approve", worksheet="Purchase Requests", record="PR-1001"), say("Approve PR-1001?")]))
    action = chat(client, wb, "Approve PR-1001")["action"]
    assert action["preview"]["status_change"] == {"from": "Pending Approval", "to": "Approved"}
    assert find(client, wb, "Purchase Requests", "PR ID", "PR-1001")["data"]["Status"] == "Pending Approval"
    assert confirm(client, wb, action).json()["action"]["state"] == "completed"
    assert find(client, wb, "Purchase Requests", "PR ID", "PR-1001")["data"]["Status"] == "Approved"


def test_editor_cannot_approve(client, wb, use_model):
    set_role(client, "editor")
    use_model(ScriptedProvider([propose(action="approve", worksheet="Purchase Requests", record="PR-1001"), say("No permission")]))
    action = chat(client, wb, "Approve PR-1001")["action"]
    assert action["code"] == "FORBIDDEN"


def test_approver_can_approve_but_not_create(client, wb, use_model):
    set_role(client, "approver")
    use_model(ScriptedProvider([propose(action="create", worksheet="Purchase Requests", fields=PR_FIELDS), say("No")]))
    assert chat(client, wb, "Raise a PR")["action"]["code"] == "FORBIDDEN"
    use_model(ScriptedProvider([propose(action="reject", worksheet="Purchase Requests", record="PR-1002", comment="Over budget"), say("Reject?")]))
    action = chat(client, wb, "Reject PR-1002, over budget")["action"]
    assert action["preview"]["comment"] == "Over budget"
    assert confirm(client, wb, action).json()["action"]["state"] == "completed"
    assert find(client, wb, "Purchase Requests", "PR ID", "PR-1002")["data"]["Status"] == "Rejected"


def test_invalid_transition_is_refused_at_draft_time(client, wb, use_model):
    use_model(ScriptedProvider([propose(action="approve", worksheet="Purchase Requests", record="PR-1003"), say("Already approved")]))
    action = chat(client, wb, "Approve PR-1003")["action"]
    assert action["state"] == "failed" and action["code"] == "INVALID_TRANSITION"


def test_approval_decided_elsewhere_makes_the_draft_stale(client, wb, use_model):
    use_model(ScriptedProvider([propose(action="approve", worksheet="Purchase Requests", record="PR-1004"), say("Approve?")]))
    action = chat(client, wb, "Approve PR-1004")["action"]
    pr = find(client, wb, "Purchase Requests", "PR ID", "PR-1004")
    rejected = client.post(f"{records_url(wb, 'Purchase Requests')}/{pr['id']}/decision", json={"action": "reject"})
    assert rejected.status_code == 200
    result = confirm(client, wb, action).json()["action"]
    assert result["state"] == "failed" and result["code"] == "STALE_DRAFT"
    assert find(client, wb, "Purchase Requests", "PR ID", "PR-1004")["data"]["Status"] == "Rejected"


# --- edit / delete / targets ------------------------------------------------------


def test_status_update_with_contextual_record(client, wb, use_model):
    use_model(ScriptedProvider([propose(action="update", worksheet="Projects", record="Lakeview Luxury Villas", fields={"Status": "in progress"}), say("Change it?")]))
    action = chat(client, wb, "Change its status to in progress", history=[{"role": "user", "content": "Tell me about Lakeview"}, {"role": "assistant", "content": "Lakeview Luxury Villas is At Risk."}])["action"]
    change = action["preview"]["fields"][0]
    assert change["name"] == "Status" and change["previous"] == "At Risk" and change["value"] == "In Progress"
    assert confirm(client, wb, action).json()["action"]["state"] == "completed"
    assert find(client, wb, "Projects", "Project Name", "Lakeview Luxury Villas")["data"]["Status"] == "In Progress"


def test_ambiguous_target_lists_candidates(client, wb, use_model):
    action = draft_project(client, wb, use_model)
    confirm(client, wb, action)
    use_model(ScriptedProvider([propose(action="update", worksheet="Projects", record="Apartments", fields={"Spent": 10}), say("Which one?")]))
    result = chat(client, wb, "Set spent to 10 for the apartments project", conv="conv-0002")["action"]
    assert result["state"] == "clarification_required"
    labels = sorted(c["label"] for c in result["candidates"])
    assert labels == ["Green Meadows Apartments", "Green Valley Apartments"]


def test_record_not_found(client, wb, use_model):
    use_model(ScriptedProvider([propose(action="delete", worksheet="Projects", record="Nonexistent Plaza"), say("Not found")]))
    result = chat(client, wb, "Delete Nonexistent Plaza")["action"]
    assert result["state"] == "clarification_required" and result["candidates"] == []


def test_delete_of_referenced_record_is_refused(client, wb, use_model):
    use_model(ScriptedProvider([propose(action="delete", worksheet="Projects", record="Green Meadows Apartments"), say("Can't")]))
    result = chat(client, wb, "Delete Green Meadows")["action"]
    assert result["state"] == "failed" and result["code"] == "RECORD_IN_USE"


def test_delete_draft_names_record_and_consequence(client, wb, use_model):
    confirm(client, wb, draft_project(client, wb, use_model))
    use_model(ScriptedProvider([propose(action="delete", worksheet="Projects", record="Green Valley Apartments"), say("Delete it? This can't be undone.")]))
    action = chat(client, wb, "Delete Green Valley Apartments", conv="conv-0003")["action"]
    assert action["preview"]["record_label"] == "Green Valley Apartments"
    assert "can't be undone" in action["preview"]["consequences"][0]
    assert confirm(client, wb, action, conv="conv-0003").json()["action"]["state"] == "completed"
    assert "Green Valley Apartments" not in project_names(client, wb)


def test_failed_mutation_reports_failure_not_success(client, wb, use_model, monkeypatch):
    action = draft_project(client, wb, use_model)
    from app.services.records import service

    def boom(*args, **kwargs):
        raise service.RecordError(409, "RECORD_LOCKED", "Locked for audit.")

    monkeypatch.setattr(service, "create_record", boom)
    result = confirm(client, wb, action).json()
    assert result["action"]["state"] == "failed" and result["action"]["code"] == "RECORD_LOCKED"
    assert "didn't go through" in result["message"]
    assert confirm(client, wb, action).json()["action"]["code"] == "ALREADY_USED"


# --- voice ---------------------------------------------------------------------------


def voice(client, wb, text, conv="conv-0001", pending=None, mode="auto"):
    body = {"messages": [{"role": "user", "content": text}], "language_mode": mode, "conversation_id": conv}
    if pending:
        body["pending_action"] = {"draft_id": pending["draft_id"], "token": pending["token"]}
    response = client.post(f"/api/workbooks/{wb}/voice/respond", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_voice_shares_the_same_flow(client, wb, use_model):
    use_model(ScriptedProvider([propose(action="create", worksheet="Purchase Requests", fields=PR_FIELDS), say("PR draft ready. Confirm చేయమంటారా?")]))
    action = voice(client, wb, "Green Meadows కి 5 tonnes TMT steel PR raise చేయి")["action"]
    assert action["state"] == "awaiting_confirmation"
    use_model(NoModel())
    out = voice(client, wb, "అవును", pending=action)
    assert out["action"]["state"] == "completed" and out["provider"] == "actions"
    assert "పూర్తయింది" in out["message"] and out["speakable"]
    assert find(client, wb, "Purchase Requests", "PR ID", "PR-1007")


def test_choosing_a_candidate_by_its_label_resolves_it(client, wb, use_model):
    use_model(ScriptedProvider([propose(action="approve", worksheet="Purchase Requests", record="PR-1001 · TMT Steel Bars 12mm"), say("Approve?")]))
    action = chat(client, wb, "PR-1001 · TMT Steel Bars 12mm")["action"]
    assert action["state"] == "awaiting_confirmation"
    assert action["preview"]["record_label"] == "PR-1001 · TMT Steel Bars 12mm"


def test_draft_tells_the_user_about_stock_side_effects(client, use_model, tmp_path):
    from tests.test_business_rules import FARM, _book

    path = tmp_path / FARM
    _book(path)
    with open(path, "rb") as f:
        farm = client.post("/api/workbooks", files={"file": (FARM, f, "application/octet-stream")}).json()["id"]
    log = {"Pond_ID": "POND-002", "Feed_Date": "2026-10-11", "Feed_Item_ID": "FEED-002", "Quantity_Kg": 10, "Recorded_By": "Suresh Reddy"}
    use_model(ScriptedProvider([propose(action="create", worksheet="Feed_Logs", fields=log), say("Log 10 kg?")]))
    action = chat(client, farm, "Log 10 kg of grower feed for pond 2")["action"]
    assert action["state"] == "awaiting_confirmation", action
    assert any("Reduces" in c and "FEED-002" in c and "10" in c for c in action["preview"]["consequences"]), action["preview"]
    assert confirm(client, farm, action).json()["action"]["state"] == "completed"
    assert find(client, farm, "Feed_Inventory", "Feed_Item_ID", "FEED-002")["data"]["Stock_Kg"] == 610
