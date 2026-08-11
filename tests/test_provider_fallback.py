from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.config import Settings
from app.container import _build_llm, _build_stt
from app.domain.enums import IntentType
from app.domain.schemas import ParsedIntent
from app.providers.llm.base import BaseIntentParser, IntentParseError
from app.providers.llm.fallback import FallbackIntentParser
from app.providers.llm.openai_compatible import _safe_fallback
from app.providers.stt.base import BaseTranscriptionProvider, TranscriptionError
from app.providers.stt.fallback import FallbackTranscriptionProvider
from app.providers.stt.openai_compatible import OpenAICompatibleSTTProvider
from app.providers.stt.openrouter import OpenRouterSTTProvider


class _FixedIntentParser(BaseIntentParser):
    def __init__(self, intent: ParsedIntent) -> None:
        self.intent = intent
        self.calls = 0

    async def parse(self, text: str, timezone: str = "Europe/Amsterdam") -> ParsedIntent:
        self.calls += 1
        return self.intent


class _FailingIntentParser(BaseIntentParser):
    def __init__(self) -> None:
        self.calls = 0

    async def parse(self, text: str, timezone: str = "Europe/Amsterdam") -> ParsedIntent:
        self.calls += 1
        raise IntentParseError("boom")


class _FixedTranscriptionProvider(BaseTranscriptionProvider):
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript
        self.calls = 0

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.ogg") -> str:
        self.calls += 1
        return self.transcript


class _FailingTranscriptionProvider(BaseTranscriptionProvider):
    def __init__(self) -> None:
        self.calls = 0

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.ogg") -> str:
        self.calls += 1
        raise TranscriptionError("timeout")


def _openrouter_response(
    *,
    status_code: int = 200,
    body: dict | None = None,
    text: str = "",
    json_error: Exception | None = None,
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    if json_error is not None:
        response.json = MagicMock(side_effect=json_error)
    else:
        response.json = MagicMock(return_value=body or {})
    return response


async def _transcribe_with_openrouter_first(
    post: AsyncMock,
) -> tuple[str, _FixedTranscriptionProvider]:
    fallback_provider = _FixedTranscriptionProvider("fallback transcript")
    provider = FallbackTranscriptionProvider(
        [
            ("openrouter", OpenRouterSTTProvider(api_key="openrouter-key")),
            ("fallback", fallback_provider),
        ]
    )

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = post
        mock_client_cls.return_value = mock_client

        result = await provider.transcribe(b"audio")

    return result, fallback_provider


@pytest.mark.asyncio
async def test_llm_fallback_tries_next_provider_on_exception():
    first = _FailingIntentParser()
    second = _FixedIntentParser(ParsedIntent(intent=IntentType.LIST_TASKS, confidence=0.8))
    parser = FallbackIntentParser([("groq", first), ("openrouter", second)])

    result = await parser.parse("покажи задачи")

    assert result.intent == IntentType.LIST_TASKS
    assert first.calls == 1
    assert second.calls == 1


@pytest.mark.asyncio
async def test_llm_fallback_tries_next_provider_on_safe_fallback():
    first = _FixedIntentParser(_safe_fallback())
    second = _FixedIntentParser(ParsedIntent(intent=IntentType.LIST_TASKS, confidence=0.8))
    parser = FallbackIntentParser([("groq", first), ("openrouter", second)])

    result = await parser.parse("покажи задачи")

    assert result.intent == IntentType.LIST_TASKS
    assert first.calls == 1
    assert second.calls == 1


@pytest.mark.asyncio
async def test_llm_fallback_returns_safe_fallback_when_all_providers_fail():
    parser = FallbackIntentParser([("groq", _FailingIntentParser())])

    result = await parser.parse("test")

    assert result.intent == IntentType.UNKNOWN
    assert result.requires_confirmation is True


@pytest.mark.asyncio
async def test_stt_fallback_tries_next_provider_on_error_or_empty_transcript():
    first = _FailingTranscriptionProvider()
    second = _FixedTranscriptionProvider("  ")
    third = _FixedTranscriptionProvider("купить молоко")
    provider = FallbackTranscriptionProvider(
        [("groq", first), ("openrouter-empty", second), ("openrouter", third)]
    )

    result = await provider.transcribe(b"audio")

    assert result == "купить молоко"
    assert first.calls == 1
    assert second.calls == 1
    assert third.calls == 1


@pytest.mark.asyncio
async def test_stt_fallback_raises_when_all_providers_fail():
    provider = FallbackTranscriptionProvider([("groq", _FailingTranscriptionProvider())])

    with pytest.raises(TranscriptionError, match="All STT providers failed"):
        await provider.transcribe(b"audio")


@pytest.mark.asyncio
async def test_stt_fallback_tries_next_provider_on_openrouter_http_error():
    post = AsyncMock(return_value=_openrouter_response(status_code=500, text="server error"))

    result, fallback_provider = await _transcribe_with_openrouter_first(post)

    assert result == "fallback transcript"
    assert fallback_provider.calls == 1


@pytest.mark.asyncio
async def test_stt_fallback_tries_next_provider_on_openrouter_timeout():
    post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    result, fallback_provider = await _transcribe_with_openrouter_first(post)

    assert result == "fallback transcript"
    assert fallback_provider.calls == 1


@pytest.mark.asyncio
async def test_stt_fallback_tries_next_provider_on_openrouter_empty_text():
    post = AsyncMock(return_value=_openrouter_response(body={"text": ""}))

    result, fallback_provider = await _transcribe_with_openrouter_first(post)

    assert result == "fallback transcript"
    assert fallback_provider.calls == 1


@pytest.mark.asyncio
async def test_stt_fallback_tries_next_provider_on_openrouter_malformed_json():
    post = AsyncMock(return_value=_openrouter_response(json_error=ValueError("bad json")))

    result, fallback_provider = await _transcribe_with_openrouter_first(post)

    assert result == "fallback transcript"
    assert fallback_provider.calls == 1


def test_container_builds_llm_fallback_in_groq_then_openrouter_order():
    cfg = Settings(
        _env_file=None,
        llm_provider="fallback",
        groq_api_key="groq-key",
        openrouter_api_key="openrouter-key",
    )

    parser = _build_llm(cfg)

    assert isinstance(parser, FallbackIntentParser)
    assert [name for name, _ in parser.providers] == ["groq", "openrouter"]
    assert parser.providers[0][1].model == "openai/gpt-oss-120b"
    assert parser.providers[1][1].model == "deepseek/deepseek-v4-flash"


def test_container_does_not_use_stt_api_key_for_groq_llm_fallback():
    cfg = Settings(
        _env_file=None,
        llm_provider="fallback",
        stt_api_key="groq-key",
        openrouter_api_key="openrouter-key",
    )

    parser = _build_llm(cfg)

    assert isinstance(parser, FallbackIntentParser)
    assert [name for name, _ in parser.providers] == ["openrouter"]


def test_container_builds_stt_fallback_in_groq_then_openrouter_order():
    cfg = Settings(
        _env_file=None,
        stt_provider="fallback",
        groq_api_key="groq-key",
        openrouter_api_key="openrouter-key",
    )

    provider = _build_stt(cfg)

    assert isinstance(provider, FallbackTranscriptionProvider)
    assert [name for name, _ in provider.providers] == ["groq", "openrouter"]
    assert provider.providers[0][1].model == "whisper-large-v3"
    assert provider.providers[1][1].model == "openai/whisper-large-v3"


def test_container_uses_openai_stt_key_as_fallback_provider():
    cfg = Settings(
        _env_file=None,
        stt_provider="fallback",
        stt_api_key="openai-key",
        stt_model="whisper-1",
        stt_base_url="https://api.openai.com/v1",
    )

    provider = _build_stt(cfg)

    assert isinstance(provider, FallbackTranscriptionProvider)
    assert [name for name, _ in provider.providers] == ["openai"]
    assert isinstance(provider.providers[0][1], OpenAICompatibleSTTProvider)
    assert provider.providers[0][1].api_key == "openai-key"


def test_container_direct_openrouter_stt_prefers_openrouter_key():
    cfg = Settings(
        _env_file=None,
        stt_provider="openrouter",
        stt_api_key="legacy-stt-key",
        openrouter_api_key="openrouter-key",
    )

    provider = _build_stt(cfg)

    assert isinstance(provider, OpenRouterSTTProvider)
    assert provider.api_key == "openrouter-key"


def test_provider_specific_stt_model_overrides_generic_openai_model():
    cfg = Settings(
        _env_file=None,
        stt_provider="fallback",
        stt_model="openai-specific-model",
        groq_api_key="groq-key",
        openrouter_api_key="openrouter-key",
        groq_stt_model="groq-specific-model",
        openrouter_stt_model="openrouter-specific-model",
    )

    provider = _build_stt(cfg)

    assert isinstance(provider, FallbackTranscriptionProvider)
    assert provider.providers[0][1].model == "groq-specific-model"
    assert provider.providers[1][1].model == "openrouter-specific-model"
