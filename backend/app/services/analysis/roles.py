"""Deterministic, name- and value-pattern based column role inference.

No AI involved: every classification here is a keyword match against the
column name, optionally combined with a type/cardinality check. Ambiguous
cases (no strong name signal) fall back to weaker heuristics with a lower
``role_confidence`` rather than being asserted with certainty -- callers
should treat low-confidence roles as suggestions, not facts.
"""

import re

from app.services.analysis.types import ColumnProfile, FieldRole

IDENTIFIER_HINTS = ("id", "code", "number", "no", "sku", "key", "ref", "reference")
TITLE_HINTS = ("name", "title", "description", "label")
# "status"/"state" name a column that literally tracks status; "stage",
# "phase", "priority" are weaker, secondary signals (e.g. a sheet can have
# both "Priority" and "Approval_Status" -- the latter should win the pick).
STATUS_HINTS_STRONG = ("status", "state")
STATUS_HINTS_WEAK = ("stage", "phase", "priority")
DUE_DATE_HINTS = ("due", "deadline")
START_DATE_HINTS = ("start",)
BUDGET_AMOUNT_HINTS = ("budget", "allocated", "allocation", "estimate", "estimated")
ACTUAL_AMOUNT_HINTS = ("spent", "actual", "paid", "committed", "incurred")
GENERIC_AMOUNT_HINTS = ("amount", "price", "cost", "value", "total", "revenue", "fee", "expense")
QUANTITY_HINTS = ("quantity", "qty", "stock", "units", "count", "available", "onhand", "level", "balance")
THRESHOLD_HINTS = ("reorder", "threshold", "minimum", "min", "safetystock")
PERSON_HINTS = ("manager", "owner", "assignee", "assigned", "contact", "vendor", "supplier", "approver", "lead", "requestedby", "requested_by")


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _matches(normalized: str, hints: tuple[str, ...]) -> bool:
    return any(hint in normalized for hint in hints)


def infer_role(name: str, inferred_type: str, values: list[object]) -> tuple[FieldRole, float]:
    normalized = _normalize(name)
    non_null = [v for v in values if v is not None and str(v).strip() != ""]
    distinct = len(set(str(v) for v in non_null))
    total = len(values) or 1

    if inferred_type == "bool":
        return FieldRole.FLAG, 0.9

    if _matches(normalized, DUE_DATE_HINTS) and inferred_type == "date":
        return FieldRole.DUE_DATE, 0.9

    if _matches(normalized, IDENTIFIER_HINTS) and inferred_type in ("int", "string"):
        return FieldRole.IDENTIFIER, 0.85

    if _matches(normalized, STATUS_HINTS_STRONG):
        return FieldRole.STATUS, 0.9

    if _matches(normalized, STATUS_HINTS_WEAK):
        return FieldRole.STATUS, 0.7

    if _matches(normalized, BUDGET_AMOUNT_HINTS) and inferred_type in ("int", "float"):
        return FieldRole.BUDGET_AMOUNT, 0.85

    if _matches(normalized, ACTUAL_AMOUNT_HINTS) and inferred_type in ("int", "float"):
        return FieldRole.ACTUAL_AMOUNT, 0.85

    if _matches(normalized, GENERIC_AMOUNT_HINTS) and inferred_type in ("int", "float"):
        return FieldRole.AMOUNT, 0.75

    if _matches(normalized, THRESHOLD_HINTS) and inferred_type in ("int", "float"):
        return FieldRole.THRESHOLD, 0.8

    if _matches(normalized, QUANTITY_HINTS) and inferred_type in ("int", "float"):
        return FieldRole.QUANTITY, 0.8

    if _matches(normalized, PERSON_HINTS) and inferred_type == "string":
        return FieldRole.PERSON, 0.75

    if _matches(normalized, TITLE_HINTS) and inferred_type == "string":
        return FieldRole.TITLE, 0.75

    if inferred_type == "date" and _matches(normalized, START_DATE_HINTS):
        return FieldRole.DATE, 0.7

    if inferred_type == "date":
        return FieldRole.DATE, 0.6

    # Weak fallbacks: no name signal, infer from shape of the data. The
    # uniqueness check needs enough rows to be meaningful -- on a handful of
    # rows, ordinary descriptive text columns are often accidentally all-unique.
    if inferred_type in ("int", "string") and total >= 10 and distinct >= max(3, int(total * 0.9)):
        return FieldRole.IDENTIFIER, 0.4

    if inferred_type == "string" and 1 < distinct <= min(15, max(2, total // 2)):
        return FieldRole.STATUS, 0.35

    if inferred_type == "string":
        return FieldRole.TITLE, 0.3

    return FieldRole.OTHER, 0.2


def profile_column(
    name: str, position: int, inferred_type: str, type_confidence: float, values: list[object]
) -> ColumnProfile:
    role, role_confidence = infer_role(name, inferred_type, values)
    non_null = [v for v in values if v is not None and str(v).strip() != ""]
    return ColumnProfile(
        name=name,
        position=position,
        inferred_type=inferred_type,
        type_confidence=type_confidence,
        role=role,
        role_confidence=role_confidence,
        distinct_count=len(set(str(v) for v in non_null)),
        null_count=len(values) - len(non_null),
    )
