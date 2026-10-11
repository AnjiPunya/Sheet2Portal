"""Field-level rules for record forms, inferred from the workbook itself.

Each rule is deterministic and only applied when the existing data already
follows it (so it never rejects the workbook's own records):

- copies: a value that always equals a field of the linked record
  (a feed log's unit cost = the feed item's unit cost; a request's
  "Material or Service" = the selected material's name) is filled in
  automatically -- read-only when it's just the linked record's name;
- constants: a column with one value in every row (every pond's Farm ID is
  FARM-001) is pre-filled instead of retyped;
- formats: phone numbers, emails and clock times;
- bounds: percentages 0-100, ratings 0-max, non-negative numbers;
- date order: an end/due/target date can't be before its start date;
- stock: used quantity can't exceed what's available -- within a row
  (Used <= Opening + Received) or in the linked inventory record (a feed
  log can't use more feed than the item has in stock).
"""

from dataclasses import dataclass, field

from app.services.analysis.kpis import parse_date
from app.services.analysis.semantics import (
    allows_negative,
    date_role,
    is_consumption_sheet,
    is_email,
    is_optional_text,
    is_percent,
    is_phone,
    is_time,
    rating_max,
)
from app.services.analysis.types import EntityConfig, FieldRole, PortalConfig
from app.services.records.links import Link, find_linked_row, norm

_NUMERIC = ("int", "float")
_NON_NEGATIVE_ROLES = {FieldRole.QUANTITY, FieldRole.THRESHOLD, FieldRole.AMOUNT, FieldRole.BUDGET_AMOUNT, FieldRole.ACTUAL_AMOUNT}
_STRICT_STATUS_WORDS = ("status", "state", "stage", "phase", "priority", "severity", "tier")
_MIN_EVIDENCE = 2


def num(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def _same(a: object, b: object) -> bool:
    na, nb = num(a), num(b)
    if na is not None and nb is not None:
        return abs(na - nb) < 1e-9
    return norm(a) == norm(b) and norm(a) != ""


@dataclass(frozen=True)
class Copy:
    column: str
    link: Link
    source_column: str  # column in link.target the value comes from
    derived: bool  # True: always the linked record's value (read-only)


@dataclass(frozen=True)
class DateOrder:
    end: str
    start: str


@dataclass(frozen=True)
class RowStock:
    outbound: str  # e.g. Used_Qty
    supply: tuple[str, ...]  # e.g. (Opening_Stock, Received_Qty)


@dataclass(frozen=True)
class LinkedStock:
    quantity: str  # quantity column on the consuming record (Feed_Logs.Quantity_Kg)
    link: Link  # to the inventory record
    stock: str | None  # direct stock column (Stock_Kg)
    opening: str | None = None  # or a flow: opening + inbound - outbound
    inbound: str | None = None
    outbound: str | None = None

    def available(self, target_row: dict) -> float | None:
        if self.stock:
            return num(target_row.get(self.stock))
        opening = num(target_row.get(self.opening)) if self.opening else None
        if opening is None:
            return None
        return opening + (num(target_row.get(self.inbound)) or 0) - (num(target_row.get(self.outbound)) or 0)


@dataclass
class FieldRules:
    copies: dict[str, Copy] = field(default_factory=dict)
    constants: dict[str, object] = field(default_factory=dict)
    formats: dict[str, str] = field(default_factory=dict)  # column -> tel | email | time
    choices: dict[str, list[str]] = field(default_factory=dict)  # yes/no-style columns stored as text
    bounds: dict[str, tuple[float | None, float | None]] = field(default_factory=dict)
    date_orders: list[DateOrder] = field(default_factory=list)
    row_stock: RowStock | None = None
    linked_stock: LinkedStock | None = None
    optional: set[str] = field(default_factory=set)
    strict_status: bool = True


def _detect_copies(entity: EntityConfig, rows: list[dict], links: dict[str, Link], config: PortalConfig, rows_by_entity, computed: set[str]) -> dict[str, Copy]:
    targets = {e.worksheet: e for e in config.entities}
    copies: dict[str, Copy] = {}
    # Relationship links first: they're the stronger evidence of "which record".
    ordered = sorted(links.values(), key=lambda link: link.source != "relationship")
    for column in entity.columns:
        name = column.name
        if name in computed or name == entity.identifier_column:
            continue
        own = links.get(name)
        if own is not None and own.source == "relationship":
            continue  # a real reference (Project_ID) is always chosen, never inferred from another field
        for link in ordered:
            if link.column == name or link.target not in targets:
                continue
            target = targets[link.target]
            candidates = sorted(
                (c.name for c in target.columns),
                key=lambda x: (norm(x).replace(" ", "") != norm(name).replace(" ", ""), x not in (target.title_column, target.identifier_column)),
            )
            for source in candidates:
                evidence, consistent = 0, True
                for row in rows:
                    if row.get(name) in (None, ""):
                        continue
                    linked = find_linked_row(link, row.get(link.column), rows_by_entity)
                    if linked is None:
                        continue
                    if not _same(row.get(name), linked.get(source)):
                        consistent = False
                        break
                    evidence += 1
                if consistent and evidence >= _MIN_EVIDENCE:
                    derived = name in links or source in (target.title_column, target.identifier_column, link.target_column)
                    copies[name] = Copy(name, link, source, derived)
                    break
            if name in copies:
                break
    return copies


def _date_orders(entity: EntityConfig, rows: list[dict]) -> list[DateOrder]:
    dates = [c.name for c in entity.columns if c.inferred_type == "date"]
    orders = []
    for end in dates:
        if date_role(end) != "end":
            continue
        best: tuple[int, str] | None = None
        for start in dates:
            if start == end or date_role(start) != "start":
                continue
            pairs = [(parse_date(r.get(start)), parse_date(r.get(end))) for r in rows]
            pairs = [(s, e) for s, e in pairs if s and e]
            if pairs and all(e >= s for s, e in pairs) and (best is None or len(pairs) > best[0]):
                best = (len(pairs), start)
        if best:
            orders.append(DateOrder(end, best[1]))
    return orders


def analyse_fields(
    entity: EntityConfig,
    rows: list[dict],
    links: dict[str, Link],
    config: PortalConfig,
    rows_by_entity: dict[str, list[dict]],
    computed: set[str],
) -> FieldRules:
    rules = FieldRules()
    rules.copies = _detect_copies(entity, rows, links, config, rows_by_entity, computed)

    for column in entity.columns:
        name = column.name
        values = [r.get(name) for r in rows if r.get(name) not in (None, "")]
        if is_optional_text(name):
            rules.optional.add(name)
        if is_phone(name):
            rules.formats[name] = "tel"
        elif column.inferred_type == "string" and values and is_email(name, values):
            rules.formats[name] = "email"
        elif column.inferred_type == "string" and is_time(values):
            rules.formats[name] = "time"

        if column.inferred_type == "bool" and any(isinstance(v, str) for v in values):
            options = sorted({str(v).strip() for v in values})
            for word in ("Yes", "No"):
                if any(o.lower() in ("yes", "no") for o in options) and word.lower() not in {o.lower() for o in options}:
                    options.append(word)
            rules.choices[name] = options

        if column.inferred_type in _NUMERIC and name not in rules.formats:
            numbers = [n for n in (num(v) for v in values) if n is not None]
            low = None
            if column.role in _NON_NEGATIVE_ROLES or (len(numbers) >= _MIN_EVIDENCE and min(numbers) >= 0 and not allows_negative(name)):
                low = 0.0
            high = None
            if is_percent(name):
                low, high = 0.0, (1.0 if numbers and max(numbers) <= 1 and any(n % 1 for n in numbers) else 100.0)
            elif (top := rating_max(name, numbers)) is not None:
                low, high = 0.0, top
            if low is not None or high is not None:
                rules.bounds[name] = (low, high)

        if (
            name not in rules.copies
            and name not in rules.optional  # never pre-fill free-text notes
            and name not in computed
            and name != entity.identifier_column
            and name not in links
            and column.inferred_type not in ("date", "bool")
            and len(rows) >= _MIN_EVIDENCE
            and len(values) == len(rows)
            and len({norm(v) for v in values}) == 1
        ):
            rules.constants[name] = values[0]

    rules.date_orders = _date_orders(entity, rows)

    strategy = entity.low_stock_strategy
    if strategy and strategy.type == "flow" and strategy.outbound_column and strategy.opening_column:
        supply = tuple(c for c in (strategy.opening_column, strategy.inbound_column) if c)
        rules.row_stock = RowStock(strategy.outbound_column, supply)

    if is_consumption_sheet(entity.worksheet):
        quantity = next(
            (c.name for c in entity.columns if c.role == FieldRole.QUANTITY and c.name not in computed and c.name not in links),
            None,
        )
        targets = {e.worksheet: e for e in config.entities}
        for link in links.values():
            target = targets.get(link.target)
            ts = target.low_stock_strategy if target else None
            if quantity is None or ts is None:
                continue
            if ts.type == "direct" and ts.quantity_column:
                rules.linked_stock = LinkedStock(quantity, link, ts.quantity_column)
            elif ts.type == "flow" and ts.opening_column:
                rules.linked_stock = LinkedStock(quantity, link, None, ts.opening_column, ts.inbound_column, ts.outbound_column)
            if rules.linked_stock:
                break

    if entity.status_column:
        status = next((c for c in entity.columns if c.name == entity.status_column), None)
        words = norm(entity.status_column).replace(" ", "")
        rules.strict_status = bool(status and status.role_confidence >= 0.7 and any(w in words for w in _STRICT_STATUS_WORDS))
    return rules
