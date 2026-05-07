from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.adapters.telegram.callbacks import TaskCallback
from app.domain.enums import TaskStatus
from app.domain.models import Task
from app.utils.time_utils import format_remind_at


class Renderer:
    """Builds Telegram message text and inline keyboards."""

    # ─── Task created ─────────────────────────────────────────────────────────

    def task_created(self, task: Task) -> tuple[str, InlineKeyboardMarkup]:
        remind_str = ""
        if task.remind_at:
            remind_str = f"\nНапомню: {format_remind_at(task.remind_at, task.timezone)}"
        text = f"✅ Добавил: <b>{task.title}</b>{remind_str}"
        kb = self._task_action_keyboard(task.id)
        return text, kb

    # ─── Task completed ───────────────────────────────────────────────────────

    def task_completed(self, task: Task) -> str:
        return f"✅ Выполнено: <b>{task.title}</b>"

    # ─── Task cancelled ───────────────────────────────────────────────────────

    def task_cancelled(self, task: Task) -> str:
        return f"❌ Отменено: <b>{task.title}</b>"

    # ─── Task snoozed ─────────────────────────────────────────────────────────

    def task_snoozed(self, task: Task) -> str:
        remind_str = ""
        if task.remind_at:
            remind_str = format_remind_at(task.remind_at, task.timezone)
        return f"🔁 Напомню {remind_str}: <b>{task.title}</b>"

    # ─── Task list ────────────────────────────────────────────────────────────

    def task_list(self, tasks: list[Task], title: str = "Активные задачи") -> str:
        if not tasks:
            return f"📋 <b>{title}</b>\n\nНет задач."
        lines = [f"📋 <b>{title}</b>\n"]
        for i, task in enumerate(tasks, 1):
            remind = ""
            if task.remind_at:
                remind = f" — {format_remind_at(task.remind_at, task.timezone)}"
            status_icon = "✅" if task.status == TaskStatus.DONE else "🔘"
            lines.append(f"{i}. {status_icon} {task.title}{remind}")
        return "\n".join(lines)

    # ─── Reminder fire ────────────────────────────────────────────────────────

    def reminder_message(self, task: Task) -> tuple[str, InlineKeyboardMarkup]:
        text = f"⏰ Напоминание: <b>{task.title}</b>"
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Выполнено",
                callback_data=TaskCallback(action="complete", task_id=task.id).pack(),
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🔁 Через 10 мин",
                callback_data=TaskCallback(action="snooze", task_id=task.id, minutes=10).pack(),
            ),
            InlineKeyboardButton(
                text="🔁 Завтра",
                callback_data=TaskCallback(action="snooze", task_id=task.id, minutes=1440).pack(),
            ),
        )
        builder.row(
            InlineKeyboardButton(
                text="❌ Отменить",
                callback_data=TaskCallback(action="cancel", task_id=task.id).pack(),
            )
        )
        return text, builder.as_markup()

    # ─── Clarification ────────────────────────────────────────────────────────

    def clarification(self, question: str) -> str:
        return f"🤔 {question}"

    # ─── Error ────────────────────────────────────────────────────────────────

    def error(self, msg: str = "Что-то пошло не так. Попробуй ещё раз.") -> str:
        return f"⚠️ {msg}"

    # ─── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _task_action_keyboard(task_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Выполнено",
                callback_data=TaskCallback(action="complete", task_id=task_id).pack(),
            ),
            InlineKeyboardButton(
                text="🔁 Позже",
                callback_data=TaskCallback(action="snooze", task_id=task_id, minutes=60).pack(),
            ),
            InlineKeyboardButton(
                text="❌ Отменить",
                callback_data=TaskCallback(action="cancel", task_id=task_id).pack(),
            ),
        )
        return builder.as_markup()
