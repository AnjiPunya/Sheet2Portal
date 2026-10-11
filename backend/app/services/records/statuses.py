"""Full status choices for a status column.

A workbook only contains the statuses it happens to use today (every
worker "Active"; tasks "Not Started"/"In Progress" with none done yet), so
offering only those would make it impossible to mark a task completed or
an issue resolved. Each status column is matched to a lifecycle family
(work, issue, payment, order, procurement, active/inactive) and offered the
whole family -- keeping the workbook's own wording for values it already
uses and never adding a synonym of one of them. Deterministic; approval
workflows keep their own approve/reject rules and aren't extended here.
"""

from app.services.analysis.text import normalize_key

# Each family: ordered groups of synonyms; the first is what gets offered.
FAMILIES: dict[str, list[list[str]]] = {
    "work": [
        ["Not Started", "To Do", "Open", "Planned", "New"],
        ["In Progress", "Ongoing", "Started", "Working"],
        ["On Hold", "Paused"],
        ["At Risk", "Blocked", "Delayed"],
        ["Completed", "Done", "Complete", "Finished"],
        ["Cancelled", "Canceled"],
    ],
    "issue": [
        ["Open", "New", "Reported"],
        ["Investigating", "In Progress", "Under Review"],
        ["Monitoring", "Follow-up due", "Mitigating"],
        ["Resolved", "Fixed", "Mitigated"],
        ["Closed"],
    ],
    "payment": [
        ["Pending", "Unpaid", "Due"],
        ["Paid", "Settled"],
        ["Overdue"],
        ["Cancelled", "Refunded"],
    ],
    "order": [
        ["Pending", "New", "Placed"],
        ["Processing", "Confirmed"],
        ["Shipped", "Dispatched", "In Transit"],
        ["Delivered", "Completed", "Fulfilled"],
        ["Cancelled", "Canceled"],
        ["Returned"],
    ],
    "procurement": [
        ["Requested", "Not Ordered", "Pending"],
        ["Ordered", "PO Raised"],
        ["In Transit", "Shipped"],
        ["Received", "Delivered"],
        ["Cancelled"],
    ],
    "active": [
        ["Active"],
        ["Inactive"],
        ["On Hold", "Suspended"],
    ],
}

# Column/sheet name hints that settle ties (e.g. "Pending" is both a
# payment and an order status).
_HINTS = {
    "payment": ("payment", "paid", "invoice", "expense", "bill"),
    "order": ("order", "shipping", "delivery", "shipment"),
    "procurement": ("procurement", "purchase", "po"),
    "issue": ("issue", "risk", "incident", "treatment", "health", "complaint", "defect", "ticket"),
    "work": ("task", "project", "job", "work", "operation", "activity", "milestone"),
}


def _key(value: str) -> str:
    return normalize_key(value)


def detect_family(values: list[str], worksheet: str, column: str) -> str | None:
    keys = {_key(v) for v in values}
    context = _key(worksheet) + _key(column)
    best: tuple[int, int, str] | None = None
    for family, groups in FAMILIES.items():
        matches = sum(1 for g in groups if keys & {_key(s) for s in g})
        if matches == 0:
            continue
        hinted = int(any(h in context for h in _HINTS.get(family, ())))
        score = (matches + hinted, hinted, family)
        if best is None or score[:2] > best[:2]:
            best = score
    return best[2] if best else None


def status_options(values: list[str], worksheet: str, column: str) -> list[str]:
    """The workbook's statuses plus the rest of their lifecycle family, in
    lifecycle order. Unrecognised workbook values are kept at the end."""
    family = detect_family(values, worksheet, column)
    if family is None:
        return list(values)
    existing = {_key(v): v for v in values}
    options: list[str] = []
    for group in FAMILIES[family]:
        present = [existing[_key(s)] for s in group if _key(s) in existing]
        options.extend(present or [group[0]])
    options.extend(v for v in values if v not in options)
    seen: set[str] = set()
    return [o for o in options if not (_key(o) in seen or seen.add(_key(o)))]
