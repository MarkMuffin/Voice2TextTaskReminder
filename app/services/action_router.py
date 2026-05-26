import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.domain.enums import IntentType
from app.domain.models import Reminder, Task
from app.domain.schemas import ParsedIntent, RecurringTaskCreate, TaskCreate
from app.services.reminder_service import ReminderService
from app.services.task_service import TaskService
from app.utils.time_utils import in_minutes, parse_remind_at

if TYPE_CHECKING:
    from app.domain.models import RecurringTask
    from app.services.recurring_service import RecurringTaskService

logger = logging.getLogger(__name__)


@dataclass
class ActionResult:
    success: bool
    intent: IntentType
    task: Task | None = None
    tasks: list[Task] | None = None
    reminder: Reminder | None = None
    message: str = ""
    requires_confirmation: bool = False
    clarification_question: str | None = None
    recurring_task: "RecurringTask | None" = None
    recurring_tasks: "list[RecurringTask] | None" = None


class ActionRouter:
    def __init__(
        self,
        task_service: TaskService,
        reminder_service: ReminderService,
        recurring_service: "RecurringTaskService | None" = None,
    ) -> None:
        self._tasks = task_service
        self._reminders = reminder_service
        self._recurring = recurring_service

    async def route(
        self,
        user_id: str,
        intent: ParsedIntent,
        raw_text: str | None = None,
    ) -> ActionResult:
        if intent.requires_confirmation:
            return ActionResult(
                success=False,
                intent=intent.intent,
                requires_confirmation=True,
                clarification_question=intent.clarification_question,
            )

        match intent.intent:
            case IntentType.CREATE_REMINDER:
                return await self._create_reminder(user_id, intent, raw_text)
            case IntentType.LIST_TASKS:
                return await self._list_tasks(user_id, intent)
            case IntentType.COMPLETE_TASK:
                return await self._complete_task(user_id, intent)
            case IntentType.SNOOZE_TASK:
                return await self._snooze_task(user_id, intent)
            case IntentType.CANCEL_TASK:
                return await self._cancel_task(user_id, intent)
            case IntentType.CREATE_RECURRING_TASK:
                return await self._create_recurring_task(user_id, intent, raw_text)
            case IntentType.LIST_RECURRING_TASKS:
                return await self._list_recurring_tasks(user_id, intent)
            case IntentType.CANCEL_RECURRING_TASK:
                return await self._manage_recurring(user_id, intent, "cancel")
            case IntentType.PAUSE_RECURRING_TASK:
                return await self._manage_recurring(user_id, intent, "pause")
            case IntentType.RESUME_RECURRING_TASK:
                return await self._manage_recurring(user_id, intent, "resume")
            case _:
                return ActionResult(
                    success=False,
                    intent=IntentType.UNKNOWN,
                    requires_confirmation=True,
                    clarification_question="Не понял команду. Попробуй ещё раз.",
                )

    async def _create_reminder(
        self, user_id: str, intent: ParsedIntent, raw_text: str | None
    ) -> ActionResult:
        if not intent.title:
            return ActionResult(
                success=False,
                intent=intent.intent,
                requires_confirmation=True,
                clarification_question="О чём напомнить?",
            )

        remind_at = parse_remind_at(intent.remind_at, intent.timezone)
        task = await self._tasks.create_task(
            TaskCreate(
                user_id=user_id,
                title=intent.title,
                raw_text=raw_text,
                remind_at=remind_at,
                timezone=intent.timezone,
            )
        )

        reminder: Reminder | None = None
        if remind_at and task.id:
            reminder = await self._reminders.schedule_reminder(task.id, remind_at)

        return ActionResult(
            success=True,
            intent=intent.intent,
            task=task,
            reminder=reminder,
        )

    async def _list_tasks(self, user_id: str, intent: ParsedIntent) -> ActionResult:
        tasks = await self._tasks.list_active(user_id)
        return ActionResult(success=True, intent=intent.intent, tasks=tasks)

    async def _complete_task(self, user_id: str, intent: ParsedIntent) -> ActionResult:
        task = await self._resolve_task(user_id, intent)
        if not task:
            return self._task_not_found(intent)
        updated = await self._tasks.complete_task(task.id)
        await self._reminders.cancel_task_reminders(task.id)
        return ActionResult(success=True, intent=intent.intent, task=updated)

    async def _snooze_task(self, user_id: str, intent: ParsedIntent) -> ActionResult:
        task = await self._resolve_task(user_id, intent)
        if not task:
            return self._task_not_found(intent)

        snooze_until: datetime | None = parse_remind_at(intent.snooze_until, intent.timezone)
        if snooze_until is None:
            snooze_until = in_minutes(10, intent.timezone)

        updated = await self._tasks.snooze_task(task.id, snooze_until)
        await self._reminders.reschedule(task.id, snooze_until)
        return ActionResult(success=True, intent=intent.intent, task=updated)

    async def _cancel_task(self, user_id: str, intent: ParsedIntent) -> ActionResult:
        task = await self._resolve_task(user_id, intent)
        if not task:
            return self._task_not_found(intent)
        updated = await self._tasks.cancel_task(task.id)
        await self._reminders.cancel_task_reminders(task.id)
        return ActionResult(success=True, intent=intent.intent, task=updated)

    async def _create_recurring_task(
        self, user_id: str, intent: ParsedIntent, raw_text: str | None
    ) -> ActionResult:
        if self._recurring is None:
            return ActionResult(
                success=False,
                intent=intent.intent,
                requires_confirmation=True,
                clarification_question="Повторяющиеся задачи отключены.",
            )
        if not intent.title or not intent.recurrence:
            return ActionResult(
                success=False,
                intent=intent.intent,
                requires_confirmation=True,
                clarification_question="Укажи задачу и расписание.",
            )
        data = RecurringTaskCreate(
            user_id=user_id,
            title=intent.title,
            raw_text=raw_text,
            timezone=intent.timezone,
            recurrence=intent.recurrence,
        )
        rule = await self._recurring.create_recurring_task(data)
        return ActionResult(success=True, intent=intent.intent, recurring_task=rule)

    async def _list_recurring_tasks(self, user_id: str, intent: ParsedIntent) -> ActionResult:
        if self._recurring is None:
            return ActionResult(
                success=False,
                intent=intent.intent,
                requires_confirmation=True,
                clarification_question="Повторяющиеся задачи отключены.",
            )
        rules = await self._recurring.list_all_visible(user_id)
        return ActionResult(success=True, intent=intent.intent, recurring_tasks=rules)

    async def _manage_recurring(
        self, user_id: str, intent: ParsedIntent, action: str
    ) -> ActionResult:
        if self._recurring is None:
            return ActionResult(
                success=False,
                intent=intent.intent,
                requires_confirmation=True,
                clarification_question="Повторяющиеся задачи отключены.",
            )
        ref = intent.recurring_task_reference
        if not ref:
            return ActionResult(
                success=False,
                intent=intent.intent,
                requires_confirmation=True,
                clarification_question="Укажи какое расписание изменить.",
            )
        # Try to parse ref as integer ID first
        rule_id: int | None = None
        try:
            rule_id = int(ref)
        except ValueError:
            pass

        if rule_id is None:
            return ActionResult(
                success=False,
                intent=intent.intent,
                requires_confirmation=True,
                clarification_question="Не нашёл расписание. Используй /scheduled для просмотра.",
            )

        from app.domain.enums import CompleteTaskResult

        if action == "cancel":
            result, rule = await self._recurring.cancel_recurring(user_id, rule_id)
        elif action == "pause":
            result, rule = await self._recurring.pause_recurring(user_id, rule_id)
        else:
            result, rule = await self._recurring.resume_recurring(user_id, rule_id)

        if result == CompleteTaskResult.FORBIDDEN:
            return ActionResult(
                success=False,
                intent=intent.intent,
                requires_confirmation=True,
                clarification_question="⛔ Это расписание не принадлежит тебе.",
            )
        if result == CompleteTaskResult.NOT_FOUND:
            return ActionResult(
                success=False,
                intent=intent.intent,
                requires_confirmation=True,
                clarification_question="Не нашёл расписание. Используй /scheduled.",
            )
        return ActionResult(success=True, intent=intent.intent, recurring_task=rule)

    async def _resolve_task(self, user_id: str, intent: ParsedIntent) -> Task | None:
        """Try to find task by reference string."""
        if not intent.task_reference:
            return None
        return await self._tasks.find_by_reference(user_id, intent.task_reference)

    @staticmethod
    def _task_not_found(intent: ParsedIntent) -> ActionResult:
        return ActionResult(
            success=False,
            intent=intent.intent,
            requires_confirmation=True,
            clarification_question="Не нашёл такую задачу. Уточни название.",
        )
