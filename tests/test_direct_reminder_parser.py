from datetime import datetime

import pytest
import pytz

from app.domain.enums import IntentType
from app.providers.llm.base import BaseIntentParser
from app.services.direct_reminder_parser import DirectReminderParser


@pytest.fixture
def parser():
    tz = pytz.timezone("Europe/Tallinn")
    now = tz.localize(datetime(2026, 7, 28, 12, 0))
    return DirectReminderParser(now=lambda _: now)


def test_extracts_literal_title_after_command_and_datetime(parser):
    intent = parser.parse("Напомни завтра в 15:00 оплатить интернет", "Europe/Tallinn")

    assert intent is not None
    assert intent.intent == IntentType.CREATE_REMINDER
    assert intent.title == "оплатить интернет"
    assert intent.remind_at == "2026-07-29T15:00:00+03:00"


def test_extracts_literal_title_when_time_is_before_command(parser):
    intent = parser.parse("В 19:30 напомни написать Саше по проекту", "Europe/Tallinn")

    assert intent is not None
    assert intent.title == "написать Саше по проекту"
    assert intent.remind_at == "2026-07-28T19:30:00+03:00"


def test_uses_default_time_for_weekday(parser):
    intent = parser.parse("Напомни в пятницу забрать посылку", "Europe/Tallinn")

    assert intent is not None
    assert intent.title == "забрать посылку"
    assert intent.remind_at == "2026-07-31T09:00:00+03:00"


def test_uses_default_time_when_title_contains_a_number(parser):
    intent = parser.parse("Напомни завтра купить 2 литра молока", "Europe/Tallinn")

    assert intent is not None
    assert intent.title == "купить 2 литра молока"
    assert intent.remind_at == "2026-07-29T09:00:00+03:00"


def test_preserves_relative_duration_as_reminder_time(parser):
    intent = parser.parse("Напомни тест через 10 минут", "Europe/Tallinn")

    assert intent is not None
    assert intent.title == "тест"
    assert intent.remind_at == "2026-07-28T12:10:00+03:00"


def test_uses_correct_offset_after_dst_transition():
    tz = pytz.timezone("Europe/Amsterdam")
    now = tz.localize(datetime(2026, 10, 24, 10, 0))
    parser = DirectReminderParser(now=lambda _: now)

    intent = parser.parse("Напомни послезавтра в 10:00 позвонить врачу", "Europe/Amsterdam")

    assert intent is not None
    assert intent.remind_at == "2026-10-26T10:00:00+01:00"


def test_creates_unscheduled_task_when_time_is_missing(parser):
    intent = parser.parse("Напомни купить молоко", "Europe/Tallinn")

    assert intent is not None
    assert intent.title == "купить молоко"
    assert intent.remind_at is None


def test_does_not_hijack_recurring_commands(parser):
    assert parser.parse("Каждую пятницу напомни оплатить интернет", "Europe/Tallinn") is None


def test_parses_compound_relative_duration(parser):
    intent = parser.parse("Напомни через 2 часа 15 минут тест", "Europe/Tallinn")

    assert intent is not None
    assert intent.title == "тест"
    assert intent.remind_at == "2026-07-28T14:15:00+03:00"


def test_removes_time_of_day_inflection_from_title(parser):
    intent = parser.parse("Напомни завтра в 9 утра купить кофе", "Europe/Tallinn")

    assert intent is not None
    assert intent.title == "купить кофе"
    assert intent.remind_at == "2026-07-29T09:00:00+03:00"


@pytest.mark.parametrize(
    ("text", "expected_title", "expected_remind_at"),
    [
        ("Напомни в 10 вечера позвонить маме", "позвонить маме", "2026-07-28T22:00:00+03:00"),
        ("Напомни в 8 утра выпить таблетки", "выпить таблетки", "2026-07-29T08:00:00+03:00"),
        ("Напомни в 3 дня пообедать", "пообедать", "2026-07-28T15:00:00+03:00"),
        ("Напомни в 3 ночи проверить печь", "проверить печь", "2026-07-29T03:00:00+03:00"),
    ],
)
def test_respects_explicit_hour_with_time_of_day_suffix(
    parser, text, expected_title, expected_remind_at
):
    intent = parser.parse(text, "Europe/Tallinn")

    assert intent is not None
    assert intent.title == expected_title
    assert intent.remind_at == expected_remind_at


@pytest.mark.parametrize(
    ("text", "expected_title"),
    [
        ("Напомни завтра составить план дня", "составить план дня"),
        ("Напомни завтра обсудить итоги дня", "обсудить итоги дня"),
    ],
)
def test_preserves_day_word_in_task_title(parser, text, expected_title):
    intent = parser.parse(text, "Europe/Tallinn")

    assert intent is not None
    assert intent.title == expected_title
    assert intent.remind_at == "2026-07-29T09:00:00+03:00"


def test_removes_colloquial_command_suffix(parser):
    intent = parser.parse("Напомни-ка завтра тест", "Europe/Tallinn")

    assert intent is not None
    assert intent.title == "тест"
    assert intent.remind_at == "2026-07-29T09:00:00+03:00"


def test_weekend_means_next_saturday(parser):
    intent = parser.parse("Напомни в выходные купить подарок", "Europe/Tallinn")

    assert intent is not None
    assert intent.title == "купить подарок"
    assert intent.remind_at == "2026-08-01T09:00:00+03:00"


class _FailingParser(BaseIntentParser):
    async def parse(self, text: str, timezone: str = "Europe/Amsterdam"):
        raise AssertionError("LLM must not be called for a direct reminder")


@pytest.mark.asyncio
async def test_capture_service_skips_llm_for_direct_reminder(container):
    container.capture_service._llm = _FailingParser()

    intent = await container.capture_service.process_text(
        user_id="direct-parser-user",
        text="Напомни завтра в 15 оплатить интернет",
        timezone="Europe/Tallinn",
    )

    assert intent.title == "оплатить интернет"
    assert intent.remind_at is not None
