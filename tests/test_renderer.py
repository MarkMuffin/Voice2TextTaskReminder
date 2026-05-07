from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest

from app.domain.enums import TaskStatus
from app.services.renderer import Renderer


@pytest.fixture
def renderer():
    return Renderer()


@dataclass
class FakeTask:
    """Minimal task-like object for renderer tests — no SQLAlchemy needed."""
    id: int = 1
    user_id: str = "u1"
    title: str = "Купить молоко"
    status: Any = TaskStatus.ACTIVE
    timezone: str = "Europe/Amsterdam"
    source: str = "telegram"
    raw_text: str | None = None
    remind_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def make_task(**kwargs) -> FakeTask:
    return FakeTask(**kwargs)


def test_task_created_no_reminder(renderer):
    task = make_task()
    text, kb = renderer.task_created(task)
    assert "Купить молоко" in text
    assert "✅" in text
    assert kb is not None


def test_task_created_with_reminder(renderer):
    task = make_task(remind_at=datetime(2025, 12, 25, 9, 0, tzinfo=timezone.utc))
    text, kb = renderer.task_created(task)
    assert "Напомню" in text
    assert kb is not None


def test_task_completed(renderer):
    task = make_task()
    text = renderer.task_completed(task)
    assert "✅" in text
    assert "Купить молоко" in text


def test_task_cancelled(renderer):
    task = make_task()
    text = renderer.task_cancelled(task)
    assert "❌" in text
    assert "Купить молоко" in text


def test_task_snoozed(renderer):
    task = make_task(remind_at=datetime(2025, 12, 31, 18, 0, tzinfo=timezone.utc))
    text = renderer.task_snoozed(task)
    assert "🔁" in text


def test_task_list_empty(renderer):
    text = renderer.task_list([])
    assert "Нет задач" in text


def test_task_list_with_tasks(renderer):
    tasks = [make_task(id=i, title=f"Task {i}") for i in range(1, 4)]
    text = renderer.task_list(tasks)
    assert "Task 1" in text
    assert "Task 2" in text
    assert "Task 3" in text


def test_reminder_message(renderer):
    task = make_task(remind_at=datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc))
    text, kb = renderer.reminder_message(task)
    assert "⏰" in text
    assert "Купить молоко" in text
    assert kb is not None
    # Check buttons
    buttons = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("Выполнено" in b for b in buttons)
    assert any("10 мин" in b for b in buttons)
    assert any("Завтра" in b for b in buttons)
    assert any("Отменить" in b for b in buttons)


def test_clarification(renderer):
    text = renderer.clarification("О чём напомнить?")
    assert "О чём напомнить?" in text
    assert "🤔" in text


def test_error(renderer):
    text = renderer.error()
    assert "⚠️" in text
