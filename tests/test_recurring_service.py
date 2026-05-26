"""Tests for RecurringTaskService (async + real in-memory DB)."""

from datetime import UTC, datetime, timedelta

import pytest_asyncio
import pytz
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domain.enums import CompleteTaskResult, RecurrenceType, RecurringTaskStatus
from app.domain.schemas import RecurrenceRule, RecurringTaskCreate
from app.services.recurring_service import RecurringTaskService
from app.storage.db import init_db
from app.storage.repositories import RecurringTaskRepository, TaskRepository

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    e = create_async_engine(TEST_DB_URL, echo=False)
    await init_db(e)
    yield e
    await e.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def recurring_service(session_factory):
    repo = RecurringTaskRepository(session_factory)
    task_repo = TaskRepository(session_factory)
    return RecurringTaskService(repo, task_repo)


def _daily_rule(user_id: str = "user1", time_of_day: str = "09:00") -> RecurringTaskCreate:
    return RecurringTaskCreate(
        user_id=user_id,
        title="Daily task",
        timezone="Europe/Amsterdam",
        recurrence=RecurrenceRule(
            type=RecurrenceType.DAILY,
            interval=1,
            time_of_day=time_of_day,
        ),
    )


def _weekly_friday_rule(user_id: str = "user1") -> RecurringTaskCreate:
    return RecurringTaskCreate(
        user_id=user_id,
        title="Weekly Friday task",
        timezone="Europe/Amsterdam",
        recurrence=RecurrenceRule(
            type=RecurrenceType.WEEKLY,
            interval=1,
            time_of_day="17:00",
            day_of_week=4,
        ),
    )


class TestCreateRecurringTask:
    async def test_create_recurring_task(self, recurring_service):
        data = _daily_rule()
        rule = await recurring_service.create_recurring_task(data)

        assert rule.id is not None
        assert rule.title == "Daily task"
        assert rule.status == RecurringTaskStatus.ACTIVE
        assert rule.recurrence_type == RecurrenceType.DAILY
        assert rule.next_run_at is not None

    async def test_create_weekly_friday_task(self, recurring_service):
        data = _weekly_friday_rule()
        rule = await recurring_service.create_recurring_task(data)

        assert rule.recurrence_type == RecurrenceType.WEEKLY
        assert rule.day_of_week == 4
        assert rule.time_of_day == "17:00"


class TestGenerateDueInstances:
    async def test_generate_due_instance_creates_task(self, recurring_service):
        # Create rule with next_run_at in the past
        data = _daily_rule(time_of_day="09:00")
        rule = await recurring_service.create_recurring_task(data)

        # Manually set next_run_at to past
        await recurring_service._repo.update_after_run(
            rule.id,
            last_run_at=datetime.utcnow() - timedelta(hours=2),
            next_run_at=datetime.utcnow() - timedelta(hours=1),
        )

        now_utc = datetime.now(UTC)
        created = await recurring_service.generate_due_instances(now_utc)

        assert len(created) == 1
        task = created[0]
        assert task.title == "Daily task"
        assert task.recurring_task_id == rule.id
        assert task.scheduled_for is not None

    async def test_generate_idempotency_no_duplicate(self, recurring_service):
        data = _daily_rule()
        rule = await recurring_service.create_recurring_task(data)

        past_time = datetime.utcnow() - timedelta(hours=1)
        await recurring_service._repo.update_after_run(
            rule.id,
            last_run_at=datetime.utcnow() - timedelta(hours=2),
            next_run_at=past_time,
        )

        now_utc = datetime.now(UTC)
        # First generation
        created1 = await recurring_service.generate_due_instances(now_utc)
        assert len(created1) == 1

        # Move next_run_at back to past again to simulate second trigger on same slot
        await recurring_service._repo.update_after_run(
            rule.id,
            last_run_at=past_time,
            next_run_at=past_time,  # same time — idempotency should kick in
        )

        created2 = await recurring_service.generate_due_instances(now_utc)
        assert len(created2) == 0  # No duplicate

    async def test_generate_missed_runs_creates_one_skips_to_future(self, recurring_service):
        """If many runs are missed, only one task is created and next_run is in the future."""
        data = _daily_rule()
        rule = await recurring_service.create_recurring_task(data)

        # Simulate a very old next_run_at (3 days ago)
        await recurring_service._repo.update_after_run(
            rule.id,
            last_run_at=datetime.utcnow() - timedelta(days=4),
            next_run_at=datetime.utcnow() - timedelta(days=3),
        )

        now_utc = datetime.now(UTC)
        created = await recurring_service.generate_due_instances(now_utc)

        # Only one task should be created (for the oldest missed slot)
        assert len(created) == 1

        # next_run_at should now be in the future
        updated_rule = await recurring_service._repo.get(rule.id)
        assert updated_rule is not None
        next_run = updated_rule.next_run_at
        if next_run.tzinfo is None:
            next_run = pytz.utc.localize(next_run)
        assert next_run > now_utc

    async def test_generate_paused_rule_skipped(self, recurring_service):
        data = _daily_rule()
        rule = await recurring_service.create_recurring_task(data)

        # Pause rule
        await recurring_service._repo.update_status(rule.id, RecurringTaskStatus.PAUSED)
        # Set past next_run_at
        await recurring_service._repo.update_after_run(
            rule.id,
            last_run_at=datetime.utcnow() - timedelta(hours=2),
            next_run_at=datetime.utcnow() - timedelta(hours=1),
        )

        now_utc = datetime.now(UTC)
        created = await recurring_service.generate_due_instances(now_utc)
        assert len(created) == 0  # Paused rules skipped


class TestCancelRecurringTask:
    async def test_cancel_recurring_task(self, recurring_service):
        data = _daily_rule()
        rule = await recurring_service.create_recurring_task(data)

        result, updated = await recurring_service.cancel_recurring("user1", rule.id)

        assert result == CompleteTaskResult.COMPLETED
        assert updated is not None
        assert updated.status == RecurringTaskStatus.CANCELLED

    async def test_cancel_forbidden(self, recurring_service):
        data = _daily_rule(user_id="user1")
        rule = await recurring_service.create_recurring_task(data)

        result, updated = await recurring_service.cancel_recurring("user2", rule.id)

        assert result == CompleteTaskResult.FORBIDDEN
        assert updated is None

    async def test_cancel_not_found(self, recurring_service):
        result, updated = await recurring_service.cancel_recurring("user1", 9999)
        assert result == CompleteTaskResult.NOT_FOUND


class TestPauseRecurringTask:
    async def test_pause_recurring_task(self, recurring_service):
        data = _daily_rule()
        rule = await recurring_service.create_recurring_task(data)

        result, updated = await recurring_service.pause_recurring("user1", rule.id)

        assert result == CompleteTaskResult.COMPLETED
        assert updated is not None
        assert updated.status == RecurringTaskStatus.PAUSED

    async def test_pause_already_paused(self, recurring_service):
        data = _daily_rule()
        rule = await recurring_service.create_recurring_task(data)
        await recurring_service.pause_recurring("user1", rule.id)

        result, updated = await recurring_service.pause_recurring("user1", rule.id)
        assert result == CompleteTaskResult.ALREADY_INACTIVE


class TestResumeRecurringTask:
    async def test_resume_recalculates_next_run(self, recurring_service):
        data = _daily_rule()
        rule = await recurring_service.create_recurring_task(data)

        # Pause first
        await recurring_service.pause_recurring("user1", rule.id)

        now_utc = datetime.now(UTC)
        result, updated = await recurring_service.resume_recurring("user1", rule.id)

        assert result == CompleteTaskResult.COMPLETED
        assert updated is not None
        assert updated.status == RecurringTaskStatus.ACTIVE

        # next_run_at should be refreshed (in the future)
        refreshed = await recurring_service._repo.get(rule.id)
        new_next_run = refreshed.next_run_at
        if new_next_run.tzinfo is None:
            new_next_run = pytz.utc.localize(new_next_run)
        assert new_next_run > now_utc


class TestGenerateDuplicateInsert:
    async def test_integrity_error_on_duplicate_insert_advances_next_run(self, recurring_service):
        """Regression: IntegrityError on duplicate insert must not block next_run_at advance.

        Simulates a race condition where the app-level idempotency check is bypassed
        (e.g., two workers read list_due simultaneously). The second insert raises
        IntegrityError. Before the fix, update_after_run was skipped and the rule
        would retry the same slot forever.
        """
        from unittest.mock import AsyncMock, patch

        data = _daily_rule()
        rule = await recurring_service.create_recurring_task(data)

        past_time = datetime.now(UTC) - timedelta(hours=1)
        await recurring_service._repo.update_after_run(
            rule.id,
            last_run_at=datetime.now(UTC) - timedelta(hours=2),
            next_run_at=past_time,
        )

        # Patch find_by_recurring_and_scheduled to return None (bypassing app-level guard)
        # and create to raise IntegrityError (simulating the DB-level race condition)
        from sqlalchemy.exc import IntegrityError

        with (
            patch.object(
                recurring_service._task_repo,
                "find_by_recurring_and_scheduled",
                new=AsyncMock(return_value=None),
            ),
            patch.object(
                recurring_service._task_repo,
                "create",
                new=AsyncMock(side_effect=IntegrityError("duplicate", {}, Exception())),
            ),
        ):
            now_utc = datetime.now(UTC)
            created = await recurring_service.generate_due_instances(now_utc)

        # No task returned (insert failed), but next_run_at must have advanced
        assert len(created) == 0

        updated_rule = await recurring_service._repo.get(rule.id)
        assert updated_rule is not None
        next_run = updated_rule.next_run_at
        if next_run.tzinfo is None:
            next_run = pytz.utc.localize(next_run)
        assert next_run > now_utc, "next_run_at must advance even after IntegrityError"


class TestListAllVisible:
    async def test_list_all_visible(self, recurring_service):
        # Create active and paused rules; cancelled should not appear
        await recurring_service.create_recurring_task(_daily_rule(user_id="user42"))
        rule2 = await recurring_service.create_recurring_task(_weekly_friday_rule(user_id="user42"))
        await recurring_service.pause_recurring("user42", rule2.id)

        # Create a cancelled one
        rule3 = await recurring_service.create_recurring_task(_daily_rule(user_id="user42"))
        await recurring_service.cancel_recurring("user42", rule3.id)

        visible = await recurring_service.list_all_visible("user42")
        assert len(visible) == 2
        statuses = {r.status for r in visible}
        assert RecurringTaskStatus.CANCELLED not in statuses
