from datetime import datetime

import pytest
import pytz

from app.domain.enums import IntentType
from app.domain.schemas import ParsedIntent
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


@pytest.mark.parametrize(
    ("text", "expected_title", "expected_remind_at"),
    [
        (
            "Напомни 28 августа сходить в казино",
            "сходить в казино",
            "2026-08-28T09:00:00+03:00",
        ),
        (
            "Напомни 28.08 в 19:30 сходить в казино",
            "сходить в казино",
            "2026-08-28T19:30:00+03:00",
        ),
        ("Напомни 12.08 сходить в казино", "сходить в казино", "2026-08-12T09:00:00+03:00"),
        ("Напомни мне 12.08 купить молоко", "купить молоко", "2026-08-12T09:00:00+03:00"),
        (
            "Напомни, пожалуйста, 12.08 купить молоко",
            "купить молоко",
            "2026-08-12T09:00:00+03:00",
        ),
        (
            "Напомни 12.08.2027 сходить в казино",
            "сходить в казино",
            "2027-08-12T09:00:00+03:00",
        ),
        (
            "Напомни 28 августа 2027 года сходить в казино",
            "сходить в казино",
            "2027-08-28T09:00:00+03:00",
        ),
    ],
)
def test_parses_explicit_calendar_dates(parser, text, expected_title, expected_remind_at):
    intent = parser.parse(text, "Europe/Tallinn")

    assert intent is not None
    assert intent.title == expected_title
    assert intent.remind_at == expected_remind_at


def test_yearless_explicit_date_uses_next_year_when_this_year_has_passed():
    tz = pytz.timezone("Europe/Tallinn")
    parser = DirectReminderParser(now=lambda _: tz.localize(datetime(2026, 8, 29, 12, 0)))

    intent = parser.parse("Напомни 28.08 сходить в казино", "Europe/Tallinn")

    assert intent is not None
    assert intent.remind_at == "2027-08-28T09:00:00+03:00"


# Numeric-date contract: DD.MM[.YYYY] is a date only directly after "напомни".
# The exact same text elsewhere is part of the task title, never a reminder time.
@pytest.mark.parametrize(
    ("text", "expected_title"),
    [
        ("Напомни сходить в казино 12.08", "сходить в казино 12.08"),
        ("Напомни обновить до версии 12.08", "обновить до версии 12.08"),
        ("Напомни купить 1/2 стакана муки", "купить 1/2 стакана муки"),
        ("Напомни купить 3-4 упаковки молока", "купить 3-4 упаковки молока"),
        ("Напомни обновить python 3.11", "обновить python 3.11"),
        ("Напомни оплатить счет за 2.5 часа работы", "оплатить счет за 2.5 часа работы"),
    ],
)
def test_keeps_non_command_slot_numbers_in_task_title(parser, text, expected_title):
    intent = parser.parse(text, "Europe/Tallinn")

    assert intent is not None
    assert intent.title == expected_title
    assert intent.remind_at is None


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


@pytest.mark.parametrize(
    ("text", "expected_title", "expected_remind_at"),
    [
        ("Напомни через 3 дня оплатить счёт", "оплатить счёт", "2026-07-31T12:00:00+03:00"),
        (
            "Напомни через два месяца продлить подписку",
            "продлить подписку",
            "2026-09-28T12:00:00+03:00",
        ),
        (
            "Напомни через двадцать один день забрать заказ",
            "забрать заказ",
            "2026-08-18T12:00:00+03:00",
        ),
        ("Напомни через год проверить договор", "проверить договор", "2027-07-28T12:00:00+03:00"),
        (
            "Напомни через три года обновить документы",
            "обновить документы",
            "2029-07-28T12:00:00+03:00",
        ),
    ],
)
def test_parses_calendar_relative_durations(parser, text, expected_title, expected_remind_at):
    intent = parser.parse(text, "Europe/Tallinn")

    assert intent is not None
    assert intent.title == expected_title
    assert intent.remind_at == expected_remind_at


def test_calendar_duration_clamps_to_last_day_of_month():
    tz = pytz.timezone("Europe/Tallinn")
    now = tz.localize(datetime(2026, 1, 31, 12, 0))
    parser = DirectReminderParser(now=lambda _: now)

    intent = parser.parse("Напомни через месяц оплатить аренду", "Europe/Tallinn")

    assert intent is not None
    assert intent.remind_at == "2026-02-28T12:00:00+02:00"


def test_calendar_duration_preserves_target_date_with_explicit_time(parser):
    intent = parser.parse("Напомни через 2 дня в 10 вечера позвонить маме", "Europe/Tallinn")

    assert intent is not None
    assert intent.title == "позвонить маме"
    assert intent.remind_at == "2026-07-30T22:00:00+03:00"


@pytest.mark.parametrize(
    ("text", "expected_remind_at"),
    [
        ("Напомни сегодня в 9 утра позвонить маме", "2026-07-29T09:00:00+03:00"),
        ("Напомни позвонить маме сегодня", "2026-07-29T09:00:00+03:00"),
    ],
)
def test_today_in_the_past_rolls_over_to_tomorrow(text, expected_remind_at):
    tz = pytz.timezone("Europe/Tallinn")
    now = tz.localize(datetime(2026, 7, 28, 18, 0))
    parser = DirectReminderParser(now=lambda _: now)

    intent = parser.parse(text, "Europe/Tallinn")

    assert intent is not None
    assert intent.remind_at == expected_remind_at


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


class _TrackingParser(BaseIntentParser):
    def __init__(self, response: ParsedIntent) -> None:
        self.called = False
        self.response = response

    async def parse(self, text: str, timezone: str = "Europe/Amsterdam") -> ParsedIntent:
        self.called = True
        return self.response


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "expected_intent", "should_call_llm"),
    [
        # One-off reminders with one deterministic schedule stay local.
        ("Напомни завтра в 15 оплатить интернет", IntentType.CREATE_REMINDER, False),
        ("Напомни 28 августа сходить в казино", IntentType.CREATE_REMINDER, False),
        ("Напомни 12.08 сходить в казино", IntentType.CREATE_REMINDER, False),
        ("Напомни мне 12.08 купить молоко", IntentType.CREATE_REMINDER, False),
        ("Напомни сходить в казино 12.08", IntentType.CREATE_REMINDER, False),
        ("Напомни купить молоко", IntentType.CREATE_REMINDER, False),
        # Ambiguous, recurring, and task-management commands go to the LLM.
        ("Напомни через несколько дней купить подарок", IntentType.UNKNOWN, True),
        ("Напомни купить 1/2 стакана муки", IntentType.CREATE_REMINDER, False),
        ("Напомни купить 3-4 упаковки молока", IntentType.CREATE_REMINDER, False),
        ("Напомни обновить python 3.11", IntentType.CREATE_REMINDER, False),
        ("Напомни оплатить счет за 2.5 часа работы", IntentType.CREATE_REMINDER, False),
        ("Каждую пятницу напомни оплатить интернет", IntentType.CREATE_RECURRING_TASK, True),
        ("Покажи мои задачи", IntentType.LIST_TASKS, True),
        ("Отмени напоминание про казино", IntentType.CANCEL_TASK, True),
        ("Напомни завтра", IntentType.UNKNOWN, True),
    ],
)
@pytest.mark.asyncio
async def test_capture_service_intent_routing_contract(
    container, text, expected_intent, should_call_llm
):
    llm = _TrackingParser(ParsedIntent(intent=expected_intent, confidence=1.0))
    container.capture_service._llm = llm

    intent = await container.capture_service.process_text(
        user_id="direct-parser-user",
        text=text,
        timezone="Europe/Tallinn",
    )

    assert intent.intent == expected_intent
    assert llm.called is should_call_llm
