from datetime import UTC, datetime

import pytest

from app.domain.enums import InputSource, InputType, ReminderStatus, TaskStatus
from app.domain.models import CaptureLog, Reminder, Task
from app.storage.repositories import CaptureLogRepository, ReminderRepository, TaskRepository


@pytest.fixture
def task_repo(session_factory):
    return TaskRepository(session_factory)


@pytest.fixture
def reminder_repo(session_factory):
    return ReminderRepository(session_factory)


@pytest.fixture
def log_repo(session_factory):
    return CaptureLogRepository(session_factory)


async def test_task_create_and_get(task_repo):
    task = Task(
        user_id="u1", title="Test task", status=TaskStatus.ACTIVE, timezone="UTC", source="telegram"
    )
    created = await task_repo.create(task)
    assert created.id is not None

    fetched = await task_repo.get(created.id)
    assert fetched.title == "Test task"
    assert fetched.status == TaskStatus.ACTIVE


async def test_task_list_by_user(task_repo):
    for i in range(3):
        await task_repo.create(
            Task(
                user_id="alice",
                title=f"Task {i}",
                status=TaskStatus.ACTIVE,
                timezone="UTC",
                source="telegram",
            )
        )
    await task_repo.create(
        Task(
            user_id="bob",
            title="Bob task",
            status=TaskStatus.ACTIVE,
            timezone="UTC",
            source="telegram",
        )
    )

    alice_tasks = await task_repo.list_by_user("alice")
    assert len(alice_tasks) == 3
    bob_tasks = await task_repo.list_by_user("bob")
    assert len(bob_tasks) == 1


async def test_task_list_by_user_filtered(task_repo):
    t = await task_repo.create(
        Task(
            user_id="u2",
            title="Active",
            status=TaskStatus.ACTIVE,
            timezone="UTC",
            source="telegram",
        )
    )
    await task_repo.update_status(t.id, TaskStatus.DONE, completed_at=datetime.utcnow())
    await task_repo.create(
        Task(
            user_id="u2",
            title="Active2",
            status=TaskStatus.ACTIVE,
            timezone="UTC",
            source="telegram",
        )
    )

    active = await task_repo.list_by_user("u2", status=TaskStatus.ACTIVE)
    assert len(active) == 1
    done = await task_repo.list_by_user("u2", status=TaskStatus.DONE)
    assert len(done) == 1


async def test_task_update_status(task_repo):
    task = await task_repo.create(
        Task(user_id="u3", title="T", status=TaskStatus.ACTIVE, timezone="UTC", source="telegram")
    )
    updated = await task_repo.update_status(
        task.id, TaskStatus.DONE, completed_at=datetime.utcnow()
    )
    assert updated.status == TaskStatus.DONE
    assert updated.completed_at is not None


async def test_task_fuzzy_search(task_repo):
    await task_repo.create(
        Task(
            user_id="u4",
            title="Купить молоко",
            status=TaskStatus.ACTIVE,
            timezone="UTC",
            source="telegram",
        )
    )
    found = await task_repo.find_by_title_fuzzy("u4", "молоко")
    assert found is not None
    assert "молоко" in found.title.lower()


async def test_reminder_crud(task_repo, reminder_repo):
    task = await task_repo.create(
        Task(user_id="u5", title="T", status=TaskStatus.ACTIVE, timezone="UTC", source="telegram")
    )
    remind_at = datetime(2025, 6, 1, 9, 0, tzinfo=UTC)
    reminder = await reminder_repo.create(Reminder(task_id=task.id, remind_at=remind_at))
    assert reminder.id is not None
    assert reminder.status == ReminderStatus.PENDING

    fetched = await reminder_repo.get(reminder.id)
    assert fetched.remind_at.replace(tzinfo=None) == remind_at.replace(tzinfo=None)


async def test_reminder_list_pending(task_repo, reminder_repo):
    task = await task_repo.create(
        Task(user_id="u6", title="T", status=TaskStatus.ACTIVE, timezone="UTC", source="telegram")
    )
    r1 = await reminder_repo.create(
        Reminder(task_id=task.id, remind_at=datetime(2025, 1, 1, tzinfo=UTC))
    )
    r2 = await reminder_repo.create(
        Reminder(task_id=task.id, remind_at=datetime(2025, 2, 1, tzinfo=UTC))
    )
    await reminder_repo.mark_sent(r1.id)

    pending = await reminder_repo.list_pending()
    ids = [r.id for r in pending]
    assert r2.id in ids
    assert r1.id not in ids


async def test_capture_log_create(log_repo):
    log = CaptureLog(
        user_id="u7",
        source=InputSource.TELEGRAM,
        input_type=InputType.TEXT,
        raw_text="test text",
        parsed_intent={"intent": "create_reminder"},
        confidence=0.9,
    )
    created = await log_repo.create(log)
    assert created.id is not None
    assert created.user_id == "u7"
