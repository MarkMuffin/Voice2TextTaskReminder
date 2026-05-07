"""
Tests for Telegram callback logic using the container directly.
We don't test aiogram internals, but the service layer that callbacks invoke.
"""

from datetime import UTC, datetime, timedelta

from app.domain.enums import ReminderStatus, TaskStatus
from app.domain.schemas import TaskCreate
from app.utils.time_utils import in_minutes, to_utc_naive, tomorrow_morning


async def test_complete_task_via_service(container):
    task = await container.task_service.create_task(
        TaskCreate(user_id="cb_user", title="Callback test task")
    )
    remind_at = datetime.now(UTC) + timedelta(hours=1)
    reminder = await container.reminder_service.schedule_reminder(task.id, remind_at)

    # Simulate callback: complete
    updated = await container.task_service.complete_task(task.id)
    await container.reminder_service.cancel_task_reminders(task.id)

    assert updated.status == TaskStatus.DONE
    cancelled = await container.reminder_service.get_reminder(reminder.id)
    assert cancelled.status == ReminderStatus.CANCELLED


async def test_snooze_10min_via_service(container):
    task = await container.task_service.create_task(
        TaskCreate(user_id="cb_user", title="Snooze test task")
    )
    original_remind = datetime.now(UTC) + timedelta(hours=1)
    old_reminder = await container.reminder_service.schedule_reminder(task.id, original_remind)

    # Simulate "snooze 10 min" callback
    snooze_until = in_minutes(10)
    updated_task = await container.task_service.snooze_task(task.id, snooze_until)
    new_reminder = await container.reminder_service.reschedule(task.id, snooze_until)

    assert updated_task.remind_at is not None
    old_updated = await container.reminder_service.get_reminder(old_reminder.id)
    assert old_updated.status == ReminderStatus.CANCELLED
    assert new_reminder.status == ReminderStatus.PENDING


async def test_snooze_tomorrow_via_service(container):
    task = await container.task_service.create_task(
        TaskCreate(user_id="cb_user", title="Tomorrow snooze")
    )
    snooze_until = tomorrow_morning()
    updated_task = await container.task_service.snooze_task(task.id, snooze_until)
    new_reminder = await container.reminder_service.reschedule(task.id, snooze_until)

    assert updated_task.remind_at.date() > datetime.now(UTC).date()
    assert new_reminder.remind_at.hour == to_utc_naive(snooze_until).hour


async def test_cancel_task_via_service(container):
    task = await container.task_service.create_task(
        TaskCreate(user_id="cb_user", title="Cancel me")
    )
    await container.reminder_service.schedule_reminder(
        task.id, datetime.now(UTC) + timedelta(hours=1)
    )

    updated = await container.task_service.cancel_task(task.id)
    await container.reminder_service.cancel_task_reminders(task.id)

    assert updated.status == TaskStatus.CANCELLED
    pending = await container.reminder_service.get_pending()
    assert all(r.task_id != task.id for r in pending)


async def test_renderer_formats_callback_result(container):
    task = await container.task_service.create_task(
        TaskCreate(user_id="cb_user", title="Format me")
    )
    completed = await container.task_service.complete_task(task.id)
    text = container.renderer.task_completed(completed)
    assert "Format me" in text
    assert "✅" in text
