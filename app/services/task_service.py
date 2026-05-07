from datetime import datetime

from app.domain.enums import TaskStatus
from app.domain.models import Task
from app.domain.schemas import TaskCreate
from app.storage.repositories import TaskRepository
from app.utils.time_utils import to_utc_naive


class TaskService:
    def __init__(self, repo: TaskRepository) -> None:
        self._repo = repo

    async def create_task(self, data: TaskCreate) -> Task:
        task = Task(
            user_id=data.user_id,
            title=data.title,
            raw_text=data.raw_text,
            source=data.source,
            status=TaskStatus.ACTIVE,
            remind_at=to_utc_naive(data.remind_at) if data.remind_at else None,
            timezone=data.timezone,
        )
        return await self._repo.create(task)

    async def get_task(self, task_id: int) -> Task | None:
        return await self._repo.get(task_id)

    async def list_active(self, user_id: str) -> list[Task]:
        return await self._repo.list_by_user(user_id, status=TaskStatus.ACTIVE)

    async def list_done(self, user_id: str) -> list[Task]:
        return await self._repo.list_by_user(user_id, status=TaskStatus.DONE)

    async def list_all(self, user_id: str) -> list[Task]:
        return await self._repo.list_by_user(user_id)

    async def complete_task(self, task_id: int) -> Task | None:
        return await self._repo.update_status(
            task_id, TaskStatus.DONE, completed_at=datetime.utcnow()
        )

    async def cancel_task(self, task_id: int) -> Task | None:
        return await self._repo.update_status(task_id, TaskStatus.CANCELLED)

    async def snooze_task(self, task_id: int, snooze_until: datetime) -> Task | None:
        return await self._repo.update_remind_at(task_id, to_utc_naive(snooze_until))

    async def find_by_reference(self, user_id: str, reference: str) -> Task | None:
        """Find active task by fuzzy title match."""
        return await self._repo.find_by_title_fuzzy(user_id, reference)
