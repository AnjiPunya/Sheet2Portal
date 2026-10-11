"""Turn the records a chat answer used into named, clickable references.

The backend always identifies a record by its real database id; users see
its business name ("Green Meadows Apartments", not "Projects #cc8957").
Shared by text chat and the voice assistant, and by the tool results the
model reads, so every surface names records the same way.

- names come from the record's own name column (Project_Name, Pond_Name...),
  falling back to its title or ID code;
- when two records share a name, the ID code is added to tell them apart;
- references to records that no longer exist are dropped (never relinked);
- actions: "View details", plus "View <sheet>" for every sheet whose records
  point at this one (a project's Tasks, Materials, Expenses...), with counts.
"""

import re
import uuid
from dataclasses import dataclass, field

from app.services.analysis.text import humanize
from app.services.analysis.types import EntityConfig, FieldRole
from app.services.records.display import display_labels
from app.services.records.links import norm
from app.services.records.schema import RecordContext, build_context


# Columns about people ("Recorded_By", "Owner", "Assigned_To") never name a record.
_PERSON_COLUMN = re.compile(r"\b(by|owner|manager|assigned|assignee|recorder|sampler|staff|employee|person|responsible)\b", re.I)


@dataclass
class ReferenceIndex:
    """Names and links for one workbook, built once per chat turn."""

    config: object
    records: dict[str, list]  # worksheet -> Record objects (id, data)
    record_ctx: RecordContext
    labels: dict[str, str] = field(default_factory=dict)  # record id -> display name
    worksheet_of: dict[str, str] = field(default_factory=dict)  # record id -> worksheet
    codes: dict[str, tuple[str, str]] = field(default_factory=dict)  # norm(ID code) -> (record id, raw code)

    def entity(self, worksheet: str) -> EntityConfig | None:
        return next((e for e in self.config.entities if e.worksheet == worksheet), None)


def _naming_column(entity: EntityConfig, rows: list) -> str | None:
    """The column that names this entity's records: an explicit "...Name"
    column (Project_Name, Pond_Name), else the detected title -- but only if
    its values are unique. A shared value like the person who recorded a log
    never names it; such records fall back to their ID code (FD-001)."""
    def unique(column: str | None) -> bool:
        values = [norm(r.data.get(column)) for r in rows] if column else []
        values = [v for v in values if v]
        return bool(values) and len(set(values)) == len(values)

    named = [
        c.name
        for c in entity.columns
        if c.inferred_type == "string" and c.name != entity.identifier_column and c.name.replace("_", "").lower().endswith("name")
    ]
    for column in named:  # explicit names count even when two records share one (codes break the tie)
        if any(norm(r.data.get(column)) for r in rows):
            return column
    title = entity.title_column
    profile = next((c for c in entity.columns if c.name == title), None)
    is_person = bool(profile and profile.role == FieldRole.PERSON) or bool(title and _PERSON_COLUMN.search(title.replace("_", " ")))
    if title and title != entity.identifier_column and not is_person and unique(title):
        return title
    return None


def _base_label(entity: EntityConfig, data: dict, naming: str | None) -> str | None:
    for column in (naming, entity.identifier_column, entity.title_column):
        if column and norm(data.get(column)):
            return str(data[column]).strip()
    first = next((v for v in data.values() if isinstance(v, str) and v.strip()), None)
    return first.strip() if first else None


def build_index(config, records_by_entity: dict[str, list]) -> ReferenceIndex:
    record_ctx = build_context(config, {ws: [r.data for r in rows] for ws, rows in records_by_entity.items()})
    index = ReferenceIndex(config=config, records=records_by_entity, record_ctx=record_ctx)
    for entity in config.entities:
        rows = records_by_entity.get(entity.worksheet, [])
        naming = _naming_column(entity, rows)
        base = {str(r.id): _base_label(entity, r.data, naming) for r in rows}
        counts: dict[str, int] = {}
        for label in base.values():
            if label:
                counts[norm(label)] = counts.get(norm(label), 0) + 1
        for record in rows:
            rid = str(record.id)
            label = base[rid] or humanize(entity.singular_label)
            code = record.data.get(entity.identifier_column) if entity.identifier_column else None
            # Same name on several records: add the ID code so they can be told apart.
            if counts.get(norm(label), 0) > 1 and norm(code) and norm(code) != norm(label):
                label = f"{label} ({code})"
            index.labels[rid] = label
            index.worksheet_of[rid] = entity.worksheet
            if norm(code) and norm(code) != norm(base[rid] or ""):
                index.codes.setdefault(norm(code), (rid, str(code).strip()))
    return index


def _related_actions(index: ReferenceIndex, worksheet: str, data: dict) -> list[dict]:
    """"View <sheet>" for each sheet whose records point at this record."""
    actions, seen = [], set()
    for link in index.record_ctx.links:
        if link.target != worksheet or link.entity in seen:
            continue
        key = norm(data.get(link.target_column))
        if not key:
            continue
        count = sum(1 for r in index.records.get(link.entity, []) if norm(r.data.get(link.column)) == key)
        entity = index.entity(link.entity)
        if count and entity and not entity.reference:
            seen.add(link.entity)
            actions.append({"kind": "related", "label": f"View {humanize(entity.label)}", "worksheet": link.entity, "count": count})
    return actions


def resolve_references(index: ReferenceIndex, refs: list[dict]) -> list[dict]:
    """Add name, entity label and actions to (worksheet, record_id) pairs;
    drop any whose record no longer exists in this workbook."""
    resolved = []
    for ref in refs:
        rid, worksheet = str(ref.get("record_id")), ref.get("worksheet")
        if index.worksheet_of.get(rid) != worksheet:
            continue  # deleted, or not a record of that worksheet: never link it
        record = next(r for r in index.records[worksheet] if str(r.id) == rid)
        entity = index.entity(worksheet)
        resolved.append(
            {
                "worksheet": worksheet,
                "record_id": rid,
                "label": index.labels[rid],
                "entity_label": humanize(entity.singular_label) if entity else humanize(worksheet),
                "actions": [{"kind": "details", "label": "View details", "worksheet": worksheet}, *_related_actions(index, worksheet, record.data)],
            }
        )
    return resolved


def record_summary(index: ReferenceIndex, worksheet: str, record) -> dict:
    """What tools hand the model for one record: its id (for further tool
    calls), its name, its data, and names for the records it references."""
    out = {"id": str(record.id), "label": index.labels.get(str(record.id)), "data": record.data}
    names = display_labels(index.record_ctx, worksheet, record.data)
    if names:
        out["references"] = names
    return out


_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_ASKED_FOR_IDS = re.compile(r"\b(id|ids|code|codes|identifier|reference number|uuid)\b", re.I)


def name_records_in_text(text: str, index: ReferenceIndex, question: str = "") -> str:
    """Replace internal record ids in an answer with record names:
    UUIDs and "#cc8957"-style fragments always; business ID codes (PRJ-001)
    only when the record's name isn't already given and the user didn't ask
    for IDs."""
    if not text:
        return text

    def uuid_name(match: re.Match) -> str:
        return index.labels.get(match.group(0).lower(), match.group(0))

    text = _UUID.sub(uuid_name, text)

    by_prefix: dict[str, str] = {}
    for rid in index.labels:
        by_prefix.setdefault(rid[:6].lower(), rid)
        by_prefix.setdefault(rid[:8].lower(), rid)

    def short_name(match: re.Match) -> str:
        rid = by_prefix.get(match.group("ref").lower())
        return index.labels[rid] if rid else match.group(0)

    # "Projects #cc8957" (the sheet name plus a short id) -> the record's name.
    sheet_names = {humanize(e.label) for e in index.config.entities} | {e.worksheet for e in index.config.entities}
    sheet_names |= {humanize(e.singular_label) for e in index.config.entities}
    alternatives = "|".join(re.escape(n) for n in sorted(sheet_names, key=len, reverse=True) if n)
    if alternatives:
        text = re.sub(rf"(?<![\w])(?:{alternatives})\s+#(?P<ref>[0-9a-f]{{6,8}})\b", short_name, text, flags=re.I)
    text = re.sub(r"(?<![\w#])#(?P<ref>[0-9a-f]{6,8})\b", short_name, text, flags=re.I)

    if _ASKED_FOR_IDS.search(question or ""):
        return text
    for _, (rid, code) in sorted(index.codes.items(), key=lambda kv: -len(kv[1][1])):
        label = index.labels[rid]
        if norm(label) in norm(text):
            continue  # the name is already there; the code just disambiguates
        text = re.sub(rf"(?<![\w-]){re.escape(code)}(?![\w-])", label, text)
    return text


def is_record_id(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False
