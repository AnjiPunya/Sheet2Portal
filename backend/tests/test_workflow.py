"""Approval workflow: transitions, locking, permissions, audit trail, and
alerts updating immediately after decisions."""

import pytest

from app.models.user import User
from app.services.analysis.types import EntityConfig, StatusBreakdownItem
from app.services.records.workflow import APPROVE, REJECT, RESUBMIT, detect_workflow
from tests.test_records_crud import PR, VALID_PR, create, kpi, records_url, upload_demo


@pytest.fixture
def construction(client, tmp_path):
    return upload_demo(client, tmp_path)


def decide(client, workbook_id, record_id, action, comment=None):
    url = f"{records_url(workbook_id, PR)}/{record_id}/decision"
    return client.post(url, json={"action": action, "comment": comment})


def new_request(client, workbook_id) -> str:
    return create(client, workbook_id, PR, VALID_PR).json()["id"]


def same_tenant(client, email):
    """Put another user in the owner's tenant (roles are per user)."""
    with client.test_sessionmaker() as db:
        owner = db.query(User).filter(User.email == "owner@example.com").one()
        db.query(User).filter(User.email == email).update({"tenant_id": owner.tenant_id})
        db.commit()


# --- detection ---------------------------------------------------------------


def _entity(values):
    return EntityConfig(
        worksheet="X", label="X", singular_label="X", icon="", identifier_column=None, title_column=None,
        status_column="Status", status_breakdown=[StatusBreakdownItem(v, 1, False) for v in values],
    )


def test_workflow_detected_from_status_values():
    workflow = detect_workflow(_entity(["Pending Approval", "Approved", "Rejected"]))
    assert (workflow.pending, workflow.approved, workflow.rejected) == ("Pending Approval", "Approved", "Rejected")


@pytest.mark.parametrize("values", [["Open", "Done"], ["Pending", "Shipped", "Delivered"], ["Unapproved", "Draft"], []])
def test_no_workflow_without_approval_style_statuses(values):
    assert detect_workflow(_entity(values)) is None


def test_transition_table():
    workflow = detect_workflow(_entity(["Pending", "Approved", "Declined"]))
    assert workflow.next_status("Pending", APPROVE) == "Approved"
    assert workflow.next_status("Pending", REJECT) == "Declined"
    assert workflow.next_status("Declined", RESUBMIT) == "Pending"
    assert workflow.next_status("Approved", REJECT) is None
    assert workflow.next_status("Approved", RESUBMIT) is None
    assert workflow.next_status("Pending", RESUBMIT) is None


# --- decisions -----------------------------------------------------------------


def test_approve_records_comment_timestamp_and_user(client, construction):
    record_id = new_request(client, construction)
    response = decide(client, construction, record_id, "approve", "Within budget")
    assert response.status_code == 200
    assert response.json()["data"]["Status"] == "Approved"
    event = client.get(f"{records_url(construction, PR)}/{record_id}/activity").json()["history"][0]
    assert event["action"] == "approved"
    assert (event["from_status"], event["to_status"]) == ("Pending Approval", "Approved")
    assert event["comment"] == "Within budget"
    assert event["user_name"] == "owner" and event["created_at"]


def test_reject_then_resubmit_then_approve(client, construction):
    record_id = new_request(client, construction)
    assert decide(client, construction, record_id, "reject", "Too expensive").json()["data"]["Status"] == "Rejected"
    url = f"{records_url(construction, PR)}/{record_id}"
    assert client.get(f"{url}/activity").json()["actions"]["resubmit"] is True
    client.patch(url, json={"data": {"Quantity": 2}})  # rejected requests can be revised
    assert decide(client, construction, record_id, "resubmit").json()["data"]["Status"] == "Pending Approval"
    assert decide(client, construction, record_id, "approve").json()["data"]["Status"] == "Approved"
    actions = [e["action"] for e in client.get(f"{url}/activity").json()["history"]]
    assert actions == ["approved", "resubmitted", "updated", "rejected", "created"]


@pytest.mark.parametrize("action", ["approve", "reject", "resubmit"])
def test_approved_is_final(client, construction, action):
    record_id = new_request(client, construction)
    decide(client, construction, record_id, "approve")
    response = decide(client, construction, record_id, action)
    assert response.status_code == 409
    assert response.json()["detail"]["error_code"] == "INVALID_TRANSITION"


def test_approved_records_are_locked(client, construction):
    record_id = new_request(client, construction)
    decide(client, construction, record_id, "approve")
    url = f"{records_url(construction, PR)}/{record_id}"
    assert client.patch(url, json={"data": {"Quantity": 1}}).json()["detail"]["error_code"] == "RECORD_LOCKED"
    assert client.delete(url).json()["detail"]["error_code"] == "RECORD_LOCKED"
    assert client.get(f"{url}/activity").json()["actions"] == {
        "edit": False, "delete": False, "approve": False, "reject": False, "resubmit": False,
    }


def test_status_cannot_be_changed_through_edit(client, construction):
    record_id = new_request(client, construction)
    response = client.patch(f"{records_url(construction, PR)}/{record_id}", json={"data": {"Status": "Approved"}})
    assert response.status_code == 422
    assert "approve / reject" in response.json()["detail"]["fields"]["Status"]


def test_existing_workbook_rows_can_be_decided(client, construction):
    page = client.get(records_url(construction, PR), params={"status": "Pending Approval"}).json()
    record_id = page["records"][0]["id"]
    assert decide(client, construction, record_id, "approve").status_code == 200


def test_non_workflow_entity_has_no_decisions(client, construction):
    task_id = client.get(records_url(construction, "Tasks")).json()["records"][0]["id"]
    response = client.post(f"{records_url(construction, 'Tasks')}/{task_id}/decision", json={"action": "approve"})
    assert response.status_code == 422
    assert response.json()["detail"]["error_code"] == "NO_WORKFLOW"


def test_invalid_action_and_long_comment_rejected(client, construction):
    record_id = new_request(client, construction)
    assert decide(client, construction, record_id, "destroy").status_code == 422
    assert decide(client, construction, record_id, "approve", "x" * 1001).status_code == 422


# --- dashboard updates immediately -------------------------------------------


def test_approval_breakdown_and_alerts_update_after_decisions(client, construction):
    pending = kpi(client, construction, f"{PR}:status:Pending Approval")
    record_id = new_request(client, construction)
    assert kpi(client, construction, f"{PR}:status:Pending Approval") == pending + 1
    decide(client, construction, record_id, "approve")
    assert kpi(client, construction, f"{PR}:status:Pending Approval") == pending
    config = client.get(f"/api/workbooks/{construction}/portal").json()
    breakdown = {s["value"]: s["count"] for s in next(e for e in config["entities"] if e["worksheet"] == PR)["status_breakdown"]}
    assert breakdown["Approved"] == 2  # PR-1003 from the workbook + the new one


# --- permissions ---------------------------------------------------------------


def test_approver_can_decide_but_not_create(client, make_client, construction):
    record_id = new_request(client, construction)
    approver = make_client("approver@example.com", role="approver")
    same_tenant(client, "approver@example.com")
    assert create(approver, construction, PR, VALID_PR).status_code == 403
    actions = approver.get(f"{records_url(construction, PR)}/{record_id}/activity").json()["actions"]
    assert actions["approve"] and actions["reject"] and not actions["edit"]
    assert decide(approver, construction, record_id, "approve").status_code == 200


def test_editor_can_resubmit_but_not_approve(client, make_client, construction):
    record_id = new_request(client, construction)
    editor = make_client("editor@example.com", role="editor")
    same_tenant(client, "editor@example.com")
    response = decide(editor, construction, record_id, "approve")
    assert response.status_code == 403
    assert client.get(f"{records_url(construction, PR)}/{record_id}/activity").json()["history"][0]["action"] == "created"
    decide(client, construction, record_id, "reject")
    assert decide(editor, construction, record_id, "resubmit").status_code == 200


def test_other_tenant_cannot_decide(client, make_client, construction):
    record_id = new_request(client, construction)
    outsider = make_client("outsider@example.com")
    assert decide(outsider, construction, record_id, "approve").status_code == 404
