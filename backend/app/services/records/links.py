"""Which columns hold references to records in another worksheet.

Two deterministic sources:
- detected relationships (column name matches another entity, values
  overlap), from the analysis engine; and
- value links: a text column whose values are (almost) all titles of
  another entity's records, e.g. Purchase Requests.Item holding material
  names. These matter for forms (pick from a list, look up unit cost) even
  when the column name doesn't say which worksheet it points at.
"""

import re
from dataclasses import dataclass

from app.services.analysis.types import FieldRole, PortalConfig

_VALUE_LINK_MIN_MATCH = 0.9
_VALUE_LINK_MIN_VALUES = 2
_ID_LIKE = re.compile(r"^(?=.*\d)(?=.*[a-z])[a-z0-9][a-z0-9_\-/ ]*$")


@dataclass(frozen=True)
class Link:
    entity: str  # worksheet holding the reference
    column: str  # column holding the reference value
    target: str  # referenced worksheet
    target_column: str  # column in `target` the value matches
    source: str  # "relationship" | "values"


def norm(value: object) -> str:
    return str(value).strip().lower() if value is not None else ""


def detect_links(config: PortalConfig, rows_by_entity: dict[str, list[dict]]) -> list[Link]:
    links = [
        Link(r.from_entity, r.from_column, r.to_entity, r.to_column, "relationship")
        for r in config.relationships
        if r.from_entity != r.to_entity
    ]
    linked = {(link.entity, link.column) for link in links}

    # Candidate keys: a target's identifier and title columns, but only when
    # each value names exactly one record. That rules out e.g. a "Sampler"
    # title shared by many samples, which would otherwise turn every person
    # column into a dropdown of samplers.
    keys: list[tuple[str, str, bool, set[str]]] = []  # (target, column, is_identifier, values)
    for e in config.entities:
        if e.reference:
            continue
        target_rows = rows_by_entity.get(e.worksheet, [])
        for column, is_id in ((e.identifier_column, True), (e.title_column, False)):
            if not column or (not is_id and column == e.identifier_column):
                continue
            # Sheets with an ID column are referred to by ID; a name column is
            # only a key for sheets without IDs. Person names are never keys.
            profile = next((c for c in e.columns if c.name == column), None)
            if not is_id and (e.identifier_column or (profile and profile.role == FieldRole.PERSON)):
                continue
            values = [norm(row.get(column)) for row in target_rows]
            values = [v for v in values if v]
            if values and len(set(values)) == len(values):
                keys.append((e.worksheet, column, is_id, set(values)))

    for entity in config.entities:
        if entity.reference:
            continue
        rows = rows_by_entity.get(entity.worksheet, [])
        for column in entity.columns:
            if column.inferred_type != "string" or column.name == entity.identifier_column:
                continue
            if (entity.worksheet, column.name) in linked:
                continue
            values = [norm(row.get(column.name)) for row in rows]
            values = [v for v in values if v]
            if not values:
                continue
            best: tuple[float, str, str] | None = None
            for target, key_column, is_id, key_values in keys:
                if target == entity.worksheet:
                    continue
                ratio = sum(v in key_values for v in values) / len(values)
                enough = len(values) >= _VALUE_LINK_MIN_VALUES and len(set(values)) >= 2
                # A single exact match is enough evidence for an ID-style code (BUY-001).
                single_id = is_id and ratio == 1.0 and all(_ID_LIKE.match(v) for v in values)
                if ratio >= _VALUE_LINK_MIN_MATCH and (enough or single_id) and (best is None or ratio > best[0]):
                    best = (ratio, target, key_column)
            if best:
                links.append(Link(entity.worksheet, column.name, best[1], best[2], "values"))
    return links


def links_from(links: list[Link], worksheet: str) -> dict[str, Link]:
    """Outgoing links of one worksheet, keyed by the referencing column."""
    return {link.column: link for link in links if link.entity == worksheet}


def find_linked_row(link: Link, value: object, rows_by_entity: dict[str, list[dict]]) -> dict | None:
    key = norm(value)
    if not key:
        return None
    return next((row for row in rows_by_entity.get(link.target, []) if norm(row.get(link.target_column)) == key), None)
