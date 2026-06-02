"""Tests for OpenRouterIntentParser JSON extraction and error handling."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.enums import IntentType
from app.providers.llm.openrouter import OpenRouterIntentParser, _extract_json, _safe_fallback

VALID_JSON_PAYLOAD = {
    "intent": "create_reminder",
    "title": "Купить молоко",
    "remind_at": "2026-06-03T09:00:00",
    "timezone": "Europe/Amsterdam",
    "confidence": 0.95,
    "requires_confirmation": False,
    "clarification_question": None,
    "snooze_until": None,
    "task_reference": None,
    "recurrence": None,
    "recurring_task_reference": None,
}


# ---------------------------------------------------------------------------
# _extract_json unit tests
# ---------------------------------------------------------------------------


def test_extract_json_valid_direct():
    raw = json.dumps(VALID_JSON_PAYLOAD)
    result = _extract_json(raw)
    assert result["intent"] == "create_reminder"
    assert result["title"] == "Купить молоко"


def test_extract_json_from_markdown_json_block():
    raw = f"```json\n{json.dumps(VALID_JSON_PAYLOAD)}\n```"
    result = _extract_json(raw)
    assert result["intent"] == "create_reminder"


def test_extract_json_from_plain_markdown_block():
    raw = f"```\n{json.dumps(VALID_JSON_PAYLOAD)}\n```"
    result = _extract_json(raw)
    assert result["intent"] == "create_reminder"


def test_extract_json_from_surrounding_text():
    raw = f"Here is the result:\n{json.dumps(VALID_JSON_PAYLOAD)}\nEnd of response."
    result = _extract_json(raw)
    assert result["intent"] == "create_reminder"


def test_extract_json_raises_on_invalid():
    with pytest.raises(ValueError, match="No valid JSON"):
        _extract_json("This is not JSON at all")


def test_extract_json_raises_on_truncated():
    truncated = json.dumps(VALID_JSON_PAYLOAD)[:-10]  # cut off the end
    with pytest.raises((ValueError, Exception)):
        _extract_json(truncated)


def test_extract_json_raises_on_empty_string():
    with pytest.raises(ValueError, match="No valid JSON"):
        _extract_json("")


def test_extract_json_raises_on_whitespace_only():
    with pytest.raises(ValueError, match="No valid JSON"):
        _extract_json("   \n  ")


# ---------------------------------------------------------------------------
# _safe_fallback
# ---------------------------------------------------------------------------


def test_safe_fallback_intent_is_unknown():
    fb = _safe_fallback()
    assert fb.intent == IntentType.UNKNOWN


def test_safe_fallback_requires_confirmation():
    fb = _safe_fallback()
    assert fb.requires_confirmation is True


def test_safe_fallback_confidence_is_zero():
    fb = _safe_fallback()
    assert fb.confidence == 0.0


def test_safe_fallback_has_clarification_question():
    fb = _safe_fallback()
    assert fb.clarification_question is not None
    assert len(fb.clarification_question) > 0


# ---------------------------------------------------------------------------
# OpenRouterIntentParser.parse — integration with mocked HTTP
# ---------------------------------------------------------------------------


def _make_parser() -> OpenRouterIntentParser:
    return OpenRouterIntentParser(
        api_key="test-key",
        model="openai/gpt-4o-mini",
        base_url="https://openrouter.ai/api/v1",
    )


def _mock_response(content: str | None) -> MagicMock:
    """Build a fake httpx response returning the given content string."""
    msg = {"content": content} if content is not None else {}
    body = {"choices": [{"message": msg}]}
    resp = MagicMock()
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_parse_valid_json():
    parser = _make_parser()
    raw = json.dumps(VALID_JSON_PAYLOAD)
    resp = _mock_response(raw)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=resp)
        mock_client_cls.return_value = mock_client

        result = await parser.parse("Купить молоко завтра утром")

    assert result.intent == IntentType.CREATE_REMINDER
    assert result.title == "Купить молоко"
    assert result.confidence == 0.95
    assert result.requires_confirmation is False


@pytest.mark.asyncio
async def test_parse_json_in_markdown_block():
    parser = _make_parser()
    raw = f"```json\n{json.dumps(VALID_JSON_PAYLOAD)}\n```"
    resp = _mock_response(raw)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=resp)
        mock_client_cls.return_value = mock_client

        result = await parser.parse("test")

    assert result.intent == IntentType.CREATE_REMINDER


@pytest.mark.asyncio
async def test_parse_json_with_surrounding_text():
    parser = _make_parser()
    raw = f"Sure! Here is the JSON:\n{json.dumps(VALID_JSON_PAYLOAD)}\nDone."
    resp = _mock_response(raw)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=resp)
        mock_client_cls.return_value = mock_client

        result = await parser.parse("test")

    assert result.intent == IntentType.CREATE_REMINDER


@pytest.mark.asyncio
async def test_parse_invalid_truncated_json_returns_fallback():
    parser = _make_parser()
    truncated = json.dumps(VALID_JSON_PAYLOAD)[:-20]
    resp = _mock_response(truncated)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=resp)
        mock_client_cls.return_value = mock_client

        result = await parser.parse("test")

    assert result.intent == IntentType.UNKNOWN
    assert result.requires_confirmation is True


@pytest.mark.asyncio
async def test_parse_none_content_returns_fallback():
    parser = _make_parser()
    resp = _mock_response(None)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=resp)
        mock_client_cls.return_value = mock_client

        result = await parser.parse("test")

    assert result.intent == IntentType.UNKNOWN
    assert result.requires_confirmation is True


@pytest.mark.asyncio
async def test_parse_empty_string_content_returns_fallback():
    parser = _make_parser()
    resp = _mock_response("   ")  # whitespace only

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=resp)
        mock_client_cls.return_value = mock_client

        result = await parser.parse("test")

    assert result.intent == IntentType.UNKNOWN
    assert result.requires_confirmation is True


@pytest.mark.asyncio
async def test_parse_network_error_returns_fallback():
    parser = _make_parser()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client_cls.return_value = mock_client

        result = await parser.parse("test")

    assert result.intent == IntentType.UNKNOWN
    assert result.requires_confirmation is True
    assert result.clarification_question is not None


@pytest.mark.asyncio
async def test_parse_400_retries_without_response_format():
    """On HTTP 400, parser retries the request without response_format."""
    parser = _make_parser()

    resp_400 = MagicMock()
    resp_400.status_code = 400
    resp_400.raise_for_status = MagicMock()

    resp_ok = _mock_response(json.dumps(VALID_JSON_PAYLOAD))
    resp_ok.status_code = 200

    call_payloads: list[dict] = []

    async def post_side_effect(url, **kwargs):
        call_payloads.append(kwargs.get("json", {}))
        return resp_400 if len(call_payloads) == 1 else resp_ok

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=post_side_effect)
        mock_client_cls.return_value = mock_client

        result = await parser.parse("test")

    assert len(call_payloads) == 2
    assert "response_format" in call_payloads[0]
    assert "response_format" not in call_payloads[1]
    assert result.intent == IntentType.CREATE_REMINDER


@pytest.mark.asyncio
async def test_parse_400_retry_also_fails_returns_fallback():
    """If the retry after 400 also fails, parser returns safe fallback."""
    parser = _make_parser()

    resp_400 = MagicMock()
    resp_400.status_code = 400

    resp_500 = MagicMock()
    resp_500.status_code = 500
    resp_500.raise_for_status = MagicMock(side_effect=Exception("Internal Server Error"))

    call_count = 0

    async def post_side_effect(url, **kwargs):
        nonlocal call_count
        call_count += 1
        return resp_400 if call_count == 1 else resp_500

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=post_side_effect)
        mock_client_cls.return_value = mock_client

        result = await parser.parse("test")

    assert result.intent == IntentType.UNKNOWN
    assert result.requires_confirmation is True
