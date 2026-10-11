"""Confirm or cancel an assistant-prepared draft (the draft card's buttons).

The same checks run here as for a spoken/typed "yes" in /chat and
/voice/respond: signed-in owner of the draft, the draft's workbook in the
user's tenant, the one-time token, expiry, and then permission, staleness
and the record service's own rules at execution time (see
app/services/actions/executor.py).
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.portal import _load_workbook_for_portal
from app.core.db import get_db
from app.models.user import User
from app.schemas.actions import ActionCancelIn, ActionConfirmIn, ActionResultOut, ActionStateOut
from app.services.actions import executor, messages
from app.services.actions.session import outcome_message, outcome_state

router = APIRouter(prefix="/api/workbooks", tags=["actions"])


def _result(outcome: executor.Outcome, language: str | None) -> ActionResultOut:
    return ActionResultOut(
        message=outcome_message(outcome, messages.language_of(None, language)),
        action=ActionStateOut(**outcome_state(outcome)),
    )


@router.post("/{workbook_id}/actions/{draft_id}/confirm", response_model=ActionResultOut)
def confirm_action(
    workbook_id: uuid.UUID,
    draft_id: uuid.UUID,
    payload: ActionConfirmIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ActionResultOut:
    _load_workbook_for_portal(db, workbook_id, user.tenant_id)  # 404 for another tenant's workbook
    outcome = executor.execute(db, user, draft_id, payload.token, payload.conversation_id, workbook_id)
    return _result(outcome, payload.language)


@router.post("/{workbook_id}/actions/{draft_id}/cancel", response_model=ActionResultOut)
def cancel_action(
    workbook_id: uuid.UUID,
    draft_id: uuid.UUID,
    payload: ActionCancelIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ActionResultOut:
    _load_workbook_for_portal(db, workbook_id, user.tenant_id)
    outcome = executor.cancel(db, user, draft_id, payload.conversation_id, workbook_id)
    return _result(outcome, payload.language)
