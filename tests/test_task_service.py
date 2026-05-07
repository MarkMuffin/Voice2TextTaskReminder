from datetime import datetime, timezone

import pytest
import pytz

from app.domain.enums import TaskStatus
from app.domain.schemas import TaskCreate
from app.services.task_service import TaskService
from app.storage.repositories import TaskRepository


@pytest.fixture
def task_service(session_factory):
    return TaskService(TaskRepository(session_factory))


@pytest.fixture
def sample_task_data():
    return TaskCreate(
        user_id="user_1",
        title="Купить молоко",
        raw_text="Напомни купить молоко завтра утром",
        remind_at=datetime(2025, 1, 10, 9, 0, tzinfo=timezone.utc),
        timezone="Europe/Amsterdam",
    )


async def test_create_task(task_service, sample_task_data):
    task = await task_service.create_task(sample_task_data)
    assert task.id is not None
    assert task.title == "Купить молоко"
    assert task.status == TaskStatus.ACTIVE
    assert task.user_id == "user_1"


async def test_complete_task(task_service, sample_task_data):
    task = await task_service.create_task(sample_task_data)
    updated = await task_service.complete_task(task.id)
    assert updated.status == TaskStatus.DONE
    assert updated.completed_at is not None


async def test_cancel_task(task_service, sample_task_data):
    task = await task_service.create_task(sample_task_data)
    updated = await task_service.cancel_task(task.id)
    assert updated.status == TaskStatus.CANCELLED


async def test_list_active(task_service):
    await task_service.create_task(TaskCreate(user_id="u1", title="Task 1"))
    await task_service.create_task(TaskCreate(user_id="u1", title="Task 2"))
    t3 = await task_service.create_task(TaskCreate(user_id="u1", title="Task 3"))
    await task_service.complete_task(t3.id)

    active = await task_service.list_active("u1")
    assert len(active) == 2
    assert all(t.status == TaskStatus.ACTIVE for t in active)


async def test_list_done(task_service):
    t = await task_service.create_task(TaskCreate(user_id="u2", title="Done task"))
    await task_service.complete_task(t.id)
    done = await task_service.list_done("u2")
    assert len(done) == 1
    assert done[0].status == TaskStatus.DONE


async def test_snooze_task(task_service, sample_task_data):
    task = await task_service.create_task(sample_task_data)
    new_time = datetime(2025, 2, 1, 18, 0, tzinfo=timezone.utc)
    updated = await task_service.snooze_task(task.id, new_time)
    assert updated.remind_at.replace(tzinfo=None) == new_time.replace(tzinfo=None)


async def test_find_by_reference(task_service):
    await task_service.create_task(TaskCreate(user_id="u3", title="Купить хлеб"))
    found = await task_service.find_by_reference("u3", "хлеб")
    assert found is not None
    assert "хлеб" in found.title.lower()


async def test_find_by_reference_not_found(task_service):
    result = await task_service.find_by_reference("u99", "несуществующее")
    assert result is None


async def test_complete_nonexistent_task(task_service):
    result = await task_service.complete_task(99999)
    assert result is None


async def test_tasks_isolated_by_user(task_service):
    await task_service.create_task(TaskCreate(user_id="alice", title="Alice task"))
    await task_service.create_task(TaskCreate(user_id="bob", title="Bob task"))

    alice_tasks = await task_service.list_active("alice")
    bob_tasks = await task_service.list_active("bob")
    assert len(alice_tasks) == 1
    assert len(bob_tasks) == 1
