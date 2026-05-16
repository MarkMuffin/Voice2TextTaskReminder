from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.adapters.telegram.callbacks import TaskCallback, TaskListCallback
from app.domain.enums import TaskStatus
from app.domain.models import Task
from app.utils.time_utils import format_remind_at, format_time_until

TASK_LIST_MAX = 20


class Renderer:
    """Builds Telegram message text and inline keyboards."""

    # ─── Task created ─────────────────────────────────────────────────────────

    def task_created(self, task: Task) -> tuple[str, InlineKeyboardMarkup]:
        remind_str = ""
        if task.remind_at:
            remind_str = f"\nНапомню: {format_remind_at(task.remind_at, task.timezone)}"
            until = format_time_until(task.remind_at)
            if until:
                remind_str += f" ({until})"
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
            until = format_time_until(task.remind_at)
            if until:
                remind_str += f" ({until})"
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
                until = format_time_until(task.remind_at)
                if until:
                    remind += f" ({until})"
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

    # ─── Interactive list (inline keyboard) ───────────────────────────────────

    def render_inline_task_list(
        self, tasks: list[Task], completed: list[Task] | None = None
    ) -> tuple[str, InlineKeyboardMarkup]:
        builder = InlineKeyboardBuilder()
        completed = completed or []

        if not tasks and not completed:
            return "📋 Активных задач нет", builder.as_markup()

        total = len(tasks)
        shown = tasks[:TASK_LIST_MAX]

        lines = ["📋 Активные задачи\n"]

        if shown:
            for i, task in enumerate(shown, 1):
                if task.remind_at:
                    time_str = format_remind_at(task.remind_at, task.timezone)
                    until = format_time_until(task.remind_at)
                    if until:
                        time_str += f" · {until}"
                    remind_line = f"\n   ⏰ {time_str}"
                else:
                    remind_line = "\n   ⏰ без напоминания"
                lines.append(f"{i}. ☐ {task.title}{remind_line}")

            if total > TASK_LIST_MAX:
                lines.append(f"\n⚠️ Показаны первые {TASK_LIST_MAX} из {total}")
        else:
            lines.append("Все задачи выполнены! 🎉")

        if completed:
            lines.append("")
            for task in completed:
                lines.append(f"<s>☑ {task.title}</s>")

        text = "\n".join(lines)

        # Numbered done buttons, 5 per row (only for active tasks)
        done_buttons = [
            InlineKeyboardButton(
                text=f"✅ {i}",
                callback_data=TaskListCallback(action="done", task_id=task.id, task_num=i).pack(),
            )
            for i, task in enumerate(shown, 1)
        ]
        for chunk_start in range(0, len(done_buttons), 5):
            builder.row(*done_buttons[chunk_start : chunk_start + 5])

        builder.row(
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=TaskListCallback(action="refresh").pack(),
            )
        )
        return text, builder.as_markup()

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
