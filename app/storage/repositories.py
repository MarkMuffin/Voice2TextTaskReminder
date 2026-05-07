from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.domain.enums import ReminderStatus, TaskStatus
from app.domain.models import CaptureLog, Reminder, Task


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
            result = await session.execute(
                select(Task).where(Task.id == task_id)
            )
            return result.scalar_one_or_none()

    async def get_with_reminders(self, task_id: int) -> Task | None:
        async with self._sf() as session:
            result = await session.execute(
                select(Task)
                .options(selectinload(Task.reminders))
                .where(Task.id == task_id)
            )
            return result.scalar_one_or_none()

    async def list_by_user(
        self, user_id: str, status: TaskStatus | None = None
    ) -> list[Task]:
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
            await session.execute(
                update(Task).where(Task.id == task_id).values(**values)
            )
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
            result = await session.execute(
                select(Reminder).where(Reminder.id == reminder_id)
            )
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
