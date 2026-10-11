"""Thin per-provider configuration over the shared OpenAI-compatible client.

The Groq default matches the sibling Vedha/Orka project's tool-calling
model. Gemini uses the ``gemini-flash-latest`` alias: gemini-2.0-flash (still
referenced by Vedha) was shut down on 2026-06-01 and gemini-2.5-flash is
closed to new API keys, so a pinned version keeps breaking. OpenRouter uses its
``openrouter/free`` router, which picks a free model that supports the
features a request needs (tool calling included) -- free ``:free`` model IDs
rotate too often to hardcode one. Override any default via CHATBOT_MODEL.
"""

from app.core.config import Settings
from app.services.ai.openai_compatible import OpenAICompatibleProvider

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_DEFAULT_MODEL = "openai/gpt-oss-120b"

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GEMINI_DEFAULT_MODEL = "gemini-flash-latest"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_DEFAULT_MODEL = "openrouter/free"

# Same model/endpoint as Vedha's Cerebras fallback.
CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"
CEREBRAS_DEFAULT_MODEL = "gpt-oss-120b"

_PROVIDER_DEFAULTS = {
    "groq": (GROQ_URL, GROQ_DEFAULT_MODEL, "groq_api_key"),
    "gemini": (GEMINI_URL, GEMINI_DEFAULT_MODEL, "gemini_api_key"),
    "openrouter": (OPENROUTER_URL, OPENROUTER_DEFAULT_MODEL, "openrouter_api_key"),
    "cerebras": (CEREBRAS_URL, CEREBRAS_DEFAULT_MODEL, "cerebras_api_key"),
}


def build_provider(name: str, settings: Settings) -> OpenAICompatibleProvider | None:
    """Build the named provider, or None if it has no API key configured.

    Returning None (rather than raising) lets the registry try the next
    configured provider / report a clear "nothing configured" error.
    """
    entry = _PROVIDER_DEFAULTS.get(name.lower())
    if entry is None:
        return None
    url, default_model, key_field = entry
    api_key = getattr(settings, key_field)
    if not api_key:
        return None
    # CHATBOT_MODEL names a model of the *configured* provider; a fallback
    # provider would reject that name, so it keeps its own default.
    is_configured_provider = name.lower() == (settings.chatbot_provider or "").lower()
    return OpenAICompatibleProvider(
        name=name.lower(),
        api_key=api_key,
        base_url=url,
        model=(settings.chatbot_model if is_configured_provider else "") or default_model,
        timeout=settings.chat_request_timeout_seconds,
    )


def configured_providers(settings: Settings) -> list[str]:
    """Names of providers that currently have an API key available."""
    return [name for name in _PROVIDER_DEFAULTS if getattr(settings, _PROVIDER_DEFAULTS[name][2])]


def known_provider_names() -> list[str]:
    return list(_PROVIDER_DEFAULTS)
