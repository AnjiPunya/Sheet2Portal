from pydantic import BaseModel, ConfigDict


class ColumnProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    position: int
    inferred_type: str
    type_confidence: float
    role: str
    role_confidence: float


class StatusBreakdownItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    value: str
    count: int
    is_risk: bool


class KPIDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    entity: str | None
    value: float | int | None
    format: str
    severity: str | None
    detail: str | None
    unavailable_reason: str | None


class LowStockStrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: str
    quantity_column: str | None
    threshold_column: str | None
    opening_column: str | None
    inbound_column: str | None
    outbound_column: str | None


class EntityConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    worksheet: str
    label: str
    singular_label: str
    icon: str
    identifier_column: str | None
    title_column: str | None
    status_column: str | None
    columns: list[ColumnProfileOut]
    layout: str
    row_count: int
    status_breakdown: list[StatusBreakdownItemOut]
    kpis: list[KPIDefinitionOut]
    low_stock_strategy: LowStockStrategyOut | None
    reference: bool = False


class RelationshipCandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_entity: str
    from_column: str
    to_entity: str
    to_column: str
    match_rate: float
    confidence: str


class PortalConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    entities: list[EntityConfigOut]
    kpis: list[KPIDefinitionOut]
    alerts: list[KPIDefinitionOut]
    relationships: list[RelationshipCandidateOut]
    primary_entity: str | None
    domain: str = "generic"
    charts: list[dict] = []


class RecordOut(BaseModel):
    id: str
    data: dict
    # Readable labels for reference columns (Project_ID -> "Green Meadows Apartments · Kompally").
    display: dict[str, str] = {}


class RecordPageOut(BaseModel):
    records: list[RecordOut]
    total: int
    page: int
    page_size: int
