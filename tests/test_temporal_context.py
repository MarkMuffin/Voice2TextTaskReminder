"""Tests for build_llm_temporal_context and temporal context injection in the parser."""

import json
from datetime import datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytz

from app.providers.llm.openrouter import OpenRouterIntentParser, build_llm_temporal_context
from tests.test_openrouter_parser import VALID_JSON_PAYLOAD

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dt(
    year: int,
    month: int,
    day: int,
    hour: int = 12,
    minute: int = 0,
    tz_name: str = "Europe/Amsterdam",
) -> datetime:
    tz = pytz.timezone(tz_name)
    return cast(datetime, tz.localize(datetime(year, month, day, hour, minute, 0)))


def _make_parser() -> OpenRouterIntentParser:
    return OpenRouterIntentParser(api_key="test-key")


def _mock_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# build_llm_temporal_context — unit tests
# ---------------------------------------------------------------------------


def test_context_contains_all_four_fields():
    ctx = build_llm_temporal_context(_dt(2026, 6, 3, 21, 14), "Europe/Amsterdam")
    assert "Current datetime:" in ctx
    assert "Current date: 2026-06-03" in ctx
    assert "Current weekday: Wednesday" in ctx
    assert "User timezone: Europe/Amsterdam" in ctx


def test_context_wednesday():
    # June 3, 2026 is a Wednesday
    ctx = build_llm_temporal_context(_dt(2026, 6, 3), "Europe/Amsterdam")
    assert "Current weekday: Wednesday" in ctx


def test_context_friday():
    # June 5, 2026 is a Friday
    ctx = build_llm_temporal_context(_dt(2026, 6, 5), "Europe/Amsterdam")
    assert "Current weekday: Friday" in ctx


def test_context_saturday():
    # June 6, 2026 is a Saturday
    ctx = build_llm_temporal_context(_dt(2026, 6, 6), "Europe/Amsterdam")
    assert "Current weekday: Saturday" in ctx


def test_context_sunday():
    # June 7, 2026 is a Sunday
    ctx = build_llm_temporal_context(_dt(2026, 6, 7), "Europe/Amsterdam")
    assert "Current weekday: Sunday" in ctx


def test_context_around_midnight():
    # "завтра" at 23:58 on Wednesday must still report Wednesday, not Thursday
    ctx = build_llm_temporal_context(_dt(2026, 6, 3, 23, 58), "Europe/Amsterdam")
    assert "Current date: 2026-06-03" in ctx
    assert "Current weekday: Wednesday" in ctx


def test_context_different_timezone():
    ctx = build_llm_temporal_context(_dt(2026, 6, 3, 9, 0, tz_name="Asia/Tokyo"), "Asia/Tokyo")
    assert "User timezone: Asia/Tokyo" in ctx
    assert "Current weekday: Wednesday" in ctx


def test_context_dst_summer():
    """Summer: Amsterdam is UTC+2 — offset must appear in ISO string."""
    tz = pytz.timezone("Europe/Amsterdam")
    dt = tz.localize(datetime(2026, 7, 15, 12, 0))
    ctx = build_llm_temporal_context(dt, "Europe/Amsterdam")
    assert "Current date: 2026-07-15" in ctx
    assert "+02:00" in ctx


def test_context_dst_winter():
    """Winter: Amsterdam is UTC+1 — offset must appear in ISO string."""
    tz = pytz.timezone("Europe/Amsterdam")
    dt = tz.localize(datetime(2026, 1, 15, 12, 0))
    ctx = build_llm_temporal_context(dt, "Europe/Amsterdam")
    assert "Current date: 2026-01-15" in ctx
    assert "+01:00" in ctx


# ---------------------------------------------------------------------------
# Relative date scenarios — verify correct context is built
# (LLM is mocked; we verify the context injected so the model can reason correctly)
# ---------------------------------------------------------------------------


def test_context_v_subbotu_when_wednesday():
    """'в субботу' from Wednesday: nearest Saturday is +3 days (June 6)."""
    ctx = build_llm_temporal_context(_dt(2026, 6, 3), "Europe/Amsterdam")
    # LLM sees Wednesday + Current date 2026-06-03 → computes Saturday as 2026-06-06
    assert "Current weekday: Wednesday" in ctx
    assert "Current date: 2026-06-03" in ctx


def test_context_v_voskresenye_when_friday():
    """'в воскресенье' from Friday: nearest Sunday is +2 days (June 7)."""
    ctx = build_llm_temporal_context(_dt(2026, 6, 5), "Europe/Amsterdam")
    assert "Current weekday: Friday" in ctx
    assert "Current date: 2026-06-05" in ctx


def test_context_zavtra_around_midnight():
    """'завтра' at 23:59 Wednesday → Thursday (current date + 1), not Friday."""
    ctx = build_llm_temporal_context(_dt(2026, 6, 3, 23, 59), "Europe/Amsterdam")
    assert "Current date: 2026-06-03" in ctx
    assert "Current weekday: Wednesday" in ctx


def test_context_poslezavtra():
    """'послезавтра' from Wednesday → Friday (current date +2)."""
    ctx = build_llm_temporal_context(_dt(2026, 6, 3), "Europe/Amsterdam")
    assert "Current date: 2026-06-03" in ctx


def test_context_sleduyushchiy_ponedelnik():
    """'в следующий понедельник' from Wednesday: next Monday is June 8."""
    ctx = build_llm_temporal_context(_dt(2026, 6, 3), "Europe/Amsterdam")
    assert "Current weekday: Wednesday" in ctx
    assert "Current date: 2026-06-03" in ctx


def test_context_recurring_kazhdyy_pyatnicu():
    """Recurring 'каждую пятницу' — temporal context is still injected."""
    ctx = build_llm_temporal_context(_dt(2026, 6, 3), "Europe/Amsterdam")
    assert "Current date: 2026-06-03" in ctx
    assert "Current weekday: Wednesday" in ctx


# ---------------------------------------------------------------------------
# Parser integration — temporal context appears in system message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parser_injects_current_date_in_system_prompt():
    """System message must contain all four temporal fields."""
    parser = _make_parser()
    resp = _mock_response(json.dumps(VALID_JSON_PAYLOAD))
    captured: dict = {}

    async def capture_post(url, **kwargs):
        captured.update(kwargs.get("json", {}))
        return resp

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=capture_post)
        mock_cls.return_value = mock_client

        await parser.parse("напомни завтра утром", timezone="Europe/Amsterdam")

    system_msg = captured["messages"][0]["content"]
    assert "Current datetime:" in system_msg
    assert "Current date:" in system_msg
    assert "Current weekday:" in system_msg
    assert "User timezone: Europe/Amsterdam" in system_msg


@pytest.mark.asyncio
async def test_parser_temporal_context_reflects_timezone():
    """Different timezone → different User timezone label in system message."""
    parser = _make_parser()
    resp = _mock_response(json.dumps(VALID_JSON_PAYLOAD))
    captured: dict = {}

    async def capture_post(url, **kwargs):
        captured.update(kwargs.get("json", {}))
        return resp

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=capture_post)
        mock_cls.return_value = mock_client

        await parser.parse("test", timezone="Asia/Tokyo")

    system_msg = captured["messages"][0]["content"]
    assert "User timezone: Asia/Tokyo" in system_msg


@pytest.mark.asyncio
async def test_parser_includes_relative_date_rules_in_prompt():
    """System prompt must contain relative date rules for the LLM."""
    parser = _make_parser()
    resp = _mock_response(json.dumps(VALID_JSON_PAYLOAD))
    captured: dict = {}

    async def capture_post(url, **kwargs):
        captured.update(kwargs.get("json", {}))
        return resp

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=capture_post)
        mock_cls.return_value = mock_client

        await parser.parse("в субботу напомни позвонить", timezone="Europe/Amsterdam")

    system_msg = captured["messages"][0]["content"]
    assert "Relative date rules" in system_msg
    assert "Current date" in system_msg
