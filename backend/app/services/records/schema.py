"""Per-entity form schema and the context every record operation needs.

Everything is derived from the workbook (column types, roles, links,
calculated fields, workflow, field rules), so the same create/edit
framework works for any worksheet in any domain.
"""

import re
from dataclasses import dataclass, field

from app.services.analysis.kpis import is_done_value
from app.services.analysis.text import humanize
from app.services.analysis.types import EntityConfig, PortalConfig
from app.services.records.field_rules import _NON_NEGATIVE_ROLES, FieldRules, analyse_fields
from app.services.records.formulas import Formula, detect_formulas
from app.services.records.links import Link, detect_links, links_from, norm
from app.services.records.statuses import status_options
from app.services.records.workflow import Workflow, detect_workflow


def status_choices(entity: EntityConfig) -> list[str]:
    """Every valid status for the entity: the workbook's own values plus the
    rest of their lifecycle (so a task can be marked Completed even if none
    is yet)."""
    values = [item.value for item in entity.status_breakdown]
    if not entity.status_column:
        return values
    return status_options(values, entity.worksheet, entity.status_column)

__all__ = ["_NON_NEGATIVE_ROLES", "EntityRules", "RecordContext", "build_context", "form_schema", "next_identifier"]

_ID_PATTERN = re.compile(r"^(?P<prefix>[A-Za-z]+[-_ ]?)(?P<number>\d+)$")
_MAX_OPTIONS = 500
_MAX_SUGGESTIONS = 12


@dataclass(frozen=True)
class IdPattern:
    """How to generate the next ID. Either one prefix (PR-1007), or a prefix
    chosen by another field (Party_Type Supplier -> SUP-007, Buyer -> BUY-002)."""

    width: int
    prefix: str | None = None
    by_column: str | None = None
    prefixes: tuple[tuple[str, str], ...] = ()  # (normalised by_column value, prefix)

    def prefix_for(self, data: dict) -> str | None:
        if self.prefix is not None:
            return self.prefix
        value = norm(data.get(self.by_column))
        return dict(self.prefixes).get(value)


@dataclass
class EntityRules:
    entity: EntityConfig
    rows: list[dict]
    links: dict[str, Link]  # outgoing, by column (selectable references)
    formulas: list[Formula]
    workflow: Workflow | None
    required: set[str]
    id_pattern: IdPattern | None
    fields: FieldRules
    extra_fields: list[str] = field(default_factory=list)  # lookup factors stored on the record (e.g. Unit Cost)
    all_links: dict[str, Link] = field(default_factory=dict)  # including links shown as auto-filled copies

    @property
    def computed(self) -> set[str]:
        return {f.target for f in self.formulas}

    def column(self, name: str):
        return next((c for c in self.entity.columns if c.name == name), None)


@dataclass
class RecordContext:
    config: PortalConfig
    rows_by_entity: dict[str, list[dict]]
    links: list[Link]

    def rules(self, worksheet: str) -> EntityRules | None:
        entity = next((e for e in self.config.entities if e.worksheet == worksheet), None)
        if entity is None or entity.reference:
            return None  # documentation sheets are read-only
        rows = self.rows_by_entity.get(worksheet, [])
        formulas = detect_formulas(entity, self.config, self.rows_by_entity, self.links)
        computed = {f.target for f in formulas}
        all_links = links_from(self.links, worksheet)
        field_rules = analyse_fields(entity, rows, all_links, self.config, self.rows_by_entity, computed)
        # A column that's just the name of a record picked in another field
        # (Material_or_Service next to Material_ID) is filled in, not picked.
        derived = {name for name, copy in field_rules.copies.items() if copy.derived}
        links = {name: link for name, link in all_links.items() if name not in derived}
        extra = [f.column for formula in formulas for f in formula.factors if f.link is not None]
        return EntityRules(
            entity=entity,
            rows=rows,
            links=links,
            formulas=formulas,
            workflow=detect_workflow(entity),
            required=_required_columns(entity, rows, computed, field_rules),
            id_pattern=_id_pattern(entity, rows),
            fields=field_rules,
            extra_fields=extra,
            all_links=all_links,
        )


def build_context(config: PortalConfig, rows_by_entity: dict[str, list[dict]]) -> RecordContext:
    return RecordContext(config, rows_by_entity, detect_links(config, rows_by_entity))


def _required_columns(entity: EntityConfig, rows: list[dict], computed: set[str], fields: FieldRules) -> set[str]:
    """A field is required if it's the record's title, or if every existing
    row has a value for it -- except calculated or auto-filled fields and
    free-text extras like notes, which never block saving."""
    required = {entity.title_column} if entity.title_column else set()
    if len(rows) >= 2:
        for column in entity.columns:
            if column.inferred_type == "bool":
                continue
            if all(row.get(column.name) not in (None, "") for row in rows):
                required.add(column.name)
    derived = {name for name, copy in fields.copies.items() if copy.derived}
    return required - computed - fields.optional - derived


def _id_pattern(entity: EntityConfig, rows: list[dict]) -> IdPattern | None:
    """IDs like PR-1001 / ORD-1006 are generated (next number). Several
    prefixes are supported when another field decides which one applies."""
    if not entity.identifier_column or not rows:
        return None
    matches = [_ID_PATTERN.match(str(row.get(entity.identifier_column) or "").strip()) for row in rows]
    if not all(matches):
        return None
    width = max(len(m.group("number")) for m in matches)
    prefixes = {m.group("prefix") for m in matches}
    if len(prefixes) == 1:
        return IdPattern(width=width, prefix=prefixes.pop())
    for column in entity.columns:
        if column.name == entity.identifier_column or column.inferred_type != "string":
            continue
        mapping: dict[str, str] = {}
        consistent = True
        for row, match in zip(rows, matches):
            key = norm(row.get(column.name))
            if not key or mapping.setdefault(key, match.group("prefix")) != match.group("prefix"):
                consistent = False
                break
        if consistent and len(set(mapping.values())) == len(prefixes):
            return IdPattern(width=width, by_column=column.name, prefixes=tuple(sorted(mapping.items())))
    return None


def next_identifier(rules: EntityRules, data: dict | None = None) -> str | None:
    pattern = rules.id_pattern
    if not pattern:
        return None
    prefix = pattern.prefix_for(data or {})
    if prefix is None:
        return None
    numbers = [
        int(m.group("number"))
        for m in (_ID_PATTERN.match(str(row.get(rules.entity.identifier_column) or "").strip()) for row in rules.rows)
        if m and m.group("prefix") == prefix
    ]
    return f"{prefix}{str(max(numbers, default=0) + 1).zfill(pattern.width)}"


def _input_for(type_: str) -> str:
    return {"int": "number", "float": "number", "date": "date", "bool": "checkbox"}.get(type_, "text")


def _base_spec(name: str, type_: str, role: str) -> dict:
    return {
        "name": name,
        "label": humanize(name),
        "type": type_,
        "input": _input_for(type_),
        "role": role,
        "required": False,
        "readonly": False,
        "computed": None,
        "options": None,
        "option_labels": None,
        "suggestions": None,
        "min": None,
        "max": None,
        "format": None,
        "auto": None,
        "hint": None,
    }


def _link_options(ctx: RecordContext, link: Link) -> tuple[list[str], dict[str, str] | None]:
    target = next((e for e in ctx.config.entities if e.worksheet == link.target), None)
    target_rows = ctx.rows_by_entity.get(link.target, [])
    values = sorted({str(r.get(link.target_column)).strip() for r in target_rows if norm(r.get(link.target_column))})[:_MAX_OPTIONS]
    labels = None
    # Codes (POND-001) read better with the record's name beside them.
    if target and target.title_column and target.title_column != link.target_column:
        by_key = {norm(r.get(link.target_column)): r.get(target.title_column) for r in target_rows}
        labels = {v: f"{v} · {by_key[norm(v)]}" for v in values if by_key.get(norm(v))}
    return values, labels


def _lookup_defaults(ctx: RecordContext, link: Link, source_column: str) -> dict:
    return {
        str(r.get(link.target_column)).strip(): r.get(source_column)
        for r in ctx.rows_by_entity.get(link.target, [])
        if norm(r.get(link.target_column))
    }


def form_schema(ctx: RecordContext, rules: EntityRules) -> dict:
    """What the frontend renders. Option lists and limits come from the
    workbook's own data; the backend re-validates everything on submit."""
    entity = rules.entity
    fr = rules.fields
    fields: list[dict] = []
    for column in entity.columns:
        name = column.name
        spec = _base_spec(name, column.inferred_type, column.role.value)
        spec["required"] = name in rules.required
        low, high = fr.bounds.get(name, (None, None))
        spec.update(min=low, max=high)
        link = rules.links.get(name)
        formula = next((f for f in rules.formulas if f.target == name), None)
        copy = fr.copies.get(name)

        if formula:
            spec.update(readonly=True, computed=formula.describe(), required=False)
        elif copy and copy.derived:
            spec.update(
                readonly=True,
                required=False,
                lookup={"from": copy.link.column, "entity": copy.link.target, "defaults": _lookup_defaults(ctx, copy.link, copy.source_column)},
                hint=f"Filled in from the selected {humanize(copy.link.column)}.",
            )
        elif link:
            options, labels = _link_options(ctx, link)
            spec.update(input="select", options=options, option_labels=labels, link={"entity": link.target, "column": link.target_column})
        elif name == entity.status_column and rules.workflow and name == rules.workflow.status_column:
            # Workflow-controlled: set by approve/reject actions, never typed in.
            spec.update(input="select", options=[i.value for i in entity.status_breakdown], readonly=True, required=False, workflow=True, default=rules.workflow.pending)
        elif name == entity.status_column and fr.strict_status:
            spec.update(input="select", options=status_choices(entity))
        elif name in fr.choices:
            spec.update(type="string", input="select", options=fr.choices[name])
        elif name in fr.formats:
            fmt = fr.formats[name]
            spec.update(type="string", input={"tel": "tel", "email": "email", "time": "time"}[fmt], format=fmt, min=None, max=None)
        elif column.inferred_type == "string" and name != entity.identifier_column:
            distinct = sorted({str(r.get(name)).strip() for r in rules.rows if norm(r.get(name))})
            if 1 < len(distinct) <= _MAX_SUGGESTIONS and len(rules.rows) >= 3 and len(distinct) < len(rules.rows):
                spec["suggestions"] = distinct

        if copy and not copy.derived and not formula:
            spec["lookup"] = {"from": copy.link.column, "entity": copy.link.target, "defaults": _lookup_defaults(ctx, copy.link, copy.source_column)}
            spec["hint"] = f"Filled in from the selected {humanize(copy.link.column)}; you can change it."
        if name in fr.constants and not spec["readonly"]:
            spec["default"] = fr.constants[name]
            spec["hint"] = "Pre-filled: every existing record uses this value."
        if name == entity.identifier_column:
            pattern = rules.id_pattern
            if pattern and pattern.prefix is not None:
                spec.update(auto="next_id", required=False, placeholder=next_identifier(rules), hint="Generated automatically if left blank.")
            elif pattern:
                by_value = {
                    str(r.get(pattern.by_column)).strip(): next_identifier(rules, r)
                    for r in rules.rows
                    if norm(r.get(pattern.by_column))
                }
                spec.update(
                    auto="next_id",
                    required=False,
                    auto_by={"column": pattern.by_column, "next": by_value},
                    hint=f"Generated from {humanize(pattern.by_column)} if left blank.",
                )
            else:
                spec["hint"] = "Must be unique."
        for order in fr.date_orders:
            if order.end == name:
                spec["after"] = order.start
                spec["hint"] = f"Can't be before {humanize(order.start)}."
        if fr.row_stock and name == fr.row_stock.outbound:
            spec["max_sum"] = list(fr.row_stock.supply)
            spec["hint"] = f"Can't exceed {' + '.join(humanize(s) for s in fr.row_stock.supply)}."
        stock = fr.linked_stock
        if stock and name == stock.quantity:
            available = {
                str(r.get(stock.link.target_column)).strip(): stock.available(r)
                for r in ctx.rows_by_entity.get(stock.link.target, [])
                if norm(r.get(stock.link.target_column))
            }
            spec["max_from"] = {"from": stock.link.column, "entity": stock.link.target, "available": available}
            spec["hint"] = f"Can't exceed the stock available in {humanize(stock.link.target)}."
        fields.append(spec)

    # Lookup factors (e.g. a purchase request's Unit Cost, looked up from the
    # selected material) are editable inputs, prefilled from the lookup.
    for formula in rules.formulas:
        for factor in formula.factors:
            if factor.link is None or any(f["name"] == factor.column for f in fields):
                continue
            spec = _base_spec(factor.column, "float", "amount")
            spec.update(
                required=True,
                min=0,
                lookup={"from": factor.link.column, "entity": factor.link.target, "defaults": _lookup_defaults(ctx, factor.link, factor.column)},
            )
            # Show it right after the field it's looked up from.
            index = next((i for i, f in enumerate(fields) if f["name"] == factor.link.column), len(fields) - 1)
            fields.insert(index + 1, spec)

    workflow = rules.workflow
    return {
        "worksheet": entity.worksheet,
        "label": humanize(entity.label),
        "singular_label": humanize(entity.singular_label),
        "identifier_column": entity.identifier_column,
        "title_column": entity.title_column,
        "fields": fields,
        "formulas": [
            {
                "target": f.target,
                "factors": [{"column": x.column, "lookup_from": x.link.column if x.link else None} for x in f.factors],
                "description": f.describe(),
            }
            for f in rules.formulas
        ],
        "workflow": (
            {
                "status_column": workflow.status_column,
                "pending": workflow.pending,
                "approved": workflow.approved,
                "rejected": workflow.rejected,
            }
            if workflow
            else None
        ),
        "done_statuses": [value for value in status_choices(entity) if is_done_value(value)],
    }

