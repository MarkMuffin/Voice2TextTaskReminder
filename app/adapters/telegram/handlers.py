import logging
from typing import TYPE_CHECKING

from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.types import Message

from app.config import settings
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
            "/help — справка"
        )

    @r.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(
            "🗣 Просто скажи или напиши:\n"
            "• «Напомни купить молоко завтра утром»\n"
            "• «Позвонить маме в пятницу вечером»\n"
            "• «Сделал задачу про молоко»\n"
            "• «Отмени напоминание про молоко»\n\n"
            "/list — список активных задач\n"
            "/done — выполненные задачи"
        )

    @r.message(Command("list"))
    async def cmd_list(message: Message) -> None:
        user_id = str(message.from_user.id)
        tasks = await container.task_service.list_active(user_id)
        text = container.renderer.task_list(tasks, "Активные задачи")
        await message.answer(text, parse_mode="HTML")

    @r.message(Command("done"))
    async def cmd_done(message: Message) -> None:
        user_id = str(message.from_user.id)
        tasks = await container.task_service.list_done(user_id)
        text = container.renderer.task_list(tasks, "Выполненные задачи")
        await message.answer(text, parse_mode="HTML")

    @r.message(F.voice)
    async def handle_voice(message: Message) -> None:
        user_id = str(message.from_user.id)
        tz = settings.default_timezone

        await message.answer("🎙 Обрабатываю...")

        try:
            file = await bot.get_file(message.voice.file_id)
            file_bytes = await bot.download_file(file.file_path)
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
        user_id = str(message.from_user.id)
        tz = settings.default_timezone
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
                sent = await message.answer(text, reply_markup=kb, parse_mode="HTML")
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
            await message.answer(
                container.renderer.task_list(tasks), parse_mode="HTML"
            )

        case IntentType.COMPLETE_TASK:
            if r.task:
                await message.answer(
                    container.renderer.task_completed(r.task), parse_mode="HTML"
                )

        case IntentType.SNOOZE_TASK:
            if r.task:
                await message.answer(
                    container.renderer.task_snoozed(r.task), parse_mode="HTML"
                )

        case IntentType.CANCEL_TASK:
            if r.task:
                await message.answer(
                    container.renderer.task_cancelled(r.task), parse_mode="HTML"
                )
        case _:
            await message.answer(container.renderer.error("Неизвестная команда."))
