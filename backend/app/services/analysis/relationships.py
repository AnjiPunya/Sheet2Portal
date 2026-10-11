"""Deterministic cross-worksheet relationship detection.

A column is a *candidate* foreign key when its (normalized) name matches
another entity's singular/plural label, optionally with an id/name/code
suffix (e.g. "Project", "ProjectID", "Project Name" -> the "Projects"
entity). A candidate is only kept if its actual values overlap with the
target entity's identifying column -- name matching alone is not treated as
proof, per the "no silent certainty on ambiguous mappings" rule. The
resulting ``match_rate`` is surfaced so the caller can distinguish a
confirmed relationship from a weak guess rather than asserting one.
"""

from app.services.analysis.text import normalize_key
from app.services.analysis.types import EntityConfig, IdentifiedRow, PortalConfig, RelationshipCandidate

_SUFFIXES = ("id", "name", "code", "no", "number", "ref")


def _matches_entity_key(col_key: str, entity_key: str) -> bool:
    if not entity_key:
        return False
    if col_key == entity_key:
        return True
    return any(col_key == entity_key + suffix for suffix in _SUFFIXES)


def _distinct_values(rows: list[dict], column: str) -> set[str]:
    values = set()
    for row in rows:
        value = row.get(column)
        if value is not None and str(value).strip() != "":
            values.add(str(value).strip().lower())
    return values


def detect_relationships(
    entities: list[EntityConfig], rows_by_entity: dict[str, list[dict]]
) -> list[RelationshipCandidate]:
    entity_keys: list[tuple[str, EntityConfig]] = []
    for entity in entities:
        entity_keys.append((normalize_key(entity.singular_label), entity))
        entity_keys.append((normalize_key(entity.label), entity))

    candidates: list[RelationshipCandidate] = []

    for entity in entities:
        rows = rows_by_entity.get(entity.worksheet, [])
        for col in entity.columns:
            if col.inferred_type not in ("string", "int"):
                continue

            col_key = normalize_key(col.name)
            target = next(
                (
                    target_entity
                    for entity_key, target_entity in entity_keys
                    if target_entity.worksheet != entity.worksheet and _matches_entity_key(col_key, entity_key)
                ),
                None,
            )
            if target is None:
                continue

            source_values = _distinct_values(rows, col.name)
            if not source_values:
                continue

            # Try every plausible identifying column on the target (its
            # identifier and its title) and keep whichever actually overlaps
            # best -- the "best guess" identifier column can be wrong, so
            # name matching alone never gets to assert the relationship.
            best_column: str | None = None
            best_rate = 0.0
            for target_column in {c for c in (target.identifier_column, target.title_column) if c}:
                target_values = _distinct_values(rows_by_entity.get(target.worksheet, []), target_column)
                if not target_values:
                    continue
                rate = len(source_values & target_values) / len(source_values)
                if rate > best_rate:
                    best_rate, best_column = rate, target_column

            if best_column is None or best_rate < 0.3:
                continue

            confidence = "high" if best_rate >= 0.8 else "medium" if best_rate >= 0.5 else "low"
            candidates.append(
                RelationshipCandidate(
                    from_entity=entity.worksheet,
                    from_column=col.name,
                    to_entity=target.worksheet,
                    to_column=best_column,
                    match_rate=round(best_rate, 2),
                    confidence=confidence,
                )
            )

    return candidates


def related_rows_for(
    worksheet: str,
    record_data: dict,
    config: PortalConfig,
    rows_by_entity: dict[str, list[IdentifiedRow]],
) -> list[dict]:
    """Find records related to ``record_data`` (a row from ``worksheet``) via
    the config's already-detected relationships, in both directions:
    outgoing (this row references another entity) and incoming (another
    entity's rows reference this one, by identifier or title). Shared by the
    record-detail API and the chatbot's traverse-relationship tool so both
    stay behaviorally identical.
    """
    related: list[dict] = []

    for rel in config.relationships:
        if rel.from_entity != worksheet:
            continue
        value = record_data.get(rel.from_column)
        if value is None or str(value).strip() == "":
            continue
        matches = [
            row
            for row in rows_by_entity.get(rel.to_entity, [])
            if str(row.data.get(rel.to_column, "")).strip().lower() == str(value).strip().lower()
        ]
        if matches:
            related.append(
                {
                    "entity": rel.to_entity,
                    "relationship": f"{rel.from_column} -> {rel.to_entity}",
                    "records": [{"id": m.id, "data": m.data} for m in matches],
                }
            )

    entity = next((e for e in config.entities if e.worksheet == worksheet), None)
    identity_columns = {c for c in (entity.identifier_column, entity.title_column) if c} if entity else set()
    for rel in config.relationships:
        if rel.to_entity != worksheet or rel.to_column not in identity_columns:
            continue
        own_value = record_data.get(rel.to_column)
        if own_value is None:
            continue
        matches = [
            row
            for row in rows_by_entity.get(rel.from_entity, [])
            if str(row.data.get(rel.from_column, "")).strip().lower() == str(own_value).strip().lower()
        ]
        if matches:
            related.append(
                {
                    "entity": rel.from_entity,
                    "relationship": f"{rel.from_entity}.{rel.from_column}",
                    "records": [{"id": m.id, "data": m.data} for m in matches],
                }
            )

    return related
