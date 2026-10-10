"""Deterministic KPI and alert computation from actual uploaded records.

Every KPI here is derived from columns the role-inference step (roles.py)
tagged with a specific meaning (amount, quantity, threshold, due date, ...).
If an entity doesn't have the columns a given KPI needs, that KPI is simply
not produced -- nothing is estimated or hardcoded to fill the gap.
"""

import re
from datetime import date, datetime

from app.services.analysis.types import (
    ColumnProfile,
    EntityConfig,
    FieldRole,
    KPIDefinition,
    LowStockStrategy,
    StatusBreakdownItem,
)

_CURRENT_STOCK_HINTS = ("onhand", "available", "balance", "currentstock", "instock", "netstock", "closingstock")
_OPENING_HINTS = ("opening",)
# Deliberately no bare "in"/"out" -- too short, collides with unrelated
# words like "opening" (which itself contains "in").
_INBOUND_HINTS = ("received", "purchased", "added", "incoming", "restocked", "inbound")
_OUTBOUND_HINTS = ("used", "consumed", "issued", "outgoing", "dispatched", "outbound")


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def resolve_low_stock_strategy(
    quantity_cols: list[ColumnProfile], threshold_col: ColumnProfile
) -> LowStockStrategy | None:
    """Pick how to read "current quantity" when a sheet has several
    quantity-shaped columns. A single Quantity-role column is the easy case,
    but inventory sheets often track opening/received/used instead of a
    running balance -- picking the first such column arbitrarily (e.g.
    "Opening Stock") silently produces a wrong low-stock comparison, so this
    looks for an explicit on-hand/balance column first, then falls back to
    deriving one from an opening+inbound-outbound triad if present.
    """
    if not quantity_cols:
        return None

    direct = next((c for c in quantity_cols if any(h in _normalize(c.name) for h in _CURRENT_STOCK_HINTS)), None)
    if direct:
        return LowStockStrategy(type="direct", quantity_column=direct.name, threshold_column=threshold_col.name)

    if len(quantity_cols) >= 2:
        opening = next((c for c in quantity_cols if any(h in _normalize(c.name) for h in _OPENING_HINTS)), None)
        remaining = [c for c in quantity_cols if c is not opening]
        inbound = next((c for c in remaining if any(h in _normalize(c.name) for h in _INBOUND_HINTS)), None)
        outbound = next((c for c in remaining if any(h in _normalize(c.name) for h in _OUTBOUND_HINTS)), None)
        if opening and (inbound or outbound):
            return LowStockStrategy(
                type="flow",
                threshold_column=threshold_col.name,
                opening_column=opening.name,
                inbound_column=inbound.name if inbound else None,
                outbound_column=outbound.name if outbound else None,
            )

    return LowStockStrategy(type="direct", quantity_column=quantity_cols[0].name, threshold_column=threshold_col.name)


def current_quantity(row: dict, strategy: LowStockStrategy) -> float | None:
    if strategy.type == "direct":
        return _numeric(row.get(strategy.quantity_column)) if strategy.quantity_column else None

    opening = _numeric(row.get(strategy.opening_column)) if strategy.opening_column else None
    if opening is None:
        return None
    inbound = (_numeric(row.get(strategy.inbound_column)) if strategy.inbound_column else None) or 0
    outbound = (_numeric(row.get(strategy.outbound_column)) if strategy.outbound_column else None) or 0
    return opening + inbound - outbound

RISK_KEYWORDS = (
    "risk",
    "delay",
    "overdue",
    "block",
    "critical",
    "pending",
    "open",
    "reject",
    "fail",
    "late",
    "over budget",
    "overbudget",
    "cancel",
)

DONE_KEYWORDS = ("done", "complete", "closed", "approved", "paid", "delivered", "resolved")

_DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S")


def is_risk_value(value: str) -> bool:
    lowered = value.strip().lower()
    return any(keyword in lowered for keyword in RISK_KEYWORDS)


def is_done_value(value: str) -> bool:
    lowered = value.strip().lower()
    return any(keyword in lowered for keyword in DONE_KEYWORDS)


_CRITICAL_STATUS_KEYWORDS = ("critical", "block", "fail")


def _status_alert_severity(value: str) -> str:
    lowered = value.strip().lower()
    return "critical" if any(k in lowered for k in _CRITICAL_STATUS_KEYWORDS) else "warning"


def parse_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    return None


def compute_status_breakdown(rows: list[dict], status_column: str | None) -> list[StatusBreakdownItem]:
    if status_column is None:
        return []
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(status_column)
        if value is None or str(value).strip() == "":
            continue
        key = str(value).strip()
        counts[key] = counts.get(key, 0) + 1
    return [
        StatusBreakdownItem(value=value, count=count, is_risk=is_risk_value(value))
        for value, count in sorted(counts.items(), key=lambda kv: -kv[1])
    ]


def _columns_by_role(columns: list[ColumnProfile], role: FieldRole) -> list[ColumnProfile]:
    return [c for c in columns if c.role == role]


def _numeric(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def compute_entity_kpis(entity: EntityConfig, rows: list[dict]) -> tuple[list[KPIDefinition], list[KPIDefinition]]:
    """Return (kpis, alerts) for a single entity."""
    kpis: list[KPIDefinition] = []
    alerts: list[KPIDefinition] = []

    kpis.append(
        KPIDefinition(
            key=f"{entity.worksheet}:count",
            label=f"Total {entity.label}",
            entity=entity.worksheet,
            value=len(rows),
            format="number",
        )
    )

    for col in _columns_by_role(entity.columns, FieldRole.BUDGET_AMOUNT) + _columns_by_role(
        entity.columns, FieldRole.ACTUAL_AMOUNT
    ) + _columns_by_role(entity.columns, FieldRole.AMOUNT):
        values = [_numeric(row.get(col.name)) for row in rows]
        values = [v for v in values if v is not None]
        if not values:
            continue
        label = col.name if col.name.strip().lower().startswith("total") else f"Total {col.name}"
        kpis.append(
            KPIDefinition(
                key=f"{entity.worksheet}:sum:{col.name}",
                label=label,
                entity=entity.worksheet,
                value=round(sum(values), 2),
                format="number",
            )
        )

    budget_cols = _columns_by_role(entity.columns, FieldRole.BUDGET_AMOUNT)
    actual_cols = _columns_by_role(entity.columns, FieldRole.ACTUAL_AMOUNT)
    if budget_cols and actual_cols:
        budget_col, actual_col = budget_cols[0], actual_cols[0]
        total_budget = sum(v for v in (_numeric(r.get(budget_col.name)) for r in rows) if v is not None)
        total_actual = sum(v for v in (_numeric(r.get(actual_col.name)) for r in rows) if v is not None)
        if total_budget > 0:
            pct_used = round((total_actual / total_budget) * 100, 1)
            kpis.append(
                KPIDefinition(
                    key=f"{entity.worksheet}:budget_used",
                    label="Budget Used",
                    entity=entity.worksheet,
                    value=pct_used,
                    format="percent",
                    detail=f"{total_actual:,.0f} of {total_budget:,.0f}",
                )
            )
        over_budget_count = sum(
            1
            for r in rows
            if (b := _numeric(r.get(budget_col.name))) is not None
            and (a := _numeric(r.get(actual_col.name))) is not None
            and a > b
        )
        if over_budget_count > 0:
            alert = KPIDefinition(
                key=f"{entity.worksheet}:over_budget",
                label=f"{entity.singular_label}s Over Budget",
                entity=entity.worksheet,
                value=over_budget_count,
                format="number",
                severity="warning",
                detail="Actual exceeds budget",
            )
            kpis.append(alert)
            alerts.append(alert)

    quantity_cols = _columns_by_role(entity.columns, FieldRole.QUANTITY)
    threshold_cols = _columns_by_role(entity.columns, FieldRole.THRESHOLD)
    if quantity_cols and threshold_cols:
        strategy = resolve_low_stock_strategy(quantity_cols, threshold_cols[0])
        entity.low_stock_strategy = strategy
        low_stock_count = sum(
            1
            for r in rows
            if (q := current_quantity(r, strategy)) is not None
            and (t := _numeric(r.get(strategy.threshold_column))) is not None
            and q <= t
        )
        if low_stock_count > 0:
            alert = KPIDefinition(
                key=f"{entity.worksheet}:low_stock",
                label="Low-Stock Alerts",
                entity=entity.worksheet,
                value=low_stock_count,
                format="number",
                severity="critical",
                detail="At or below reorder threshold",
            )
            kpis.append(alert)
            alerts.append(alert)

    due_date_cols = _columns_by_role(entity.columns, FieldRole.DUE_DATE)
    flag_cols = _columns_by_role(entity.columns, FieldRole.FLAG)
    status_cols = _columns_by_role(entity.columns, FieldRole.STATUS)
    if due_date_cols:
        due_col = due_date_cols[0]
        done_col = flag_cols[0] if flag_cols else None
        done_status_col = status_cols[0] if status_cols and not done_col else None
        today = date.today()
        overdue_count = 0
        for row in rows:
            due = parse_date(row.get(due_col.name))
            if due is None or due >= today:
                continue
            if done_col is not None and bool(row.get(done_col.name)):
                continue
            if done_status_col is not None:
                status_value = row.get(done_status_col.name)
                if status_value and is_done_value(str(status_value)):
                    continue
            overdue_count += 1
        if overdue_count > 0:
            alert = KPIDefinition(
                key=f"{entity.worksheet}:overdue",
                label=f"Overdue {entity.label}",
                entity=entity.worksheet,
                value=overdue_count,
                format="number",
                severity="warning",
                detail=f"Past due as of {today.isoformat()}",
            )
            kpis.append(alert)
            alerts.append(alert)

    # Generic "this status value looks like trouble" alert -- only when the
    # status column itself was picked with reasonable confidence (a strong
    # name hint, not the weak low-cardinality fallback), and only for a
    # genuinely categorical column, to avoid firing on something that merely
    # resembles a status by accident.
    status_col_profile = next((c for c in entity.columns if c.name == entity.status_column), None)
    if status_col_profile and status_col_profile.role_confidence >= 0.7 and len(entity.status_breakdown) <= 8:
        for item in entity.status_breakdown:
            if not item.is_risk or item.count == 0:
                continue
            alert = KPIDefinition(
                key=f"{entity.worksheet}:status:{item.value}",
                label=item.value,
                entity=entity.worksheet,
                value=item.count,
                format="number",
                severity=_status_alert_severity(item.value),
                detail=entity.label,
            )
            alerts.append(alert)

    return kpis, alerts
