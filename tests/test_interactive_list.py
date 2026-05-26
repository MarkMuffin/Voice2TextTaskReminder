"""Tests for interactive /list: renderer and service."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from app.adapters.telegram.callbacks import TaskListCallback
from app.domain.enums import CompleteTaskResult, TaskStatus
from app.domain.schemas import TaskCreate
from app.services.renderer import TASK_LIST_MAX, Renderer
from app.services.task_service import TaskService
from app.storage.repositories import TaskRepository

# ─── FakeTask ─────────────────────────────────────────────────────────────────


@dataclass
class FakeTask:
    id: int = 1
    user_id: str = "u1"
    title: str = "Тестовая задача"
    status: Any = TaskStatus.ACTIVE
    timezone: str = "Europe/Amsterdam"
    source: str = "telegram"
    raw_text: str | None = None
    remind_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def make_task(**kwargs) -> FakeTask:
    return FakeTask(**kwargs)


# ─── Renderer tests ───────────────────────────────────────────────────────────


@pytest.fixture
def renderer():
    return Renderer()


def test_render_empty_list(renderer):
    text, kb = renderer.render_inline_task_list([])
    assert "Активных задач нет" in text
    assert kb.inline_keyboard == []


def test_render_task_with_remind_at(renderer):
    task = make_task(remind_at=datetime(2030, 6, 1, 9, 0, tzinfo=UTC))
    text, kb = renderer.render_inline_task_list([task])
    assert "☐" in text
    assert "⏰" in text


def test_render_task_without_remind_at(renderer):
    task = make_task(remind_at=None)
    text, kb = renderer.render_inline_task_list([task])
    assert "без напоминания" in text


def test_render_compact_buttons_one_row(renderer):
    tasks = [make_task(id=i, title=f"Task {i}") for i in range(1, 6)]
    text, kb = renderer.render_inline_task_list(tasks)
    rows = kb.inline_keyboard
    # 1 row of 5 done buttons + 1 refresh row
    assert len(rows) == 2
    assert len(rows[0]) == 5
    assert rows[1][0].text == "🔄 Обновить"


def test_render_compact_buttons_two_rows(renderer):
    tasks = [make_task(id=i, title=f"Task {i}") for i in range(1, 9)]
    text, kb = renderer.render_inline_task_list(tasks)
    rows = kb.inline_keyboard
    # 8 done buttons → 5 + 3, plus refresh row
    assert len(rows) == 3
    assert len(rows[0]) == 5
    assert len(rows[1]) == 3
    assert rows[2][0].text == "🔄 Обновить"


def test_callback_data_length():
    """Worst-case packed callback must be ≤ 64 bytes."""
    cb = TaskListCallback(action="done", task_id=9223372036854775807, task_num=20)
    packed = cb.pack()
    assert len(packed.encode()) <= 64


def test_render_soft_limit(renderer):
    tasks = [make_task(id=i, title=f"Task {i}") for i in range(1, 22)]  # 21 tasks
    text, kb = renderer.render_inline_task_list(tasks)
    assert "⚠️" in text
    assert f"из {21}" in text
    done_buttons = [btn for row in kb.inline_keyboard for btn in row if btn.text.startswith("✅")]
    assert len(done_buttons) == TASK_LIST_MAX


def test_render_uses_local_timezone(renderer):
    # 12:00 UTC → 21:00 Asia/Tokyo (UTC+9)
    remind_at = datetime(2030, 6, 1, 12, 0, tzinfo=UTC)
    task = make_task(remind_at=remind_at, timezone="Asia/Tokyo")
    text, kb = renderer.render_inline_task_list([task])
    assert "21:00" in text


def test_render_completed_strikethrough(renderer):
    active = make_task(id=2, title="Активная задача")
    done = make_task(id=1, title="Выполненная задача", status=TaskStatus.DONE)
    text, kb = renderer.render_inline_task_list([active], completed_in_session=[done])
    assert "<s>☑ Выполненная задача</s>" in text
    assert "☐ Активная задача" in text
    done_buttons = [btn for row in kb.inline_keyboard for btn in row if btn.text.startswith("✅")]
    assert len(done_buttons) == 1  # только активная


def test_render_all_completed(renderer):
    done = make_task(id=1, title="Последняя задача", status=TaskStatus.DONE)
    text, kb = renderer.render_inline_task_list([], completed_in_session=[done])
    assert "Все задачи выполнены" in text
    assert "<s>☑ Последняя задача</s>" in text
    done_buttons = [btn for row in kb.inline_keyboard for btn in row if btn.text.startswith("✅")]
    assert len(done_buttons) == 0


# ─── Session-aware renderer tests ────────────────────────────────────────────


def test_render_with_session_interleaves_completed(renderer):
    task1 = make_task(id=1, title="Задача 1")
    task2_done = make_task(id=2, title="Задача 2", status=TaskStatus.DONE)
    task3 = make_task(id=3, title="Задача 3")

    text, kb = renderer.render_inline_task_list(
        tasks=[task1, task3],
        completed_in_session=[task2_done],
        visible_task_ids=[1, 2, 3],
    )

    pos1 = text.find("Задача 1")
    pos2 = text.find("Задача 2")
    pos3 = text.find("Задача 3")
    assert pos1 < pos2 < pos3
    assert "<s>☑ Задача 2</s>" in text


def test_render_with_session_multiple_completed(renderer):
    task1 = make_task(id=1, title="Активная")
    task2_done = make_task(id=2, title="Выполнена 2", status=TaskStatus.DONE)
    task3_done = make_task(id=3, title="Выполнена 3", status=TaskStatus.DONE)

    text, kb = renderer.render_inline_task_list(
        tasks=[task1],
        completed_in_session=[task2_done, task3_done],
        visible_task_ids=[1, 2, 3],
    )

    assert "<s>☑ Выполнена 2</s>" in text
    assert "<s>☑ Выполнена 3</s>" in text
    done_buttons = [btn for row in kb.inline_keyboard for btn in row if btn.text.startswith("✅")]
    assert len(done_buttons) == 1


def test_render_with_session_keyboard_excludes_completed(renderer):
    task1 = make_task(id=1, title="Активная 1")
    task2_done = make_task(id=2, title="Выполнена", status=TaskStatus.DONE)
    task3 = make_task(id=3, title="Активная 3")

    text, kb = renderer.render_inline_task_list(
        tasks=[task1, task3],
        completed_in_session=[task2_done],
        visible_task_ids=[1, 2, 3],
    )

    done_buttons = [btn for row in kb.inline_keyboard for btn in row if btn.text.startswith("✅")]
    assert len(done_buttons) == 2
    button_texts = {btn.text for btn in done_buttons}
    assert "✅ 1" in button_texts
    assert "✅ 3" in button_texts


def test_render_with_session_all_completed_shows_celebration(renderer):
    task1_done = make_task(id=1, title="Задача 1", status=TaskStatus.DONE)
    task2_done = make_task(id=2, title="Задача 2", status=TaskStatus.DONE)

    text, kb = renderer.render_inline_task_list(
        tasks=[],
        completed_in_session=[task1_done, task2_done],
        visible_task_ids=[1, 2],
    )

    assert "Все задачи выполнены" in text
    done_buttons = [btn for row in kb.inline_keyboard for btn in row if btn.text.startswith("✅")]
    assert len(done_buttons) == 0


def test_render_with_session_preserves_original_ordering(renderer):
    task1 = make_task(id=1, title="Первая")
    task2_done = make_task(id=2, title="Вторая выполнена", status=TaskStatus.DONE)
    task3 = make_task(id=3, title="Третья")
    task4_done = make_task(id=4, title="Четвёртая выполнена", status=TaskStatus.DONE)

    text, kb = renderer.render_inline_task_list(
        tasks=[task1, task3],
        completed_in_session=[task2_done, task4_done],
        visible_task_ids=[1, 2, 3, 4],
    )

    positions = [
        text.find("Первая"),
        text.find("Вторая"),
        text.find("Третья"),
        text.find("Четвёртая"),
    ]
    assert positions == sorted(positions)


def test_render_html_escaping_in_task_title(renderer):
    """task.title with HTML special chars must be escaped."""
    task = make_task(id=1, title="A <b>bold</b> & 'quoted' task")
    text, _ = renderer.render_inline_task_list([task])
    assert "<b>bold</b>" not in text
    assert "A &lt;b&gt;bold&lt;/b&gt; &amp; &#x27;quoted&#x27; task" in text


def test_render_html_escaping_completed_in_session(renderer):
    """Completed-in-session task title must also be escaped."""
    done = make_task(id=1, title="<script>alert(1)</script>", status=TaskStatus.DONE)
    text, _ = renderer.render_inline_task_list([], completed_in_session=[done])
    assert "<script>" not in text
    assert "&lt;script&gt;" in text


def test_render_with_session_no_session_graceful_fallback(renderer):
    """Without visible_task_ids, falls back to standard rendering."""
    task = make_task(id=1, title="Задача")
    done = make_task(id=2, title="Выполнена", status=TaskStatus.DONE)

    text, kb = renderer.render_inline_task_list(
        tasks=[task],
        completed_in_session=[done],
        visible_task_ids=None,
    )

    assert "☐ Задача" in text
    assert "<s>☑ Выполнена</s>" in text


# ─── Service tests (async, real DB) ───────────────────────────────────────────


@pytest.fixture
def task_service(session_factory):
    return TaskService(TaskRepository(session_factory))


async def test_complete_task_safe_success(task_service):
    task = await task_service.create_task(TaskCreate(user_id="u1", title="Test"))
    result, updated = await task_service.complete_task_safe("u1", task.id)
    assert result == CompleteTaskResult.COMPLETED
    assert updated is not None
    assert updated.status == TaskStatus.DONE


async def test_complete_task_safe_forbidden(task_service):
    task = await task_service.create_task(TaskCreate(user_id="u1", title="Test"))
    result, t = await task_service.complete_task_safe("other_user", task.id)
    assert result == CompleteTaskResult.FORBIDDEN
    assert t is None


async def test_complete_task_safe_not_found(task_service):
    result, t = await task_service.complete_task_safe("u1", 999999)
    assert result == CompleteTaskResult.NOT_FOUND
    assert t is None


async def test_complete_task_safe_already_done(task_service):
    task = await task_service.create_task(TaskCreate(user_id="u1", title="Test"))
    await task_service.complete_task(task.id)
    result, t = await task_service.complete_task_safe("u1", task.id)
    assert result == CompleteTaskResult.ALREADY_INACTIVE
    assert t is not None


async def test_complete_task_safe_already_cancelled(task_service):
    task = await task_service.create_task(TaskCreate(user_id="u1", title="Test"))
    await task_service.cancel_task(task.id)
    result, t = await task_service.complete_task_safe("u1", task.id)
    assert result == CompleteTaskResult.ALREADY_INACTIVE
    assert t is not None


async def test_count_active_tasks(task_service):
    await task_service.create_task(TaskCreate(user_id="counter_user", title="T1"))
    await task_service.create_task(TaskCreate(user_id="counter_user", title="T2"))
    t3 = await task_service.create_task(TaskCreate(user_id="counter_user", title="T3"))
    await task_service.complete_task(t3.id)

    count = await task_service.count_active_tasks("counter_user")
    assert count == 2
