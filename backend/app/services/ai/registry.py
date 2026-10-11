"""Resolves which configured provider the chatbot should use for a request."""

from app.core.config import Settings
from app.services.ai.base import LLMProvider, ProviderNotConfigured
from app.services.ai.providers import build_provider, configured_providers, known_provider_names

_ENV_VAR_BY_PROVIDER = {
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
}


def get_provider(settings: Settings, requested: str | None = None) -> LLMProvider:
    """Return the provider to use, or raise ProviderNotConfigured with a
    message naming exactly which environment variable is missing.
    """
    name = (requested or settings.chatbot_provider or "groq").lower()
    if name not in known_provider_names():
        known = ", ".join(sorted(known_provider_names()))
        raise ProviderNotConfigured(f"Unknown chatbot provider '{name}'. Known providers: {known}")

    provider = build_provider(name, settings)
    if provider is not None:
        return provider

    available = configured_providers(settings)
    if available:
        # The requested/default provider has no key, but another one does --
        # fall back rather than hard-failing the whole chatbot.
        fallback = build_provider(available[0], settings)
        if fallback is not None:
            return fallback

    env_var = _ENV_VAR_BY_PROVIDER.get(name, f"{name.upper()}_API_KEY")
    raise ProviderNotConfigured(
        f"No chatbot provider is configured. Set {env_var} in the backend environment "
        f"(or another of: {', '.join(_ENV_VAR_BY_PROVIDER.values())})."
    )
