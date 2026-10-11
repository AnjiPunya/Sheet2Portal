from dataclasses import dataclass, field
from enum import Enum


class FieldRole(str, Enum):
    IDENTIFIER = "identifier"
    TITLE = "title"
    STATUS = "status"
    DATE = "date"
    DUE_DATE = "due_date"
    BUDGET_AMOUNT = "budget_amount"
    ACTUAL_AMOUNT = "actual_amount"
    AMOUNT = "amount"
    QUANTITY = "quantity"
    THRESHOLD = "threshold"
    FLAG = "flag"
    PERSON = "person"
    FOREIGN_KEY = "foreign_key"
    OTHER = "other"


@dataclass
class ColumnProfile:
    name: str
    position: int
    inferred_type: str
    type_confidence: float
    role: FieldRole
    role_confidence: float
    distinct_count: int
    null_count: int


@dataclass
class RelationshipCandidate:
    from_entity: str
    from_column: str
    to_entity: str
    to_column: str
    match_rate: float
    confidence: str  # "high" | "medium" | "low"


@dataclass
class KPIDefinition:
    key: str
    label: str
    entity: str | None
    value: float | int | None
    format: str  # "number" | "currency" | "percent"
    severity: str | None = None
    detail: str | None = None
    unavailable_reason: str | None = None


@dataclass
class StatusBreakdownItem:
    value: str
    count: int
    is_risk: bool


@dataclass
class LowStockStrategy:
    """How to compute "current quantity" for a low-stock comparison.

    ``direct``: a single column already represents on-hand quantity.
    ``flow``: no single column does, but the sheet has an opening balance
    plus inbound/outbound movement columns, so current quantity is derived
    as opening + inbound - outbound. Exposed (rather than computed once and
    thrown away) so the frontend can apply the same rule per-row for
    highlighting without having to reverse-engineer it.
    """

    type: str  # "direct" | "flow"
    quantity_column: str | None = None
    threshold_column: str | None = None
    opening_column: str | None = None
    inbound_column: str | None = None
    outbound_column: str | None = None


@dataclass
class EntityConfig:
    worksheet: str
    label: str
    singular_label: str
    icon: str
    identifier_column: str | None
    title_column: str | None
    status_column: str | None
    columns: list[ColumnProfile] = field(default_factory=list)
    layout: str = "table"  # "cards" | "table"
    row_count: int = 0
    status_breakdown: list[StatusBreakdownItem] = field(default_factory=list)
    kpis: list[KPIDefinition] = field(default_factory=list)
    low_stock_strategy: LowStockStrategy | None = None
    # Documentation sheet (README, Data Dictionary, KPI definitions...):
    # read-only, never totalled, charted or alerted on.
    reference: bool = False


@dataclass
class IdentifiedRow:
    """A data row paired with its persisted record id -- the minimal shape
    relationship traversal needs, independent of whether the caller is
    working with SQLAlchemy ``Record`` objects or something else."""

    id: str
    data: dict


@dataclass
class SheetData:
    """Input to the analysis engine: a worksheet's already-parsed columns and rows."""

    name: str
    columns: list[tuple[str, str, float]]  # (name, inferred_type, type_confidence)
    rows: list[dict]


@dataclass
class PortalConfig:
    title: str
    entities: list[EntityConfig] = field(default_factory=list)
    kpis: list[KPIDefinition] = field(default_factory=list)
    alerts: list[KPIDefinition] = field(default_factory=list)
    relationships: list[RelationshipCandidate] = field(default_factory=list)
    primary_entity: str | None = None
    # Business domain ("construction", "aquaculture", ... or "generic"), used
    # only to theme the portal (dashboard banner); never affects calculations.
    domain: str = "generic"
    # Dashboard charts chosen from the data (see analysis/charts.py).
    charts: list[dict] = field(default_factory=list)
