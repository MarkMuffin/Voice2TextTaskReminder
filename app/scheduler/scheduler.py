import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

if TYPE_CHECKING:
    from aiogram import Bot

    from app.container import Container

logger = logging.getLogger(__name__)

_UTC = pytz.utc


def _as_utc(dt: datetime) -> datetime:
    """Ensure datetime is UTC-aware. SQLite returns naive UTC — re-attach tzinfo."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_UTC)
    return dt.astimezone(_UTC)


class ReminderScheduler:
    def __init__(self, container: "Container", bot: "Bot") -> None:
        self._container = container
        self._bot = bot
        # Force UTC so naive datetimes from SQLite are interpreted correctly
        self._scheduler = AsyncIOScheduler(timezone=_UTC)

    def start(self) -> None:
        self._scheduler.start()
        logger.info("Reminder scheduler started")

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)

    def schedule_reminder(
        self,
        reminder_id: int,
        task_id: int,
        remind_at: datetime,
        user_id: str,
    ) -> None:
        job_id = f"reminder_{task_id}"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

        run_date = _as_utc(remind_at)
        self._scheduler.add_job(
            self._fire_reminder,
            trigger=DateTrigger(run_date=run_date, timezone=_UTC),
            args=[reminder_id, task_id, user_id],
            id=job_id,
            replace_existing=True,
            misfire_grace_time=300,
        )
        logger.info("Scheduled reminder %s for task %s at %s UTC", reminder_id, task_id, run_date)

    def reschedule_reminder(self, task_id: int, remind_at: datetime, user_id: str) -> None:
        job_id = f"reminder_{task_id}"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

        run_date = _as_utc(remind_at)
        self._scheduler.add_job(
            self._fire_reminder_by_task,
            trigger=DateTrigger(run_date=run_date, timezone=_UTC),
            args=[task_id, user_id],
            id=job_id,
            replace_existing=True,
            misfire_grace_time=300,
        )

    def cancel_reminder(self, task_id: int) -> None:
        job_id = f"reminder_{task_id}"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
            logger.debug("Cancelled scheduled reminder for task %s", task_id)

    async def load_pending(self, user_id_map: dict[int, str]) -> None:
        """On startup, re-schedule all pending reminders."""
        now = datetime.now(UTC)
        pending = await self._container.reminder_service.get_pending()
        for reminder in pending:
            uid = user_id_map.get(reminder.task_id)
            if not uid:
                continue
            remind_at_utc = _as_utc(reminder.remind_at)
            if remind_at_utc <= now:
                logger.info("Firing missed reminder %s immediately", reminder.id)
                await self._fire_reminder(reminder.id, reminder.task_id, uid)
            else:
                self.schedule_reminder(reminder.id, reminder.task_id, remind_at_utc, uid)

    async def _fire_reminder(self, reminder_id: int, task_id: int, user_id: str) -> None:
        task = await self._container.task_service.get_task(task_id)
        if not task:
            return

        from app.domain.enums import TaskStatus

        if task.status != TaskStatus.ACTIVE:
            return

        text, kb = self._container.renderer.reminder_message(task)
        try:
            await self._bot.send_message(
                chat_id=user_id, text=text, reply_markup=kb, parse_mode="HTML"
            )
            await self._container.reminder_service.mark_sent(reminder_id)
            logger.info("Reminder %s sent to %s", reminder_id, user_id)
        except Exception as exc:
            logger.error("Failed to send reminder %s: %s", reminder_id, exc)

    async def _fire_reminder_by_task(self, task_id: int, user_id: str) -> None:
        """Find the latest pending reminder for task and fire it."""
        reminders = await self._container.reminder_service.get_pending()
        for r in reminders:
            if r.task_id == task_id:
                await self._fire_reminder(r.id, task_id, user_id)
                return
