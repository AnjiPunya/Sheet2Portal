"""HTTP plumbing shared by the STT/TTS clients: one place that maps transport
failures and status codes onto the chatbot's existing ProviderError family,
so the voice route reports them exactly like the chat route does."""

import httpx

from app.services.ai.base import ProviderError, ProviderRateLimited, ProviderTimeout, ProviderUnavailable


# Indirection so tests can inject an ``httpx.MockTransport`` without
# patching httpx globally.
client_factory = httpx.AsyncClient


class ProviderRejectedAudio(ProviderError):
    """The provider could not decode/process the uploaded audio (HTTP 400/413/415)."""


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


async def post(name: str, url: str, timeout: float, *, audio_request: bool = False, **kwargs) -> httpx.Response:
    """POST and raise a ProviderError subclass for anything but 2xx. Error
    messages never include request headers (where the API key lives)."""
    try:
        async with client_factory(timeout=timeout) as client:
            response = await client.post(url, **kwargs)
    except httpx.TimeoutException as exc:
        raise ProviderTimeout(f"{name} request timed out") from exc
    except httpx.RequestError as exc:
        raise ProviderUnavailable(f"{name} request failed: {type(exc).__name__}") from exc

    status = response.status_code
    if status == 429:
        raise ProviderRateLimited(name, retry_after=_retry_after(response))
    if status >= 500:
        raise ProviderUnavailable(f"{name} returned HTTP {status}")
    if status in (401, 403):
        raise ProviderError(f"{name} rejected the configured API key (HTTP {status})")
    if status in (400, 413, 415, 422) and audio_request:
        raise ProviderRejectedAudio(f"{name} could not process the audio (HTTP {status})")
    if status >= 400:
        raise ProviderError(f"{name} returned HTTP {status}: {response.text[:200]}")
    return response
