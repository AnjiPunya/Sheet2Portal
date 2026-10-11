"""Validate and normalise a create/edit payload against the worksheet schema.

The client is never trusted: unknown fields are rejected, values are
coerced to the column's type and format, references must point at existing
records, numbers must sit inside their valid range, dates must be in order,
stock can't be over-used, calculated and auto-filled fields are always set
here, and workflow status can't be changed through an edit.
"""

import re

from app.services.analysis.kpis import parse_date
from app.services.analysis.text import humanize
from app.services.records.field_rules import num
from app.services.records.formulas import evaluate, factor_value
from app.services.records.links import find_linked_row, norm
from app.services.records.schema import _NON_NEGATIVE_ROLES, EntityRules, RecordContext, next_identifier, status_choices

_MAX_TEXT = 2000
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^\+?[\d\s()\-]{7,20}$")
_TIME = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d(:[0-5]\d)?$")


class RecordValidationError(Exception):
    def __init__(self, fields: dict[str, str]):
        super().__init__("Please fix the highlighted fields.")
        self.fields = fields


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _fmt(value: float) -> str:
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"


def coerce(value: object, type_: str) -> object:
    """Convert to the column's type; raises ValueError with a user-facing message."""
    if _blank(value):
        return None
    if type_ in ("int", "float"):
        if isinstance(value, bool):
            raise ValueError("Enter a number.")
        if isinstance(value, str):
            try:
                value = float(value.replace(",", "").strip())
            except ValueError:
                raise ValueError("Enter a number.") from None
        if not isinstance(value, (int, float)) or value != value or value in (float("inf"), float("-inf")):
            raise ValueError("Enter a number.")
        if type_ == "int":
            if float(value) != int(value):
                raise ValueError("Enter a whole number.")
            return int(value)
        return float(value)
    if type_ == "date":
        parsed = parse_date(value) if isinstance(value, str) else None
        if parsed is None:
            raise ValueError("Enter a valid date (YYYY-MM-DD).")
        return parsed.isoformat()
    if type_ == "bool":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("true", "yes", "1"):
            return True
        if text in ("false", "no", "0"):
            return False
        raise ValueError("Choose yes or no.")
    text = str(value).strip()
    if len(text) > _MAX_TEXT:
        raise ValueError(f"Keep this under {_MAX_TEXT} characters.")
    return text


def _coerce_field(rules: EntityRules, name: str, raw: object) -> object:
    fr = rules.fields
    column = rules.column(name)
    if name in fr.choices:  # yes/no-style columns kept in the workbook's own wording
        if _blank(raw):
            return None
        options = {norm(o): o for o in fr.choices[name]}
        if norm(raw) not in options:
            raise ValueError(f"Choose one of: {', '.join(fr.choices[name])}.")
        return options[norm(raw)]
    fmt = fr.formats.get(name)
    if fmt:
        text = coerce(raw, "string")
        if text is None:
            return None
        if fmt == "email" and not _EMAIL.match(text):
            raise ValueError("Enter a valid email address.")
        if fmt == "tel" and not _PHONE.match(text):
            raise ValueError("Enter a valid phone number (digits, spaces, + - ( ) only).")
        if fmt == "time":
            if not _TIME.match(text):
                raise ValueError("Enter a valid time (HH:MM).")
            hours, minutes = text.split(":")[:2]
            text = f"{int(hours):02d}:{minutes}"
        return text
    type_ = column.inferred_type if column else "float"  # extra fields are lookup factors (numbers)
    if type_ not in ("int", "float", "date", "bool"):
        type_ = "string"
    value = coerce(raw, type_)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        low, high = fr.bounds.get(name, (None, None))
        if column is None or column.role in _NON_NEGATIVE_ROLES:
            low = 0.0 if low is None else low
        if low is not None and value < low:
            raise ValueError("Must be zero or more." if low == 0 else f"Must be at least {_fmt(low)}.")
        if high is not None and value > high:
            raise ValueError(f"Must be between {_fmt(low or 0)} and {_fmt(high)}.")
    return value


def validate(
    ctx: RecordContext,
    rules: EntityRules,
    payload: dict,
    existing: dict | None,
    other_rows: list[dict],
) -> dict:
    """Return the full record data to store, or raise RecordValidationError.
    ``existing`` is None for a create; ``other_rows`` are the worksheet's
    other records (for uniqueness checks)."""
    if not isinstance(payload, dict):
        raise RecordValidationError({"_": "Invalid request."})
    entity = rules.entity
    fr = rules.fields
    creating = existing is None
    errors: dict[str, str] = {}
    allowed = {c.name for c in entity.columns} | set(rules.extra_fields)
    workflow = rules.workflow
    derived = {name for name, copy in fr.copies.items() if copy.derived}

    data = dict(existing or {})
    touched: set[str] = set()
    for name, raw in payload.items():
        if name not in allowed:
            errors[name] = "Unknown field."
            continue
        if name in rules.computed or name in derived:
            continue  # always set below; whatever the client sent is ignored
        if workflow and name == workflow.status_column:
            current = workflow.pending if creating else workflow.state(data.get(name))
            if not _blank(raw) and norm(raw) != norm(current):
                errors[name] = "Status changes through the approve / reject actions."
            continue
        try:
            data[name] = _coerce_field(rules, name, raw)
        except ValueError as exc:
            errors[name] = str(exc)
            continue
        touched.add(name)

    if creating:
        if workflow:
            data[workflow.status_column] = workflow.pending
        # Pre-filled defaults the user didn't override: constant columns
        # (every pond's Farm ID) and values copied from the linked record.
        for name, value in fr.constants.items():
            if _blank(data.get(name)):
                data[name] = value
        if entity.identifier_column and _blank(data.get(entity.identifier_column)):
            generated = next_identifier(rules, data)
            if generated:
                data[entity.identifier_column] = generated

    # References must point at an existing record; store its canonical spelling.
    for name, link in rules.links.items():
        if name in errors or (not creating and name not in touched) or _blank(data.get(name)):
            continue
        linked = find_linked_row(link, data[name], ctx.rows_by_entity)
        if linked is None:
            errors[name] = f"Choose an existing {humanize(link.target).lower()} record."
        else:
            data[name] = linked.get(link.target_column)

    # Values copied from the linked record: derived ones always follow it;
    # editable ones are filled when blank or when the link changed.
    for name, copy in fr.copies.items():
        if name in errors or copy.link.column in errors:
            continue
        link_changed = creating or copy.link.column in touched
        refresh = copy.derived or (link_changed and name not in touched and (not creating or _blank(data.get(name))))
        if refresh:
            linked = find_linked_row(copy.link, data.get(copy.link.column), ctx.rows_by_entity)
            if linked is not None:
                data[name] = linked.get(copy.source_column)

    # Required fields: all of them on create; on edit only the ones being
    # changed (legacy rows with gaps can still be edited).
    for name in rules.required:
        if (creating or name in touched) and _blank(data.get(name)) and name not in errors:
            if name == entity.identifier_column and rules.id_pattern and rules.id_pattern.by_column:
                errors[name] = f"{humanize(name)} is required (or choose a {humanize(rules.id_pattern.by_column)} to generate one)."
            else:
                errors[name] = f"{humanize(name)} is required."

    # Status values must be one the workbook uses, when the column is a real status.
    status = entity.status_column
    if status and fr.strict_status and status in touched and not (workflow and status == workflow.status_column) and status not in errors:
        known = {norm(value): value for value in status_choices(entity)}
        if known and not _blank(data.get(status)):
            if norm(data[status]) not in known:
                errors[status] = f"Choose one of: {', '.join(known.values())}."
            else:
                data[status] = known[norm(data[status])]

    identifier = entity.identifier_column
    if identifier and not _blank(data.get(identifier)) and identifier not in errors:
        if any(norm(row.get(identifier)) == norm(data[identifier]) for row in other_rows):
            errors[identifier] = f"{humanize(identifier)} {data[identifier]} already exists."

    # End dates can't come before their start dates.
    for order in fr.date_orders:
        if order.end in errors or order.start in errors or not (creating or touched & {order.end, order.start}):
            continue
        start, end = parse_date(data.get(order.start)), parse_date(data.get(order.end))
        if start and end and end < start:
            errors[order.end] = f"{humanize(order.end)} can't be before {humanize(order.start)}."

    # Stock within a row: used can't exceed opening + received.
    row_stock = fr.row_stock
    if row_stock and (creating or touched & {row_stock.outbound, *row_stock.supply}) and row_stock.outbound not in errors:
        used = num(data.get(row_stock.outbound))
        supply = sum(num(data.get(c)) or 0 for c in row_stock.supply)
        if used is not None and used > supply:
            names = " + ".join(humanize(c) for c in row_stock.supply)
            errors[row_stock.outbound] = f"{humanize(row_stock.outbound)} ({_fmt(used)}) can't exceed {names} ({_fmt(supply)})."

    # Stock in the linked inventory record: can't use more than is available.
    stock = fr.linked_stock
    if stock and (creating or touched & {stock.quantity, stock.link.column}) and not errors.get(stock.quantity) and not errors.get(stock.link.column):
        quantity = num(data.get(stock.quantity))
        target_row = find_linked_row(stock.link, data.get(stock.link.column), ctx.rows_by_entity)
        if quantity is not None and target_row is not None:
            available = stock.available(target_row)
            if available is not None:
                if existing and norm(existing.get(stock.link.column)) == norm(data.get(stock.link.column)):
                    available += num(existing.get(stock.quantity)) or 0  # this record's own earlier usage
                if quantity > available:
                    errors[stock.quantity] = (
                        f"Only {_fmt(max(available, 0))} available for {data.get(stock.link.column)} "
                        f"in {humanize(stock.link.target)}."
                    )

    if errors:
        raise RecordValidationError(errors)

    # Calculated fields. A lookup factor (e.g. Unit Cost) is stored on the
    # record so later price changes don't silently rewrite past requests:
    # refreshed from the lookup when its source changes, unless the user
    # entered one.
    for formula in rules.formulas:
        for factor in formula.factors:
            if factor.link is None or factor.column in touched:
                continue
            if creating or factor.link.column in touched or _blank(data.get(factor.column)):
                lookup = dict(data)
                lookup.pop(factor.column, None)
                data[factor.column] = factor_value(factor, lookup, ctx.rows_by_entity)
        result = evaluate(formula, data, ctx.rows_by_entity)
        target = rules.column(formula.target)
        if result is not None and target and target.inferred_type == "int" and float(result).is_integer():
            result = int(result)
        data[formula.target] = result
    return data
