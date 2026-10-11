"""Calculated fields, inferred from the workbook's own data.

If a numeric column equals the product of two other numbers in *every*
existing row -- both in the same row (Total = Qty x Price), or one looked up
through a link (Purchase Requests: Amount = Quantity x the material's Unit
Cost) -- it's treated as calculated: forms show it read-only and the server
computes it on every create/edit, so new records stay consistent with how
the workbook already behaves. Deterministic; no AI.
"""

from dataclasses import dataclass

from app.services.analysis.text import humanize
from app.services.analysis.types import EntityConfig, PortalConfig
from app.services.records.links import Link, find_linked_row, links_from

_MIN_ROWS = 2
_NUMERIC = ("int", "float")


@dataclass(frozen=True)
class Factor:
    column: str  # column name (in this entity, or in link.target)
    link: Link | None = None  # None: a column of the same record


@dataclass(frozen=True)
class Formula:
    target: str
    factors: tuple[Factor, Factor]

    def describe(self) -> str:
        parts = [humanize(f.column) if f.link is None else f"{humanize(f.column)} (from {humanize(f.link.target)})" for f in self.factors]
        return f"{humanize(self.target)} = {parts[0]} × {parts[1]}"


def _num(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def factor_value(factor: Factor, data: dict, rows_by_entity: dict[str, list[dict]]) -> float | None:
    """A factor's value for one record. A lookup factor uses the value
    stored on the record itself when present (a user override, e.g. a
    negotiated unit cost), otherwise the linked record's value."""
    own = _num(data.get(factor.column))
    if factor.link is None or own is not None:
        return own
    linked = find_linked_row(factor.link, data.get(factor.link.column), rows_by_entity)
    return _num(linked.get(factor.column)) if linked else None


def evaluate(formula: Formula, data: dict, rows_by_entity: dict[str, list[dict]]) -> float | None:
    a, b = (factor_value(f, data, rows_by_entity) for f in formula.factors)
    if a is None or b is None:
        return None
    return round(a * b, 2)


def _holds(formula: Formula, rows: list[dict], rows_by_entity: dict[str, list[dict]]) -> bool:
    checked = 0
    for row in rows:
        target = _num(row.get(formula.target))
        a, b = (factor_value(f, row, rows_by_entity) for f in formula.factors)
        if target is None or a is None or b is None:
            continue
        if abs(target - a * b) > 0.01 + 1e-9 * abs(target):
            return False
        checked += 1
    return checked >= _MIN_ROWS


def detect_formulas(
    entity: EntityConfig, config: PortalConfig, rows_by_entity: dict[str, list[dict]], links: list[Link]
) -> list[Formula]:
    rows = rows_by_entity.get(entity.worksheet, [])
    numeric = [c.name for c in entity.columns if c.inferred_type in _NUMERIC]
    own_names = {c.name for c in entity.columns}
    targets = {e.worksheet: e for e in config.entities}

    lookup_factors = [
        Factor(c.name, link)
        for link in links_from(links, entity.worksheet).values()
        if link.target in targets
        for c in targets[link.target].columns
        if c.inferred_type in _NUMERIC and c.name not in own_names
    ]

    formulas: list[Formula] = []
    used: set[str] = set()
    for target in numeric:
        others = [n for n in numeric if n != target and n not in used]
        candidates = [
            (Factor(a), Factor(b)) for i, a in enumerate(others) for b in others[i + 1 :]
        ] + [(Factor(a), lookup) for a in others for lookup in lookup_factors]
        for factors in candidates:
            formula = Formula(target, factors)
            if _holds(formula, rows, rows_by_entity):
                formulas.append(formula)
                used.add(target)  # a calculated column is never a factor of another
                break
    return formulas
