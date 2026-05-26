import logging
from datetime import UTC, datetime

import pytz
from sqlalchemy.exc import IntegrityError

from app.domain.enums import CompleteTaskResult, RecurringTaskStatus, TaskStatus
from app.domain.models import RecurringTask, Task
from app.domain.schemas import RecurringTaskCreate
from app.storage.repositories import RecurringTaskRepository, TaskRepository
from app.utils.recurrence import calculate_next_run
from app.utils.time_utils import to_utc_naive

logger = logging.getLogger(__name__)


class RecurringTaskService:
    def __init__(
        self,
        repo: RecurringTaskRepository,
        task_repo: TaskRepository,
    ) -> None:
        self._repo = repo
        self._task_repo = task_repo

    async def create_recurring_task(self, data: RecurringTaskCreate) -> RecurringTask:
        now_utc = datetime.now(UTC)
        # apply_interval=False: first run is always the nearest natural slot,
        # not delayed by interval (interval governs spacing between subsequent runs)
        next_run = calculate_next_run(
            recurrence_type=data.recurrence.type,
            interval=data.recurrence.interval,
            time_of_day=data.recurrence.time_of_day,
            timezone=data.timezone,
            day_of_week=data.recurrence.day_of_week,
            day_of_month=data.recurrence.day_of_month,
            after_utc=now_utc,
            apply_interval=False,
        )
        rt = RecurringTask(
            user_id=data.user_id,
            title=data.title,
            raw_text=data.raw_text,
            source=data.source,
            timezone=data.timezone,
            status=RecurringTaskStatus.ACTIVE,
            recurrence_type=data.recurrence.type,
            interval=data.recurrence.interval,
            time_of_day=data.recurrence.time_of_day,
            day_of_week=data.recurrence.day_of_week,
            day_of_month=data.recurrence.day_of_month,
            next_run_at=to_utc_naive(next_run),
        )
        return await self._repo.create(rt)

    async def list_all_visible(self, user_id: str) -> list[RecurringTask]:
        """Return ACTIVE and PAUSED rules for a user."""
        rules = await self._repo.list_by_user(user_id)
        return [
            r for r in rules if r.status in (RecurringTaskStatus.ACTIVE, RecurringTaskStatus.PAUSED)
        ]

    async def cancel_recurring(
        self, user_id: str, rule_id: int
    ) -> tuple[CompleteTaskResult, RecurringTask | None]:
        rule = await self._repo.get(rule_id)
        if rule is None:
            return CompleteTaskResult.NOT_FOUND, None
        if rule.user_id != user_id:
            return CompleteTaskResult.FORBIDDEN, None
        if rule.status == RecurringTaskStatus.CANCELLED:
            return CompleteTaskResult.ALREADY_INACTIVE, rule
        await self._repo.update_status(
            rule_id, RecurringTaskStatus.CANCELLED, cancelled_at=datetime.utcnow()
        )
        rule.status = RecurringTaskStatus.CANCELLED
        return CompleteTaskResult.COMPLETED, rule

    async def pause_recurring(
        self, user_id: str, rule_id: int
    ) -> tuple[CompleteTaskResult, RecurringTask | None]:
        rule = await self._repo.get(rule_id)
        if rule is None:
            return CompleteTaskResult.NOT_FOUND, None
        if rule.user_id != user_id:
            return CompleteTaskResult.FORBIDDEN, None
        if rule.status != RecurringTaskStatus.ACTIVE:
            return CompleteTaskResult.ALREADY_INACTIVE, rule
        await self._repo.update_status(rule_id, RecurringTaskStatus.PAUSED)
        rule.status = RecurringTaskStatus.PAUSED
        return CompleteTaskResult.COMPLETED, rule

    async def resume_recurring(
        self, user_id: str, rule_id: int
    ) -> tuple[CompleteTaskResult, RecurringTask | None]:
        rule = await self._repo.get(rule_id)
        if rule is None:
            return CompleteTaskResult.NOT_FOUND, None
        if rule.user_id != user_id:
            return CompleteTaskResult.FORBIDDEN, None
        if rule.status == RecurringTaskStatus.CANCELLED:
            return CompleteTaskResult.ALREADY_INACTIVE, rule
        # Recalculate next_run from now (skip missed); same as first-run: nearest slot
        now_utc = datetime.now(UTC)
        next_run = calculate_next_run(
            recurrence_type=rule.recurrence_type,
            interval=rule.interval,
            time_of_day=rule.time_of_day,
            timezone=rule.timezone,
            day_of_week=rule.day_of_week,
            day_of_month=rule.day_of_month,
            after_utc=now_utc,
            apply_interval=False,
        )
        await self._repo.update_status(rule_id, RecurringTaskStatus.ACTIVE)
        await self._repo.update_after_run(
            rule_id,
            last_run_at=rule.last_run_at or now_utc,
            next_run_at=next_run,
        )
        rule.status = RecurringTaskStatus.ACTIVE
        rule.next_run_at = to_utc_naive(next_run)
        return CompleteTaskResult.COMPLETED, rule

    async def generate_due_instances(self, now_utc: datetime) -> list[Task]:
        """Create Task + Reminder for each due recurring rule. Returns created tasks."""
        due_rules = await self._repo.list_due(now_utc)
        created: list[Task] = []

        for rule in due_rules:
            try:
                scheduled_for_utc = _naive_as_utc(rule.next_run_at)

                # Idempotency: skip if task already created for this slot
                existing = await self._task_repo.find_by_recurring_and_scheduled(
                    rule.id, scheduled_for_utc
                )
                if existing is not None:
                    logger.debug(
                        "Recurring rule %s already has task for %s, skipping",
                        rule.id,
                        scheduled_for_utc,
                    )
                else:
                    task = Task(
                        user_id=rule.user_id,
                        title=rule.title,
                        raw_text=rule.raw_text,
                        source=rule.source,
                        status=TaskStatus.ACTIVE,
                        remind_at=to_utc_naive(scheduled_for_utc),
                        timezone=rule.timezone,
                        recurring_task_id=rule.id,
                        scheduled_for=to_utc_naive(scheduled_for_utc),
                    )
                    try:
                        task = await self._task_repo.create(task)
                        created.append(task)
                        logger.info(
                            "Created recurring task instance %s for rule %s scheduled %s",
                            task.id,
                            rule.id,
                            scheduled_for_utc,
                        )
                    except IntegrityError:
                        # Race condition: another worker inserted the same slot just now.
                        # Treat as idempotent — still advance next_run_at below.
                        logger.warning(
                            "Duplicate task for rule %s at %s (race condition) — skipping insert",
                            rule.id,
                            scheduled_for_utc,
                        )

                # Advance next_run_at past now (skip all missed).
                # Always runs — even after IntegrityError — so the rule never gets stuck.
                next_run = calculate_next_run(
                    recurrence_type=rule.recurrence_type,
                    interval=rule.interval,
                    time_of_day=rule.time_of_day,
                    timezone=rule.timezone,
                    day_of_week=rule.day_of_week,
                    day_of_month=rule.day_of_month,
                    after_utc=scheduled_for_utc,
                )
                # Keep skipping until next_run is in the future
                while next_run <= now_utc:
                    next_run = calculate_next_run(
                        recurrence_type=rule.recurrence_type,
                        interval=rule.interval,
                        time_of_day=rule.time_of_day,
                        timezone=rule.timezone,
                        day_of_week=rule.day_of_week,
                        day_of_month=rule.day_of_month,
                        after_utc=next_run,
                    )

                await self._repo.update_after_run(
                    rule.id,
                    last_run_at=scheduled_for_utc,
                    next_run_at=next_run,
                )

            except Exception as exc:
                logger.error("Error generating instance for recurring rule %s: %s", rule.id, exc)
                continue

        return created


def _naive_as_utc(dt: datetime) -> datetime:
    """Attach UTC tzinfo to a naive datetime (SQLite returns naive UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=pytz.utc)
    return dt.astimezone(pytz.utc)
