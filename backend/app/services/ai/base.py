from typing import Any, Protocol


class LLMProvider(Protocol):
    """Provider-agnostic interface for structured AI calls.

    Implementations (Anthropic, OpenAI, ...) are added starting Stage 2
    (AI-assisted schema discovery). Kept to a single method deliberately --
    this is scaffolding for a capability this pass does not yet use.
    """

    async def complete_structured(
        self, system: str, prompt: str, json_schema: dict[str, Any]
    ) -> dict[str, Any]:
        """Return a JSON object conforming to ``json_schema``."""
        ...
