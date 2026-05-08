import pytest

from app.domain.enums import IntentType
from app.domain.schemas import ParsedIntent, TaskCreate
from app.services.action_router import ActionRouter
from app.services.reminder_service import ReminderService
from app.services.task_service import TaskService
from app.storage.repositories import ReminderRepository, TaskRepository


@pytest.fixture
def task_service(session_factory):
    return TaskService(TaskRepository(session_factory))


@pytest.fixture
def reminder_service(session_factory):
    return ReminderService(ReminderRepository(session_factory))


@pytest.fixture
def router(task_service, reminder_service):
    return ActionRouter(task_service, reminder_service)


async def test_route_create_reminder(router):
    intent = ParsedIntent(
        intent=IntentType.CREATE_REMINDER,
        title="Купить хлеб",
        remind_at="2025-06-01T09:00:00+00:00",
        timezone="UTC",
        confidence=0.9,
    )
    result = await router.route("user1", intent, "купить хлеб")
    assert result.success
    assert result.task is not None
    assert result.task.title == "Купить хлеб"
    assert result.reminder is not None


async def test_route_create_reminder_no_remind_at(router):
    intent = ParsedIntent(
        intent=IntentType.CREATE_REMINDER,
        title="Просто задача",
        confidence=0.9,
    )
    result = await router.route("user1", intent)
    assert result.success
    assert result.task.title == "Просто задача"
    assert result.reminder is None  # no remind_at → no reminder


async def test_route_list_tasks(router, task_service):
    await task_service.create_task(TaskCreate(user_id="user2", title="Task A"))
    intent = ParsedIntent(intent=IntentType.LIST_TASKS, confidence=1.0)
    result = await router.route("user2", intent)
    assert result.success
    assert result.tasks is not None
    assert len(result.tasks) >= 1


async def test_route_complete_task(router, task_service):
    await task_service.create_task(TaskCreate(user_id="user3", title="Do laundry"))
    intent = ParsedIntent(
        intent=IntentType.COMPLETE_TASK,
        task_reference="laundry",
        confidence=0.9,
    )
    result = await router.route("user3", intent)
    assert result.success
    assert result.task.status == "done"


async def test_route_complete_task_not_found(router):
    intent = ParsedIntent(
        intent=IntentType.COMPLETE_TASK,
        task_reference="несуществующее",
        confidence=0.9,
    )
    result = await router.route("user99", intent)
    assert not result.success
    assert result.requires_confirmation


async def test_route_cancel_task(router, task_service):
    await task_service.create_task(TaskCreate(user_id="user4", title="Buy milk"))
    intent = ParsedIntent(
        intent=IntentType.CANCEL_TASK,
        task_reference="milk",
        confidence=0.9,
    )
    result = await router.route("user4", intent)
    assert result.success
    assert result.task.status == "cancelled"


async def test_route_snooze_task(router, task_service):
    await task_service.create_task(TaskCreate(user_id="user5", title="Call mom"))
    intent = ParsedIntent(
        intent=IntentType.SNOOZE_TASK,
        task_reference="mom",
        snooze_until="2025-12-31T09:00:00+00:00",
        confidence=0.9,
    )
    result = await router.route("user5", intent)
    assert result.success


async def test_route_requires_confirmation(router):
    intent = ParsedIntent(
        intent=IntentType.CREATE_REMINDER,
        title="Something",
        confidence=0.3,
        requires_confirmation=True,
        clarification_question="Когда напомнить?",
    )
    result = await router.route("user1", intent)
    assert not result.success
    assert result.requires_confirmation
    assert result.clarification_question == "Когда напомнить?"


async def test_route_unknown_intent(router):
    intent = ParsedIntent(intent=IntentType.UNKNOWN, confidence=0.0)
    result = await router.route("user1", intent)
    assert not result.success
    assert result.requires_confirmation
