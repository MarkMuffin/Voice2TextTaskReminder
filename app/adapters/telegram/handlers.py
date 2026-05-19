import logging
from typing import TYPE_CHECKING

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.domain.enums import InputSource

if TYPE_CHECKING:
    from app.container import Container

logger = logging.getLogger(__name__)

router = Router(name="handlers")


def setup_handlers(r: Router, container: "Container", bot: Bot) -> None:
    """Register message handlers with DI container."""

    @r.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        await message.answer(
            "👋 Привет! Я голосовой помощник для задач.\n\n"
            "Отправь голосовое сообщение или текст с командой.\n\n"
            "Команды:\n"
            "/list — активные задачи\n"
            "/done — выполненные задачи\n"
            "/scheduled — повторяющиеся задачи\n"
            "/timezone — текущий часовой пояс\n"
            "/set_timezone <tz> — установить часовой пояс (например: Europe/Moscow)\n"
            "/help — справка"
        )

    @r.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(
            "🗣 Просто скажи или напиши:\n"
            "• «Напомни купить молоко завтра утром»\n"
            "• «Позвонить маме в пятницу вечером»\n"
            "• «Сделал задачу про молоко»\n"
            "• «Отмени напоминание про молоко»\n"
            "• «Каждую пятницу в 17 пополнить фонд»\n\n"
            "/list — список активных задач\n"
            "/done — выполненные задачи\n"
            "/scheduled — повторяющиеся задачи\n"
            "/timezone — текущий часовой пояс\n"
            "/set_timezone <tz> — установить часовой пояс (например: Europe/Moscow)"
        )

    @r.message(Command("scheduled"))
    async def cmd_scheduled(message: Message) -> None:
        from datetime import UTC, datetime

        if message.from_user is None:
            return
        user_id = str(message.from_user.id)
        if container.recurring_service is None:
            await message.answer("🔁 Повторяющиеся задачи отключены.")
            return
        rules = await container.recurring_service.list_all_visible(user_id)
        now_utc = datetime.now(UTC)
        text, kb = container.renderer.render_recurring_task_list(rules, now_utc)
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

    @r.message(Command("list"))
    async def cmd_list(message: Message) -> None:
        if message.from_user is None:
            return
        user_id = str(message.from_user.id)
        tasks = await container.task_service.list_active(user_id)
        text, kb = container.renderer.render_inline_task_list(tasks)
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

    @r.message(Command("done"))
    async def cmd_done(message: Message) -> None:
        if message.from_user is None:
            return
        user_id = str(message.from_user.id)
        tasks = await container.task_service.list_done(user_id)
        text = container.renderer.task_list(tasks, "Выполненные задачи")
        await message.answer(text, parse_mode="HTML")

    @r.message(Command("timezone"))
    async def cmd_timezone(message: Message) -> None:
        if message.from_user is None:
            return
        user_id = str(message.from_user.id)
        tz = await container.user_settings_service.get_user_timezone(user_id)
        await message.answer(f"🕐 Текущий часовой пояс: <b>{tz}</b>", parse_mode="HTML")

    @r.message(Command("set_timezone"))
    async def cmd_set_timezone(message: Message) -> None:
        if message.from_user is None or message.text is None:
            return
        user_id = str(message.from_user.id)
        parts = message.text.strip().split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await message.answer("❌ Укажи город или таймзону. Например: /set_timezone Moscow")
            return
        tz_input = parts[1].strip()
        try:
            resolved = await container.user_settings_service.set_user_timezone(user_id, tz_input)
            await message.answer(f"✅ Таймзона установлена: <b>{resolved}</b>", parse_mode="HTML")
        except ValueError:
            await message.answer(
                "❌ Не удалось найти таймзону. Укажи город по-английски (Moscow, London, Tokyo) "
                "или IANA-формат (Europe/Moscow)"
            )

    @r.message(F.voice)
    async def handle_voice(message: Message) -> None:
        if message.from_user is None or message.voice is None:
            return
        user_id = str(message.from_user.id)
        tz = await container.user_settings_service.get_user_timezone(user_id)

        await message.answer("🎙 Обрабатываю...")

        try:
            file = await bot.get_file(message.voice.file_id)
            assert file.file_path is not None
            file_bytes = await bot.download_file(file.file_path)
            assert file_bytes is not None
            audio_bytes = file_bytes.read()

            transcript, intent = await container.capture_service.process_voice(
                user_id=user_id,
                audio_bytes=audio_bytes,
                source=InputSource.TELEGRAM,
                timezone=tz,
                filename="audio.ogg",
            )

            result = await container.action_router.route(
                user_id=user_id, intent=intent, raw_text=transcript
            )

            await _send_result(message, result, container, user_id)

        except Exception as exc:
            logger.exception("Voice handler error: %s", exc)
            await message.answer(container.renderer.error())

    @r.message(F.text & ~F.text.startswith("/"))
    async def handle_text(message: Message) -> None:
        if message.from_user is None or message.text is None:
            return
        user_id = str(message.from_user.id)
        tz = await container.user_settings_service.get_user_timezone(user_id)
        text = message.text.strip()

        try:
            intent = await container.capture_service.process_text(
                user_id=user_id,
                text=text,
                source=InputSource.TELEGRAM,
                timezone=tz,
            )
            result = await container.action_router.route(
                user_id=user_id, intent=intent, raw_text=text
            )
            await _send_result(message, result, container, user_id)

        except Exception as exc:
            logger.exception("Text handler error: %s", exc)
            await message.answer(container.renderer.error())


async def _send_result(message: Message, result, container, user_id: str) -> None:
    from datetime import UTC, datetime

    from app.domain.enums import IntentType
    from app.services.action_router import ActionResult

    r: ActionResult = result

    if r.requires_confirmation:
        question = r.clarification_question or "Не понял. Уточни команду."
        await message.answer(container.renderer.clarification(question))
        return

    if not r.success:
        await message.answer(container.renderer.error())
        return

    match r.intent:
        case IntentType.CREATE_REMINDER:
            if r.task:
                text, kb = container.renderer.task_created(r.task)
                await message.answer(text, reply_markup=kb, parse_mode="HTML")
                # Schedule reminder in APScheduler
                if r.task.remind_at and r.reminder:
                    container.scheduler.schedule_reminder(
                        reminder_id=r.reminder.id,
                        task_id=r.task.id,
                        remind_at=r.task.remind_at,
                        user_id=user_id,
                    )

        case IntentType.LIST_TASKS:
            tasks = r.tasks or []
            await message.answer(container.renderer.task_list(tasks), parse_mode="HTML")

        case IntentType.COMPLETE_TASK:
            if r.task:
                await message.answer(container.renderer.task_completed(r.task), parse_mode="HTML")

        case IntentType.SNOOZE_TASK:
            if r.task:
                await message.answer(container.renderer.task_snoozed(r.task), parse_mode="HTML")

        case IntentType.CANCEL_TASK:
            if r.task:
                await message.answer(container.renderer.task_cancelled(r.task), parse_mode="HTML")

        case IntentType.CREATE_RECURRING_TASK:
            if r.recurring_task:
                now_utc = datetime.now(UTC)
                text = container.renderer.render_recurring_task_created(r.recurring_task, now_utc)
                await message.answer(text, parse_mode="HTML")

        case IntentType.LIST_RECURRING_TASKS:
            rules = r.recurring_tasks or []
            now_utc = datetime.now(UTC)
            text, kb = container.renderer.render_recurring_task_list(rules, now_utc)
            await message.answer(text, reply_markup=kb, parse_mode="HTML")

        case (
            IntentType.CANCEL_RECURRING_TASK
            | IntentType.PAUSE_RECURRING_TASK
            | IntentType.RESUME_RECURRING_TASK
        ):
            if r.recurring_task:
                now_utc = datetime.now(UTC)
                rules = await container.recurring_service.list_all_visible(user_id)
                text, kb = container.renderer.render_recurring_task_list(rules, now_utc)
                await message.answer(text, reply_markup=kb, parse_mode="HTML")

        case _:
            await message.answer(container.renderer.error("Неизвестная команда."))
