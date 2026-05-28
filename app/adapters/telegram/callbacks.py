import logging
from typing import TYPE_CHECKING

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, Message

from app.domain.enums import CompleteTaskResult

if TYPE_CHECKING:
    from app.container import Container

logger = logging.getLogger(__name__)

router = Router(name="callbacks")


class TaskCallback(CallbackData, prefix="task"):
    action: str  # complete | snooze | cancel
    task_id: int
    minutes: int = 0  # used for snooze


class TaskListCallback(CallbackData, prefix="tl"):
    action: str  # done | refresh
    task_id: int = 0
    task_num: int = 0  # display number (for button label only, not DB key)


class RecurringCallback(CallbackData, prefix="rt"):
    action: str  # cancel | pause | resume | refresh
    rule_id: int = 0


def setup_callbacks(r: Router, container: "Container") -> None:
    """Register callback handlers on an existing router with DI."""

    @r.callback_query(TaskCallback.filter())
    async def handle_task_callback(query: CallbackQuery, callback_data: TaskCallback) -> None:
        task_id = callback_data.task_id
        action = callback_data.action
        user_id = str(query.from_user.id)

        if not isinstance(query.message, Message):
            return

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
                    snooze_until = tomorrow_morning()
                else:
                    snooze_until = in_minutes(minutes)

                task = await container.task_service.snooze_task(task_id, snooze_until)
                if task:
                    await container.reminder_service.reschedule(task_id, snooze_until)
                    if container.scheduler is not None:
                        container.scheduler.reschedule_reminder(task_id, snooze_until, user_id)
                    await query.message.edit_text(
                        container.renderer.task_snoozed(task), parse_mode="HTML"
                    )
                else:
                    await query.answer("Задача не найдена.")

            elif action == "cancel":
                task = await container.task_service.cancel_task(task_id)
                await container.reminder_service.cancel_task_reminders(task_id)
                if container.scheduler is not None:
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

    @r.callback_query(TaskListCallback.filter(F.action == "done"))
    async def handle_list_done(query: CallbackQuery, callback_data: TaskListCallback) -> None:
        if not isinstance(query.message, Message):
            return
        user_id = str(query.from_user.id)
        task_id = callback_data.task_id
        chat_id = query.message.chat.id
        message_id = query.message.message_id

        result, task = await container.task_service.complete_task_safe(user_id, task_id)

        if result == CompleteTaskResult.FORBIDDEN:
            await query.answer("⛔ Эта задача не принадлежит тебе")
            return
        elif result == CompleteTaskResult.NOT_FOUND:
            await query.answer("❌ Задача не найдена")
        elif result == CompleteTaskResult.ALREADY_INACTIVE:
            await query.answer("ℹ️ Задача уже закрыта")
            container.list_session_store.mark_completed(chat_id, message_id, task_id)
        else:  # COMPLETED
            await container.reminder_service.cancel_task_reminders(task_id)
            await query.answer("✅ Готово")
            container.list_session_store.mark_completed(chat_id, message_id, task_id)

        completed_ids = container.list_session_store.get_completed_ids(chat_id, message_id)
        visible_task_ids = container.list_session_store.get_visible_task_ids(chat_id, message_id)
        tasks = await container.task_service.list_active(user_id)
        completed_tasks = (
            await container.task_service.get_tasks_by_ids(completed_ids) if completed_ids else []
        )
        text, kb = container.renderer.render_inline_task_list(
            tasks,
            completed_in_session=completed_tasks or None,
            visible_task_ids=visible_task_ids or None,
        )
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except TelegramBadRequest:
            pass

    @r.callback_query(TaskListCallback.filter(F.action == "refresh"))
    async def handle_list_refresh(query: CallbackQuery) -> None:
        if not isinstance(query.message, Message):
            return
        user_id = str(query.from_user.id)
        chat_id = query.message.chat.id
        message_id = query.message.message_id

        container.list_session_store.clear_session(chat_id, message_id)

        tasks = await container.task_service.list_active(user_id)
        text, kb = container.renderer.render_inline_task_list(tasks)
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except TelegramBadRequest:
            pass
        await query.answer()

    async def _refresh_recurring_list(query: CallbackQuery, user_id: str) -> None:
        from datetime import UTC, datetime

        if container.recurring_service is None:
            await query.answer("Повторяющиеся задачи отключены.")
            return
        if not isinstance(query.message, Message):
            return
        rules = await container.recurring_service.list_all_visible(user_id)
        now_utc = datetime.now(UTC)
        text, kb = container.renderer.render_recurring_task_list(rules, now_utc)
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except TelegramBadRequest:
            pass

    @r.callback_query(RecurringCallback.filter(F.action == "refresh"))
    async def handle_recurring_refresh(query: CallbackQuery) -> None:
        if not isinstance(query.message, Message):
            return
        user_id = str(query.from_user.id)
        await _refresh_recurring_list(query, user_id)
        await query.answer()

    @r.callback_query(RecurringCallback.filter(F.action == "cancel"))
    async def handle_recurring_cancel(
        query: CallbackQuery, callback_data: RecurringCallback
    ) -> None:
        if not isinstance(query.message, Message):
            return
        user_id = str(query.from_user.id)
        if container.recurring_service is None:
            await query.answer("Повторяющиеся задачи отключены.")
            return
        from app.domain.enums import CompleteTaskResult

        result, _ = await container.recurring_service.cancel_recurring(
            user_id, callback_data.rule_id
        )
        if result == CompleteTaskResult.FORBIDDEN:
            await query.answer("⛔ Это расписание не принадлежит тебе")
            return
        elif result == CompleteTaskResult.NOT_FOUND:
            await query.answer("❌ Расписание не найдено")
            return
        await query.answer("❌ Расписание отменено")
        await _refresh_recurring_list(query, user_id)

    @r.callback_query(RecurringCallback.filter(F.action == "pause"))
    async def handle_recurring_pause(
        query: CallbackQuery, callback_data: RecurringCallback
    ) -> None:
        if not isinstance(query.message, Message):
            return
        user_id = str(query.from_user.id)
        if container.recurring_service is None:
            await query.answer("Повторяющиеся задачи отключены.")
            return
        from app.domain.enums import CompleteTaskResult

        result, _ = await container.recurring_service.pause_recurring(
            user_id, callback_data.rule_id
        )
        if result == CompleteTaskResult.FORBIDDEN:
            await query.answer("⛔ Это расписание не принадлежит тебе")
            return
        elif result == CompleteTaskResult.NOT_FOUND:
            await query.answer("❌ Расписание не найдено")
            return
        await query.answer("⏸ Расписание приостановлено")
        await _refresh_recurring_list(query, user_id)

    @r.callback_query(RecurringCallback.filter(F.action == "resume"))
    async def handle_recurring_resume(
        query: CallbackQuery, callback_data: RecurringCallback
    ) -> None:
        if not isinstance(query.message, Message):
            return
        user_id = str(query.from_user.id)
        if container.recurring_service is None:
            await query.answer("Повторяющиеся задачи отключены.")
            return
        from app.domain.enums import CompleteTaskResult

        result, _ = await container.recurring_service.resume_recurring(
            user_id, callback_data.rule_id
        )
        if result == CompleteTaskResult.FORBIDDEN:
            await query.answer("⛔ Это расписание не принадлежит тебе")
            return
        elif result == CompleteTaskResult.NOT_FOUND:
            await query.answer("❌ Расписание не найдено")
            return
        await query.answer("▶️ Расписание возобновлено")
        await _refresh_recurring_list(query, user_id)
