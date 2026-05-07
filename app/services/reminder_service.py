from datetime import datetime

from app.domain.models import Reminder
from app.storage.repositories import ReminderRepository
from app.utils.time_utils import to_utc_naive


class ReminderService:
    def __init__(self, repo: ReminderRepository) -> None:
        self._repo = repo

    async def schedule_reminder(self, task_id: int, remind_at: datetime) -> Reminder:
        reminder = Reminder(task_id=task_id, remind_at=to_utc_naive(remind_at))
        return await self._repo.create(reminder)

    async def get_pending(self, before: datetime | None = None) -> list[Reminder]:
        return await self._repo.list_pending(before=before)

    async def get_reminder(self, reminder_id: int) -> Reminder | None:
        return await self._repo.get(reminder_id)

    async def mark_sent(self, reminder_id: int) -> None:
        await self._repo.mark_sent(reminder_id)

    async def cancel_task_reminders(self, task_id: int) -> None:
        await self._repo.cancel_by_task(task_id)

    async def cancel_reminder(self, reminder_id: int) -> None:
        await self._repo.cancel(reminder_id)

    async def reschedule(self, task_id: int, new_time: datetime) -> Reminder:
        """Cancel existing pending reminders and create a new one."""
        await self._repo.cancel_by_task(task_id)
        return await self.schedule_reminder(task_id, new_time)
