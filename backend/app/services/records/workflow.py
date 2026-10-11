"""Approval workflow, enabled per entity from its own status values.

An entity gets a Pending -> Approved / Rejected workflow when its status
column already uses a pending-style value plus an approved- or
rejected-style value (e.g. Purchase Requests: "Pending Approval",
"Approved", "Rejected"). The workbook's own wording is kept. Generic --
nothing here knows about purchase requests.

Rules (enforced by the backend, not just the UI):
- new records start Pending;
- Pending -> Approved or Rejected (needs the approve permission);
- Rejected -> Pending ("resubmit", needs edit permission);
- Approved is final: the record can't be edited, deleted or re-decided;
- the status field can't be changed through a normal edit.
"""

import re
from dataclasses import dataclass

from app.services.analysis.types import EntityConfig

_PENDING = re.compile(r"pending|awaiting|submitted|for approval|in review|under review", re.I)
_APPROVED = re.compile(r"^(?!un|not|dis)\s*approved?\b", re.I)
_REJECTED = re.compile(r"reject|declin|denied", re.I)

APPROVE, REJECT, RESUBMIT = "approve", "reject", "resubmit"


@dataclass(frozen=True)
class Workflow:
    status_column: str
    pending: str
    approved: str
    rejected: str

    def transitions(self) -> dict[str, dict[str, str]]:
        """status -> {action: next status}"""
        return {
            self.pending: {APPROVE: self.approved, REJECT: self.rejected},
            self.rejected: {RESUBMIT: self.pending},
            self.approved: {},
        }

    def state(self, status: object) -> str:
        """Normalise a stored status to one of the three workflow states."""
        text = str(status or "").strip().lower()
        for value in (self.approved, self.rejected, self.pending):
            if text == value.lower():
                return value
        return self.pending  # unknown/blank statuses are treated as awaiting a decision

    def next_status(self, status: object, action: str) -> str | None:
        return self.transitions()[self.state(status)].get(action)

    def is_final(self, status: object) -> bool:
        return self.state(status) == self.approved


def detect_workflow(entity: EntityConfig) -> Workflow | None:
    if not entity.status_column:
        return None
    values = [item.value for item in entity.status_breakdown]
    pending = next((v for v in values if _PENDING.search(v)), None)
    approved = next((v for v in values if _APPROVED.search(v)), None)
    rejected = next((v for v in values if _REJECTED.search(v)), None)
    if pending is None or (approved is None and rejected is None):
        return None
    return Workflow(entity.status_column, pending, approved or "Approved", rejected or "Rejected")
