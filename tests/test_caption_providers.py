"""Two providers, one of which is expected to be down at any given time."""

import httpx
import pytest
import respx

from sau.captions.providers import (
    GEMINI_BASE_URL,
    OPENROUTER_URL,
    CaptionError,
    GeminiProvider,
    OpenRouterProvider,
    _read_gemini,
    _read_openrouter,
    available,
    complete,
)
from sau.config import Settings
from sau.errors import PlatformError


def settings(**overrides) -> Settings:
    base = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "redis_url": "redis://localhost:6379/15",
    }
    return Settings(**{**base, **overrides})


GEMINI_URL = f"{GEMINI_BASE_URL}/models/gemini-2.5-flash:generateContent"
REPLY = '{"hooks": [{"part": 1, "hook": "a"}]}'


def gemini_ok(text=REPLY):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def openrouter_ok(text=REPLY):
    return {"choices": [{"message": {"content": text}}]}


class TestReadGemini:
    def test_returns_the_text(self):
        assert _read_gemini(gemini_ok("hi")) == "hi"

    def test_joins_multiple_parts(self):
        payload = {"candidates": [{"content": {"parts": [{"text": "a"}, {"text": "b"}]}}]}
        assert _read_gemini(payload) == "ab"

    def test_a_safety_block_is_named_not_indexed_into(self):
        # Gemini reports this as HTTP 200 with no candidates at all.
        with pytest.raises(PlatformError, match="blocked"):
            _read_gemini({"promptFeedback": {"blockReason": "SAFETY"}})

    def test_no_candidates_is_reported(self):
        with pytest.raises(PlatformError, match="no candidates"):
            _read_gemini({"candidates": []})

    def test_empty_text_carries_the_finish_reason(self):
        payload = {"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]}
        with pytest.raises(PlatformError, match="MAX_TOKENS"):
            _read_gemini(payload)


class TestReadOpenRouter:
    def test_returns_the_text(self):
        assert _read_openrouter(openrouter_ok("hi")) == "hi"

    def test_upstream_error_in_a_200_body_is_raised(self):
        with pytest.raises(PlatformError, match="upstream"):
            _read_openrouter({"error": {"message": "provider offline"}})

    def test_no_choices_is_reported(self):
        with pytest.raises(PlatformError, match="no choices"):
            _read_openrouter({"choices": []})


class TestAvailable:
    def test_skips_providers_with_no_key(self):
        names = [p.name for p in available(settings(gemini_api_key="k"))]
        assert names == ["gemini"]

    def test_respects_the_configured_order(self):
        config = settings(
            gemini_api_key="k",
            openrouter_api_key="k",
            caption_providers=["openrouter", "gemini"],
        )
        assert [p.name for p in available(config)] == ["openrouter", "gemini"]

    def test_an_unknown_name_is_skipped_not_fatal(self):
        config = settings(gemini_api_key="k", caption_providers=["nope", "gemini"])
        assert [p.name for p in available(config)] == ["gemini"]

    def test_nothing_configured_is_an_empty_list(self):
        assert available(settings()) == []


class TestComplete:
    @respx.mock
    def test_the_first_provider_serves(self):
        route = respx.post(GEMINI_URL).mock(return_value=httpx.Response(200, json=gemini_ok()))
        reply, provider = complete("prompt", settings(gemini_api_key="k", openrouter_api_key="k"))
        assert provider == "gemini"
        assert reply == REPLY
        assert route.called

    @respx.mock
    def test_falls_back_to_the_second_when_the_first_fails(self):
        # A 401 rather than a 500 on purpose: one provider's key being wrong is
        # precisely the case the other one exists for, and it must not retry
        # its way through the backoff first.
        respx.post(GEMINI_URL).mock(return_value=httpx.Response(401, json={"error": "bad key"}))
        openrouter = respx.post(OPENROUTER_URL).mock(
            return_value=httpx.Response(200, json=openrouter_ok())
        )

        reply, provider = complete("prompt", settings(gemini_api_key="k", openrouter_api_key="k"))
        assert provider == "openrouter"
        assert reply == REPLY
        assert openrouter.called

    @respx.mock
    def test_order_is_configurable_so_either_can_be_primary(self):
        respx.post(OPENROUTER_URL).mock(return_value=httpx.Response(200, json=openrouter_ok()))
        _, provider = complete(
            "prompt",
            settings(
                gemini_api_key="k",
                openrouter_api_key="k",
                caption_providers=["openrouter", "gemini"],
            ),
        )
        assert provider == "openrouter"

    @respx.mock
    def test_every_provider_failing_raises_and_names_them(self):
        respx.post(GEMINI_URL).mock(return_value=httpx.Response(401, json={}))
        respx.post(OPENROUTER_URL).mock(return_value=httpx.Response(401, json={}))
        with pytest.raises(CaptionError, match="gemini, openrouter"):
            complete("prompt", settings(gemini_api_key="k", openrouter_api_key="k"))

    def test_no_provider_configured_says_so_plainly(self):
        with pytest.raises(CaptionError, match="GEMINI_API_KEY"):
            complete("prompt", settings())

    @respx.mock
    def test_the_gemini_key_travels_in_a_header_not_the_url(self):
        route = respx.post(GEMINI_URL).mock(return_value=httpx.Response(200, json=gemini_ok()))
        complete("prompt", settings(gemini_api_key="secret"))
        request = route.calls[0].request
        assert request.headers["x-goog-api-key"] == "secret"
        assert "secret" not in str(request.url)


class TestConfigured:
    def test_gemini_needs_a_key(self):
        assert GeminiProvider(settings()).configured() is False
        assert GeminiProvider(settings(gemini_api_key="k")).configured() is True

    def test_openrouter_needs_a_key(self):
        assert OpenRouterProvider(settings()).configured() is False
        assert OpenRouterProvider(settings(openrouter_api_key="k")).configured() is True
