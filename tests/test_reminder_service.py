from datetime import UTC, datetime, timedelta

import pytest

from app.domain.enums import ReminderStatus
from app.domain.schemas import TaskCreate
from app.services.reminder_service import ReminderService
from app.services.task_service import TaskService
from app.storage.repositories import ReminderRepository, TaskRepository


@pytest.fixture
def task_service(session_factory):
    return TaskService(TaskRepository(session_factory))


@pytest.fixture
def reminder_service(session_factory):
    return ReminderService(ReminderRepository(session_factory))


async def test_schedule_reminder(task_service, reminder_service):
    task = await task_service.create_task(TaskCreate(user_id="u1", title="Test"))
    remind_at = datetime(2025, 6, 1, 9, 0, tzinfo=UTC)
    reminder = await reminder_service.schedule_reminder(task.id, remind_at)

    assert reminder.id is not None
    assert reminder.task_id == task.id
    assert reminder.status == ReminderStatus.PENDING
    # SQLite strips tzinfo on round-trip; compare naive UTC values
    assert reminder.remind_at.replace(tzinfo=None) == remind_at.replace(tzinfo=None)


async def test_get_pending(task_service, reminder_service):
    task = await task_service.create_task(TaskCreate(user_id="u1", title="Test"))
    future = datetime.now(UTC) + timedelta(hours=1)
    past = datetime.now(UTC) - timedelta(hours=1)

    await reminder_service.schedule_reminder(task.id, future)
    await reminder_service.schedule_reminder(task.id, past)

    pending = await reminder_service.get_pending()
    assert len(pending) == 2


async def test_get_pending_before(task_service, reminder_service):
    task = await task_service.create_task(TaskCreate(user_id="u1", title="Test"))
    past = datetime.now(UTC) - timedelta(minutes=5)
    future = datetime.now(UTC) + timedelta(hours=1)

    await reminder_service.schedule_reminder(task.id, past)
    await reminder_service.schedule_reminder(task.id, future)

    now = datetime.now(UTC)
    due = await reminder_service.get_pending(before=now)
    assert len(due) == 1
    assert due[0].remind_at.replace(tzinfo=None) <= now.replace(tzinfo=None)


async def test_mark_sent(task_service, reminder_service):
    task = await task_service.create_task(TaskCreate(user_id="u1", title="Test"))
    reminder = await reminder_service.schedule_reminder(task.id, datetime(2025, 1, 1, tzinfo=UTC))
    await reminder_service.mark_sent(reminder.id)

    updated = await reminder_service.get_reminder(reminder.id)
    assert updated.status == ReminderStatus.SENT
    assert updated.sent_at is not None


async def test_cancel_task_reminders(task_service, reminder_service):
    task = await task_service.create_task(TaskCreate(user_id="u1", title="Test"))
    r1 = await reminder_service.schedule_reminder(task.id, datetime(2025, 1, 1, tzinfo=UTC))
    r2 = await reminder_service.schedule_reminder(task.id, datetime(2025, 1, 2, tzinfo=UTC))

    await reminder_service.cancel_task_reminders(task.id)

    updated_r1 = await reminder_service.get_reminder(r1.id)
    updated_r2 = await reminder_service.get_reminder(r2.id)
    assert updated_r1.status == ReminderStatus.CANCELLED
    assert updated_r2.status == ReminderStatus.CANCELLED


async def test_reschedule(task_service, reminder_service):
    task = await task_service.create_task(TaskCreate(user_id="u1", title="Test"))
    old_time = datetime(2025, 1, 1, tzinfo=UTC)
    new_time = datetime(2025, 1, 2, tzinfo=UTC)

    old = await reminder_service.schedule_reminder(task.id, old_time)
    new_reminder = await reminder_service.reschedule(task.id, new_time)

    old_updated = await reminder_service.get_reminder(old.id)
    assert old_updated.status == ReminderStatus.CANCELLED
    assert new_reminder.remind_at.replace(tzinfo=None) == new_time.replace(tzinfo=None)
    assert new_reminder.status == ReminderStatus.PENDING
