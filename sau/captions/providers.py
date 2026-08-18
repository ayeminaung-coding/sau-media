"""Text generation providers for drafting caption hooks.

Two providers, tried in order, because neither is worth depending on alone:
Gemini is cheap and direct, OpenRouter reaches the same model (and dozens of
others) through a different account and a different network path. Whichever is
listed first serves; the next one covers it when it is down, rate limited, or
refuses the prompt.

Both are plain JSON over HTTPS, so neither brings a vendor SDK with it -- the
existing `httpx` dependency and the existing retry helper are the whole
transport story.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx

from sau.config import Settings, get_settings
from sau.errors import PlatformError, SauError
from sau.http import build_client, is_retryable, with_retries
from sau.logging import get_logger

log = get_logger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class CaptionError(SauError):
    """No configured provider produced a draft."""


class Provider(ABC):
    """One text generator, reduced to the single call this feature makes."""

    name: str

    @abstractmethod
    def configured(self) -> bool:
        """Whether this provider has the credentials to be worth attempting."""

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Return the model's reply as raw text. Raises `PlatformError`."""


def _timeout(settings: Settings) -> httpx.Timeout:
    # Generating a dozen hooks in one call is slower than any platform request
    # but far from the upload timeouts, so it gets its own budget.
    seconds = settings.caption_timeout_seconds
    return httpx.Timeout(connect=10.0, read=seconds, write=30.0, pool=10.0)


def _fail(provider: str, response: httpx.Response) -> PlatformError:
    """Turn a non-2xx reply into the error taxonomy the retry helper reads."""
    detail = response.text[:500]
    return PlatformError(
        f"caption request failed: {detail}",
        platform=provider,
        retryable=is_retryable(response),
        status_code=response.status_code,
    )


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def configured(self) -> bool:
        return bool(self._settings.gemini_api_key)

    def complete(self, prompt: str) -> str:
        model = self._settings.gemini_model
        url = f"{GEMINI_BASE_URL}/models/{model}:generateContent"
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            # Asking for JSON is what makes the reply parseable without
            # scraping a code fence off the front of it.
            "generationConfig": {"temperature": 0.9, "responseMimeType": "application/json"},
        }

        def call() -> str:
            with build_client(timeout=_timeout(self._settings)) as client:
                # The key goes in a header, not the `?key=` query parameter
                # Gemini also accepts: a URL lands in logs and proxy traces.
                response = client.post(
                    url,
                    json=body,
                    headers={"x-goog-api-key": self._settings.gemini_api_key},
                )
            if response.status_code >= 400:
                raise _fail(self.name, response)
            return _read_gemini(response.json())

        return with_retries(call, attempts=3, label="gemini.generate")


def _read_gemini(payload: Any) -> str:
    """Pull the text out of a Gemini reply, naming what went wrong instead.

    A safety block returns HTTP 200 with no candidates at all, so the absence
    has to be reported rather than indexed into.
    """
    if not isinstance(payload, dict):
        raise PlatformError("gemini returned a non-object body", platform="gemini")

    blocked = (payload.get("promptFeedback") or {}).get("blockReason")
    if blocked:
        raise PlatformError(f"gemini blocked the prompt: {blocked}", platform="gemini")

    candidates = payload.get("candidates") or []
    if not candidates:
        raise PlatformError("gemini returned no candidates", platform="gemini")

    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts)
    if not text.strip():
        reason = candidates[0].get("finishReason", "unknown")
        raise PlatformError(f"gemini returned empty text ({reason})", platform="gemini")
    return text


class OpenRouterProvider(Provider):
    name = "openrouter"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def configured(self) -> bool:
        return bool(self._settings.openrouter_api_key)

    def complete(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self._settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        if self._settings.openrouter_referer:
            headers["HTTP-Referer"] = self._settings.openrouter_referer
        if self._settings.openrouter_title:
            headers["X-Title"] = self._settings.openrouter_title

        body = {
            "model": self._settings.openrouter_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.9,
            "response_format": {"type": "json_object"},
        }

        def call() -> str:
            with build_client(timeout=_timeout(self._settings)) as client:
                response = client.post(OPENROUTER_URL, json=body, headers=headers)
            if response.status_code >= 400:
                raise _fail(self.name, response)
            return _read_openrouter(response.json())

        return with_retries(call, attempts=3, label="openrouter.generate")


def _read_openrouter(payload: Any) -> str:
    """Pull the text out of an OpenAI-shaped reply.

    OpenRouter reports upstream provider failures in a 200 body with an
    `error` member and no choices, so a bare index would raise a KeyError
    several layers from the cause.
    """
    if not isinstance(payload, dict):
        raise PlatformError("openrouter returned a non-object body", platform="openrouter")

    error = payload.get("error")
    if error:
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise PlatformError(f"openrouter upstream error: {message}", platform="openrouter")

    choices = payload.get("choices") or []
    if not choices:
        raise PlatformError("openrouter returned no choices", platform="openrouter")

    text = (choices[0].get("message") or {}).get("content") or ""
    if not text.strip():
        raise PlatformError("openrouter returned empty content", platform="openrouter")
    return text


_REGISTRY: dict[str, type[GeminiProvider] | type[OpenRouterProvider]] = {
    GeminiProvider.name: GeminiProvider,
    OpenRouterProvider.name: OpenRouterProvider,
}


def available(settings: Settings | None = None) -> list[Provider]:
    """The configured providers, in the order they should be tried.

    An unknown name is logged and skipped rather than raising: a typo in
    `CAPTION_PROVIDERS` should not take the whole API down at import time.
    """
    settings = settings or get_settings()
    providers: list[Provider] = []
    for name in settings.caption_providers:
        factory = _REGISTRY.get(name.strip().lower())
        if factory is None:
            log.warning("captions.provider.unknown", provider=name)
            continue
        provider = factory(settings)
        if provider.configured():
            providers.append(provider)
    return providers


def complete(prompt: str, settings: Settings | None = None) -> tuple[str, str]:
    """Run `prompt` against the first provider that answers.

    Returns the reply and the name of the provider that gave it. Every failure
    falls through to the next provider, including an auth failure: one
    provider's key being wrong is precisely the case the other exists for.
    """
    providers = available(settings)
    if not providers:
        raise CaptionError(
            "No caption provider is configured. Set GEMINI_API_KEY or "
            "OPENROUTER_API_KEY, or write the hooks by hand."
        )

    last: Exception | None = None
    for provider in providers:
        try:
            reply = provider.complete(prompt)
        except (PlatformError, httpx.HTTPError) as exc:
            log.warning("captions.provider.failed", provider=provider.name, error=str(exc))
            last = exc
            continue
        log.info("captions.provider.served", provider=provider.name)
        return reply, provider.name

    tried = ", ".join(p.name for p in providers)
    raise CaptionError(f"every caption provider failed ({tried}): {last}") from last
