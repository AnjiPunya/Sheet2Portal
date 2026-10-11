"""Readable labels for references: show "Green Meadows Apartments · Kompally"
next to PRJ-001, "North Pond" next to POND-001. Raw IDs stay in the data
(and in the UI as secondary text); this only adds display labels."""

import re

from app.services.analysis.types import EntityConfig, FieldRole
from app.services.records.links import Link, find_linked_row, links_from, norm
from app.services.records.schema import RecordContext

_LOCATION = re.compile(r"location|site|address|city|zone|block|plot|storage", re.I)


def _name_column(entity: EntityConfig, key: str) -> str | None:
    """The column that names a record: one called "...Name" (Project_Name,
    Vendor_Name) beats a guessed title, and never the key itself."""
    for column in entity.columns:
        if column.inferred_type == "string" and column.name != key and re.search(r"name$", column.name.replace("_", "").lower()):
            if column.role != FieldRole.PERSON or column.name == entity.title_column or "contact" not in column.name.lower():
                return column.name
    if entity.title_column and entity.title_column not in (key, entity.identifier_column):
        return entity.title_column
    return None


def _location_column(entity: EntityConfig, exclude: set[str]) -> str | None:
    return next(
        (c.name for c in entity.columns if c.inferred_type == "string" and c.name not in exclude and _LOCATION.search(c.name)),
        None,
    )


def link_label(ctx: RecordContext, link: Link, value: object) -> str | None:
    target = next((e for e in ctx.config.entities if e.worksheet == link.target), None)
    row = find_linked_row(link, value, ctx.rows_by_entity)
    if target is None or row is None:
        return None
    name = _name_column(target, link.target_column)
    parts = [str(row[name]).strip()] if name and norm(row.get(name)) else []
    location = _location_column(target, {link.target_column, name or ""})
    if location and norm(row.get(location)):
        parts.append(str(row[location]).strip())
    label = " · ".join(parts)
    return label if label and norm(label) != norm(value) else None


def display_labels(ctx: RecordContext, worksheet: str, data: dict) -> dict[str, str]:
    """column -> readable label, for every reference column with a match."""
    labels = {}
    for column, link in links_from(ctx.links, worksheet).items():
        label = link_label(ctx, link, data.get(column))
        if label:
            labels[column] = label
    return labels
