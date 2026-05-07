import logging
from typing import TYPE_CHECKING

from aiogram import Router
from aiogram.types import CallbackQuery
from aiogram.filters.callback_data import CallbackData

if TYPE_CHECKING:
    from app.container import Container

logger = logging.getLogger(__name__)

router = Router(name="callbacks")


class TaskCallback(CallbackData, prefix="task"):
    action: str  # complete | snooze | cancel
    task_id: int
    minutes: int = 0  # used for snooze


def setup_callbacks(r: Router, container: "Container") -> None:
    """Register callback handlers on an existing router with DI."""

    @r.callback_query(TaskCallback.filter())
    async def handle_task_callback(query: CallbackQuery, callback_data: TaskCallback) -> None:
        task_id = callback_data.task_id
        action = callback_data.action
        user_id = str(query.from_user.id)

        try:
            if action == "complete":
                task = await container.task_service.complete_task(task_id)
                await container.reminder_service.cancel_task_reminders(task_id)
                if task:
                    await query.message.edit_text(
                        container.renderer.task_completed(task), parse_mode="HTML"
                    )
                else:
                    await query.answer("Задача не найдена.")

            elif action == "snooze":
                from app.utils.time_utils import in_minutes, tomorrow_morning

                minutes = callback_data.minutes
                if minutes >= 1440:
                    snooze_until = tomorrow_morning(timezone=None)
                else:
                    snooze_until = in_minutes(minutes)

                task = await container.task_service.snooze_task(task_id, snooze_until)
                if task:
                    await container.reminder_service.reschedule(task_id, snooze_until)
                    container.scheduler.reschedule_reminder(task_id, snooze_until, user_id)
                    await query.message.edit_text(
                        container.renderer.task_snoozed(task), parse_mode="HTML"
                    )
                else:
                    await query.answer("Задача не найдена.")

            elif action == "cancel":
                task = await container.task_service.cancel_task(task_id)
                await container.reminder_service.cancel_task_reminders(task_id)
                container.scheduler.cancel_reminder(task_id)
                if task:
                    await query.message.edit_text(
                        container.renderer.task_cancelled(task), parse_mode="HTML"
                    )
                else:
                    await query.answer("Задача не найдена.")

        except Exception as exc:
            logger.exception("Callback error: %s", exc)
            await query.answer("Ошибка. Попробуй ещё раз.")

        await query.answer()
