from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.domain.enums import RecurringTaskStatus, ReminderStatus, TaskStatus
from app.domain.models import CaptureLog, RecurringTask, Reminder, Task, UserSettings


class TaskRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def create(self, task: Task) -> Task:
        async with self._sf() as session:
            session.add(task)
            await session.commit()
            await session.refresh(task)
            return task

    async def get(self, task_id: int) -> Task | None:
        async with self._sf() as session:
            result = await session.execute(select(Task).where(Task.id == task_id))
            return result.scalar_one_or_none()

    async def get_with_reminders(self, task_id: int) -> Task | None:
        async with self._sf() as session:
            result = await session.execute(
                select(Task).options(selectinload(Task.reminders)).where(Task.id == task_id)
            )
            return result.scalar_one_or_none()

    async def list_by_user(self, user_id: str, status: TaskStatus | None = None) -> list[Task]:
        async with self._sf() as session:
            q = select(Task).where(Task.user_id == user_id)
            if status is not None:
                q = q.where(Task.status == status)
            q = q.order_by(Task.created_at.desc())
            result = await session.execute(q)
            return list(result.scalars().all())

    async def update_status(
        self, task_id: int, status: TaskStatus, completed_at: datetime | None = None
    ) -> Task | None:
        async with self._sf() as session:
            values: dict = {"status": status, "updated_at": datetime.utcnow()}
            if completed_at is not None:
                values["completed_at"] = completed_at
            await session.execute(update(Task).where(Task.id == task_id).values(**values))
            await session.commit()
            return await self._get_in_session(session, task_id)

    async def update_remind_at(self, task_id: int, remind_at: datetime) -> Task | None:
        async with self._sf() as session:
            await session.execute(
                update(Task)
                .where(Task.id == task_id)
                .values(remind_at=remind_at, updated_at=datetime.utcnow())
            )
            await session.commit()
            return await self._get_in_session(session, task_id)

    async def count_by_user(self, user_id: str, status: TaskStatus | None = None) -> int:
        async with self._sf() as session:
            q = select(func.count()).select_from(Task).where(Task.user_id == user_id)
            if status is not None:
                q = q.where(Task.status == status)
            result = await session.execute(q)
            return int(result.scalar() or 0)

    async def get_by_ids(self, task_ids: list[int]) -> list[Task]:
        if not task_ids:
            return []
        async with self._sf() as session:
            result = await session.execute(select(Task).where(Task.id.in_(task_ids)))
            return list(result.scalars().all())

    async def find_by_title_fuzzy(self, user_id: str, title_fragment: str) -> Task | None:
        """Find active task by partial title match."""
        async with self._sf() as session:
            result = await session.execute(
                select(Task)
                .where(
                    Task.user_id == user_id,
                    Task.status == TaskStatus.ACTIVE,
                    Task.title.ilike(f"%{title_fragment}%"),
                )
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def find_by_recurring_and_scheduled(
        self, recurring_task_id: int, scheduled_for: datetime
    ) -> Task | None:
        """Idempotency check: find existing task for recurring rule + scheduled time."""
        async with self._sf() as session:
            # SQLite stores datetimes as naive UTC; strip tzinfo for comparison
            scheduled_cmp = (
                scheduled_for.replace(tzinfo=None) if scheduled_for.tzinfo else scheduled_for
            )
            result = await session.execute(
                select(Task)
                .where(
                    Task.recurring_task_id == recurring_task_id,
                    Task.scheduled_for == scheduled_cmp,
                )
                .limit(1)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def _get_in_session(session: AsyncSession, task_id: int) -> Task | None:
        result = await session.execute(select(Task).where(Task.id == task_id))
        return result.scalar_one_or_none()


class ReminderRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def create(self, reminder: Reminder) -> Reminder:
        async with self._sf() as session:
            session.add(reminder)
            await session.commit()
            await session.refresh(reminder)
            return reminder

    async def get(self, reminder_id: int) -> Reminder | None:
        async with self._sf() as session:
            result = await session.execute(select(Reminder).where(Reminder.id == reminder_id))
            return result.scalar_one_or_none()

    async def list_pending(self, before: datetime | None = None) -> list[Reminder]:
        async with self._sf() as session:
            q = select(Reminder).where(Reminder.status == ReminderStatus.PENDING)
            if before is not None:
                # SQLite stores datetimes as naive UTC; strip tzinfo for comparison
                before_cmp = before.replace(tzinfo=None) if before.tzinfo else before
                q = q.where(Reminder.remind_at <= before_cmp)
            q = q.order_by(Reminder.remind_at.asc())
            result = await session.execute(q)
            return list(result.scalars().all())

    async def list_by_task(self, task_id: int) -> list[Reminder]:
        async with self._sf() as session:
            result = await session.execute(
                select(Reminder)
                .where(Reminder.task_id == task_id)
                .order_by(Reminder.remind_at.desc())
            )
            return list(result.scalars().all())

    async def mark_sent(self, reminder_id: int) -> None:
        async with self._sf() as session:
            await session.execute(
                update(Reminder)
                .where(Reminder.id == reminder_id)
                .values(status=ReminderStatus.SENT, sent_at=datetime.utcnow())
            )
            await session.commit()

    async def cancel_by_task(self, task_id: int) -> None:
        async with self._sf() as session:
            await session.execute(
                update(Reminder)
                .where(
                    Reminder.task_id == task_id,
                    Reminder.status == ReminderStatus.PENDING,
                )
                .values(status=ReminderStatus.CANCELLED)
            )
            await session.commit()

    async def cancel(self, reminder_id: int) -> None:
        async with self._sf() as session:
            await session.execute(
                update(Reminder)
                .where(Reminder.id == reminder_id)
                .values(status=ReminderStatus.CANCELLED)
            )
            await session.commit()


class UserSettingsRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def get(self, user_id: str) -> UserSettings | None:
        async with self._sf() as session:
            result = await session.execute(
                select(UserSettings).where(UserSettings.user_id == user_id)
            )
            return result.scalar_one_or_none()

    async def upsert(self, user_id: str, timezone: str) -> UserSettings:
        async with self._sf() as session:
            existing = await session.get(UserSettings, user_id)
            if existing:
                existing.timezone = timezone
                existing.updated_at = datetime.utcnow()
                await session.commit()
                await session.refresh(existing)
                return existing
            else:
                obj = UserSettings(user_id=user_id, timezone=timezone)
                session.add(obj)
                await session.commit()
                await session.refresh(obj)
                return obj


class CaptureLogRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def create(self, log: CaptureLog) -> CaptureLog:
        async with self._sf() as session:
            session.add(log)
            await session.commit()
            await session.refresh(log)
            return log

    async def list_by_user(self, user_id: str, limit: int = 50) -> list[CaptureLog]:
        async with self._sf() as session:
            result = await session.execute(
                select(CaptureLog)
                .where(CaptureLog.user_id == user_id)
                .order_by(CaptureLog.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())


class RecurringTaskRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def create(self, rt: RecurringTask) -> RecurringTask:
        async with self._sf() as session:
            session.add(rt)
            await session.commit()
            await session.refresh(rt)
            return rt

    async def get(self, rule_id: int) -> RecurringTask | None:
        async with self._sf() as session:
            result = await session.execute(select(RecurringTask).where(RecurringTask.id == rule_id))
            return result.scalar_one_or_none()

    async def list_by_user(self, user_id: str, status: str | None = None) -> list[RecurringTask]:
        async with self._sf() as session:
            q = select(RecurringTask).where(RecurringTask.user_id == user_id)
            if status is not None:
                q = q.where(RecurringTask.status == status)
            q = q.order_by(RecurringTask.created_at.desc())
            result = await session.execute(q)
            return list(result.scalars().all())

    async def list_due(self, before_utc: datetime) -> list[RecurringTask]:
        """Return ACTIVE rules whose next_run_at <= before_utc."""
        async with self._sf() as session:
            before_cmp = before_utc.replace(tzinfo=None) if before_utc.tzinfo else before_utc
            q = (
                select(RecurringTask)
                .where(
                    RecurringTask.status == RecurringTaskStatus.ACTIVE,
                    RecurringTask.next_run_at <= before_cmp,
                )
                .order_by(RecurringTask.next_run_at.asc())
            )
            result = await session.execute(q)
            return list(result.scalars().all())

    async def update_status(
        self,
        rule_id: int,
        status: str,
        cancelled_at: datetime | None = None,
    ) -> None:
        async with self._sf() as session:
            values: dict = {"status": status, "updated_at": datetime.utcnow()}
            if cancelled_at is not None:
                values["cancelled_at"] = cancelled_at
            await session.execute(
                update(RecurringTask).where(RecurringTask.id == rule_id).values(**values)
            )
            await session.commit()

    async def update_after_run(
        self, rule_id: int, last_run_at: datetime, next_run_at: datetime
    ) -> None:
        async with self._sf() as session:
            last_cmp = last_run_at.replace(tzinfo=None) if last_run_at.tzinfo else last_run_at
            next_cmp = next_run_at.replace(tzinfo=None) if next_run_at.tzinfo else next_run_at
            await session.execute(
                update(RecurringTask)
                .where(RecurringTask.id == rule_id)
                .values(
                    last_run_at=last_cmp,
                    next_run_at=next_cmp,
                    updated_at=datetime.utcnow(),
                )
            )
            await session.commit()
