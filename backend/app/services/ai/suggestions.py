"""Deterministic suggested questions, derived from the same PortalConfig
(entities/KPIs/alerts) the dashboard already computes -- so suggestions are
automatically relevant to whatever domain the uploaded workbook is in,
without any per-domain logic here.
"""

from app.services.analysis.types import KPIDefinition, PortalConfig

_ALERT_QUESTION_BY_KIND = {
    "low_stock": "Which items in {entity} are low on stock?",
    "overdue": "Which {entity} are overdue?",
    "over_budget": "Which {entity} are over budget?",
}


def _entity_label(config: PortalConfig, worksheet: str | None) -> str:
    entity = next((e for e in config.entities if e.worksheet == worksheet), None)
    return entity.label if entity else (worksheet or "records")


def _alert_question(alert: KPIDefinition, config: PortalConfig) -> str:
    entity_label = _entity_label(config, alert.entity)
    kind = alert.key.rsplit(":", 1)[-1]
    template = _ALERT_QUESTION_BY_KIND.get(kind)
    if template:
        return template.format(entity=entity_label)
    return f'Which {entity_label} have status "{alert.label}"?'


def generate_suggestions(config: PortalConfig, max_suggestions: int = 6) -> list[str]:
    suggestions: list[str] = []

    primary = next((e for e in config.entities if e.worksheet == config.primary_entity), None)
    if primary:
        suggestions.append(f"How many {primary.label.lower()} are there in total?")
        budget_used = next((k for k in primary.kpis if k.label == "Budget Used"), None)
        if budget_used:
            suggestions.append(f"What's the total budget and how much has been spent on {primary.label.lower()}?")

    for alert in config.alerts:
        if len(suggestions) >= max_suggestions:
            break
        question = _alert_question(alert, config)
        if question not in suggestions:
            suggestions.append(question)

    return suggestions[:max_suggestions]
