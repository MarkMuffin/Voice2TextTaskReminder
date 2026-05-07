import pytest
from pydantic import ValidationError

from app.domain.enums import IntentType
from app.domain.schemas import ParsedIntent
from app.providers.llm.mock import MockIntentParser


def test_valid_create_reminder():
    intent = ParsedIntent(
        intent=IntentType.CREATE_REMINDER,
        title="Купить молоко",
        remind_at="2025-01-10T09:00:00+01:00",
        timezone="Europe/Amsterdam",
        confidence=0.95,
    )
    assert intent.intent == IntentType.CREATE_REMINDER
    assert intent.title == "Купить молоко"
    assert intent.confidence == 0.95


def test_valid_list_tasks():
    intent = ParsedIntent(intent=IntentType.LIST_TASKS, confidence=1.0)
    assert intent.intent == IntentType.LIST_TASKS
    assert intent.title is None


def test_valid_complete_task():
    intent = ParsedIntent(
        intent=IntentType.COMPLETE_TASK,
        task_reference="молоко",
        confidence=0.9,
    )
    assert intent.task_reference == "молоко"


def test_valid_snooze():
    intent = ParsedIntent(
        intent=IntentType.SNOOZE_TASK,
        task_reference="молоко",
        snooze_until="2025-01-11T09:00:00",
        confidence=0.85,
    )
    assert intent.snooze_until == "2025-01-11T09:00:00"


def test_confidence_bounds():
    with pytest.raises(ValidationError):
        ParsedIntent(intent=IntentType.UNKNOWN, confidence=1.5)
    with pytest.raises(ValidationError):
        ParsedIntent(intent=IntentType.UNKNOWN, confidence=-0.1)


def test_unknown_intent():
    intent = ParsedIntent(
        intent=IntentType.UNKNOWN,
        requires_confirmation=True,
        clarification_question="Уточни команду",
        confidence=0.0,
    )
    assert intent.requires_confirmation is True
    assert intent.clarification_question == "Уточни команду"


async def test_mock_parser_create_reminder():
    parser = MockIntentParser()
    intent = await parser.parse("Напомни купить молоко завтра утром")
    assert intent.intent == IntentType.CREATE_REMINDER
    assert intent.confidence > 0


async def test_mock_parser_list_tasks():
    parser = MockIntentParser()
    intent = await parser.parse("покажи список задач")
    assert intent.intent == IntentType.LIST_TASKS


async def test_mock_parser_complete():
    parser = MockIntentParser()
    intent = await parser.parse("сделал задачу")
    assert intent.intent == IntentType.COMPLETE_TASK


async def test_mock_parser_cancel():
    parser = MockIntentParser()
    intent = await parser.parse("отмени напоминание")
    assert intent.intent == IntentType.CANCEL_TASK


async def test_mock_parser_fixed_response():
    fixed = ParsedIntent(
        intent=IntentType.LIST_TASKS,
        confidence=1.0,
    )
    parser = MockIntentParser(fixed_response=fixed)
    result = await parser.parse("любой текст")
    assert result.intent == IntentType.LIST_TASKS
