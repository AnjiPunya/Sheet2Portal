"""Orchestrates the rule-based pipeline: parsed worksheets -> PortalConfig.

Entirely deterministic -- no AI involved. Column role inference (roles.py),
KPI computation (kpis.py) and relationship detection (relationships.py) are
independent, testable rule sets; this module wires them together in two
passes:

1. Profile columns and make a first guess at identifier/title/status per
   entity, using only within-entity signals (name + value shape).
2. Detect cross-entity relationships using those guesses as targets, then
   go back and reclassify any column that turned out to be a foreign key
   (a column named after another entity, whose values actually resolve
   there) -- a naive single pass would leave columns like "Project" in a
   Tasks sheet misread as a low-cardinality "status" field, which then
   corrupts status breakdowns, KPIs and the identifier pick for that sheet.
"""

from app.services.analysis.kpis import compute_entity_kpis, compute_status_breakdown
from app.services.analysis.relationships import detect_relationships
from app.services.analysis.roles import profile_column
from app.services.analysis.text import humanize, singularize
from app.services.analysis.types import ColumnProfile, EntityConfig, FieldRole, PortalConfig, SheetData

_ICON = "table"
_CARD_LAYOUT_MIN_DESCRIPTIVE_FIELDS = 2
_DESCRIPTIVE_ROLES = {
    FieldRole.STATUS,
    FieldRole.PERSON,
    FieldRole.DATE,
    FieldRole.DUE_DATE,
    FieldRole.BUDGET_AMOUNT,
    FieldRole.ACTUAL_AMOUNT,
    FieldRole.AMOUNT,
}


def _pick_by_role(columns: list[ColumnProfile], role: FieldRole) -> str | None:
    candidates = sorted((c for c in columns if c.role == role), key=lambda c: -c.role_confidence)
    return candidates[0].name if candidates else None


def _pick_title_column(columns: list[ColumnProfile]) -> str | None:
    title = _pick_by_role(columns, FieldRole.TITLE)
    if title:
        return title
    strings = [c for c in columns if c.inferred_type == "string"]
    return strings[0].name if strings else None


def _choose_layout(columns: list[ColumnProfile]) -> str:
    has_title = any(c.role == FieldRole.TITLE for c in columns)
    descriptive = sum(1 for c in columns if c.role in _DESCRIPTIVE_ROLES)
    return "cards" if has_title and descriptive >= _CARD_LAYOUT_MIN_DESCRIPTIVE_FIELDS else "table"


def _resolve_entity_picks(entity: EntityConfig) -> None:
    entity.identifier_column = _pick_by_role(entity.columns, FieldRole.IDENTIFIER)
    entity.title_column = _pick_title_column(entity.columns)
    entity.status_column = _pick_by_role(entity.columns, FieldRole.STATUS)
    entity.layout = _choose_layout(entity.columns)


def _choose_primary_entity(entities: list[EntityConfig], relationships) -> str | None:
    if not entities:
        return None
    inbound_counts: dict[str, int] = {}
    for rel in relationships:
        inbound_counts[rel.to_entity] = inbound_counts.get(rel.to_entity, 0) + 1
    if inbound_counts:
        return max(inbound_counts.items(), key=lambda kv: kv[1])[0]

    pool = [e for e in entities if e.layout == "cards"] or entities
    return max(pool, key=lambda e: e.row_count).worksheet


def build_portal_config(workbook_title: str, sheets: list[SheetData]) -> PortalConfig:
    entities: list[EntityConfig] = []
    rows_by_entity: dict[str, list[dict]] = {}

    # Pass 1: profile + naive per-entity picks (within-entity signals only).
    for sheet in sheets:
        if not sheet.columns or not sheet.rows:
            continue

        profiled = [
            profile_column(name, i, inferred_type, confidence, [row.get(name) for row in sheet.rows])
            for i, (name, inferred_type, confidence) in enumerate(sheet.columns)
        ]
        label = humanize(sheet.name)

        entity = EntityConfig(
            worksheet=sheet.name,
            label=label,
            singular_label=singularize(label),
            icon=_ICON,
            identifier_column=None,
            title_column=None,
            status_column=None,
            columns=profiled,
            row_count=len(sheet.rows),
        )
        _resolve_entity_picks(entity)
        entities.append(entity)
        rows_by_entity[sheet.name] = sheet.rows

    # Pass 2: detect relationships against the naive picks, then reclassify
    # any column that turned out to be a foreign key and re-resolve that
    # entity's identifier/title/status from the corrected roles.
    relationships = detect_relationships(entities, rows_by_entity)

    fk_by_entity: dict[str, set[str]] = {}
    for rel in relationships:
        fk_by_entity.setdefault(rel.from_entity, set()).add(rel.from_column)

    for entity in entities:
        fk_columns = fk_by_entity.get(entity.worksheet)
        if not fk_columns:
            continue
        changed = False
        for col in entity.columns:
            if col.name in fk_columns and col.role != FieldRole.FOREIGN_KEY:
                match = next(
                    (r for r in relationships if r.from_entity == entity.worksheet and r.from_column == col.name),
                    None,
                )
                col.role = FieldRole.FOREIGN_KEY
                col.role_confidence = match.match_rate if match else 0.5
                changed = True
        if changed:
            _resolve_entity_picks(entity)
            entity.status_breakdown = compute_status_breakdown(rows_by_entity[entity.worksheet], entity.status_column)

    for entity in entities:
        if not entity.status_breakdown:
            entity.status_breakdown = compute_status_breakdown(
                rows_by_entity[entity.worksheet], entity.status_column
            )

    all_kpis = []
    all_alerts = []
    for entity in entities:
        kpis, alerts = compute_entity_kpis(entity, rows_by_entity[entity.worksheet])
        entity.kpis = kpis
        all_kpis.extend(kpis)
        all_alerts.extend(alerts)

    return PortalConfig(
        title=workbook_title,
        entities=entities,
        kpis=all_kpis,
        alerts=all_alerts,
        relationships=relationships,
        primary_entity=_choose_primary_entity(entities, relationships),
    )
