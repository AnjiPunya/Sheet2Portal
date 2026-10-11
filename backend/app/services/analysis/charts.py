"""Dashboard charts, chosen from what the workbook actually contains.

Deterministic and computed from the same rows as the KPI cards, so a chart
total always matches its card. A chart is only produced when its fields
exist and there's enough data for it to say something -- no empty or
one-bar charts. Nothing here is specific to a business domain: the
construction demo gets budget-vs-actual, approval, expenses-over-time and
status charts because of its column roles and values, not its name.
"""

from collections import defaultdict
from datetime import date, timedelta

from app.services.analysis.kpis import parse_date
from app.services.analysis.semantics import is_per_unit
from app.services.analysis.text import humanize


def _lower(label: str) -> str:
    """Sentence-case a label mid-title, keeping acronyms and units: "Total Seed Cost (INR)" -> "total seed cost (INR)"."""
    return " ".join(w if (w.isupper() or w.startswith("(")) else w[:1].lower() + w[1:] for w in label.split(" "))
from app.services.analysis.types import EntityConfig, FieldRole, PortalConfig

_MAX_BARS = 12
_MAX_STATUS_CHARTS = 3
_MAX_TIME_CHARTS = 2


def _num(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    return float(value) if isinstance(value, (int, float)) else None


def _first(entity: EntityConfig, *roles: FieldRole):
    return next((c for c in entity.columns if c.role in roles), None)


def budget_vs_actual(entity: EntityConfig, rows: list[dict]) -> dict | None:
    budget = _first(entity, FieldRole.BUDGET_AMOUNT)
    actual = _first(entity, FieldRole.ACTUAL_AMOUNT)
    if not (budget and actual and entity.title_column):
        return None
    items = []
    for row in rows:
        b, a = _num(row.get(budget.name)), _num(row.get(actual.name))
        label = row.get(entity.title_column)
        if b is None or a is None or label in (None, ""):
            continue
        items.append({"label": str(label), "values": [round(b, 2), round(a, 2)], "flag": "over" if a > b else None})
    if len(items) < 2:
        return None
    items.sort(key=lambda item: item["values"][0], reverse=True)
    return {
        "id": f"{entity.worksheet}:budget-vs-actual",
        "kind": "grouped_bar",
        "title": f"{humanize(entity.label)}: {_lower(humanize(budget.name))} vs {_lower(humanize(actual.name))}",
        "entity": entity.worksheet,
        "series": [humanize(budget.name), humanize(actual.name)],
        "items": items[:_MAX_BARS],
        "note": f"{sum(1 for i in items if i['flag'])} over budget" if any(i["flag"] for i in items) else None,
    }


def approval_breakdown(entity: EntityConfig, workflow) -> dict | None:
    counts = {item.value: item.count for item in entity.status_breakdown}
    segments = [
        {"label": workflow.approved, "value": counts.get(workflow.approved, 0), "status": "good"},
        {"label": workflow.pending, "value": counts.get(workflow.pending, 0), "status": "warning"},
        {"label": workflow.rejected, "value": counts.get(workflow.rejected, 0), "status": "critical"},
    ]
    other = sum(counts.values()) - sum(s["value"] for s in segments)
    if other > 0:
        segments.append({"label": "Other", "value": other, "status": "neutral"})
    if sum(s["value"] for s in segments) == 0:
        return None
    return {
        "id": f"{entity.worksheet}:approval",
        "kind": "status_stack",
        "title": f"{humanize(entity.label)} approval status",
        "entity": entity.worksheet,
        "segments": segments,
    }


def _bucket(day: date, unit: str) -> date:
    if unit == "day":
        return day
    if unit == "week":
        return day - timedelta(days=day.weekday())
    if unit == "month":
        return day.replace(day=1)
    return day.replace(month=3 * ((day.month - 1) // 3) + 1, day=1)


def _step(day: date, unit: str) -> date:
    if unit == "day":
        return day + timedelta(days=1)
    if unit == "week":
        return day + timedelta(days=7)
    months = 1 if unit == "month" else 3
    month = day.month - 1 + months
    return day.replace(year=day.year + month // 12, month=month % 12 + 1)


def amount_over_time(entity: EntityConfig, rows: list[dict]) -> dict | None:
    # Only per-transaction amounts (an expense, an order). Running/lifetime
    # totals -- a project's Spent, a customer's Total Spent (actual_amount
    # role), or anything on a sheet that carries a budget -- plotted by a
    # start/signup date would be meaningless, so they're skipped.
    if _first(entity, FieldRole.BUDGET_AMOUNT, FieldRole.ACTUAL_AMOUNT):
        return None
    # A total, not a unit price (Feed Logs: Total Cost, not Unit Cost per kg).
    amount = next((c for c in entity.columns if c.role == FieldRole.AMOUNT and not is_per_unit(c.name)), None)
    when = _first(entity, FieldRole.DATE)
    if not (amount and when):
        return None
    dated = [(parse_date(row.get(when.name)), _num(row.get(amount.name))) for row in rows]
    dated = [(d, v) for d, v in dated if d is not None and v is not None]
    if len(dated) < 3:
        return None
    first, last = min(d for d, _ in dated), max(d for d, _ in dated)
    span = (last - first).days
    unit = "day" if span <= 14 else "week" if span <= 120 else "month" if span <= 730 else "quarter"
    totals: dict[date, float] = defaultdict(float)
    for day, value in dated:
        totals[_bucket(day, unit)] += value
    if len(totals) < 2:
        return None
    # Continuous axis: include empty periods so gaps read as gaps.
    points, cursor, end = [], _bucket(first, unit), _bucket(last, unit)
    while cursor <= end and len(points) < 60:
        points.append({"period": cursor.isoformat(), "value": round(totals.get(cursor, 0.0), 2)})
        cursor = _step(cursor, unit)
    return {
        "id": f"{entity.worksheet}:over-time",
        "kind": "time_columns",
        "title": f"{humanize(entity.label)}: {_lower(humanize(amount.name))} by {unit}",
        "entity": entity.worksheet,
        "unit": unit,
        "series": humanize(amount.name),
        "points": points,
        "total": round(sum(v for _, v in dated), 2),
    }


def status_bars(entity: EntityConfig) -> dict | None:
    items = entity.status_breakdown
    if not (2 <= len(items) <= 8):
        return None
    status = next((c for c in entity.columns if c.name == entity.status_column), None)
    if status is None or status.role_confidence < 0.7:
        return None  # a guessed "status" (e.g. Recorded By, Species) isn't worth a chart
    return {
        "id": f"{entity.worksheet}:status",
        "kind": "status_bars",
        "title": f"{humanize(entity.label)} by {_lower(humanize(entity.status_column or 'status'))}",
        "entity": entity.worksheet,
        "items": [{"label": i.value, "value": i.count, "risk": i.is_risk} for i in items],
    }


def build_charts(config: PortalConfig, rows_by_entity: dict[str, list[dict]]) -> list[dict]:
    from app.services.records.workflow import detect_workflow  # records builds on analysis, not vice versa

    charts: list[dict] = []
    entities = [e for e in config.entities if not e.reference]

    for entity in entities:
        if chart := budget_vs_actual(entity, rows_by_entity.get(entity.worksheet, [])):
            charts.append(chart)

    workflow_entities = set()
    for entity in entities:
        workflow = detect_workflow(entity)
        if workflow and (chart := approval_breakdown(entity, workflow)):
            charts.append(chart)
            workflow_entities.add(entity.worksheet)

    time_charts = [
        chart
        for entity in sorted(entities, key=lambda e: e.worksheet in workflow_entities)  # prefer transaction sheets
        if (chart := amount_over_time(entity, rows_by_entity.get(entity.worksheet, [])))
    ]
    charts.extend(time_charts[:_MAX_TIME_CHARTS])

    # Status charts: the primary entity first, then work items with due dates,
    # then the rest; workflow entities already have their approval chart.
    def status_priority(entity: EntityConfig) -> tuple:
        has_due = any(c.role == FieldRole.DUE_DATE for c in entity.columns)
        return (entity.worksheet != config.primary_entity, not has_due, -entity.row_count)

    status_charts = [
        chart
        for entity in sorted(entities, key=status_priority)
        if entity.worksheet not in workflow_entities and (chart := status_bars(entity))
    ]
    charts.extend(status_charts[:_MAX_STATUS_CHARTS])
    return charts
