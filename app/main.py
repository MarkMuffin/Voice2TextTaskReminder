import asyncio
import logging
import os

import uvicorn
from aiogram.types import BotCommand
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from sqlalchemy import inspect, select

from alembic import command as alembic_command
from app.adapters.http.api import recurring_router, set_container
from app.adapters.http.api import router as capture_router
from app.adapters.telegram.bot import create_bot, create_dispatcher
from app.config import settings
from app.container import Container
from app.domain.enums import TaskStatus
from app.domain.models import Base, Task
from app.scheduler.scheduler import ReminderScheduler
from app.storage.db import create_engine, create_session_factory

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app(container: Container) -> FastAPI:
    app = FastAPI(title="Voice2Text Task Reminder", version="0.2.0")
    app.include_router(capture_router)
    app.include_router(recurring_router)
    set_container(container)
    return app


async def _setup_db(engine) -> None:
    """Fresh DB → create_all + stamp head. Existing DB → alembic upgrade head."""
    async with engine.connect() as conn:
        has_alembic = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).has_table("alembic_version")
        )

    alembic_cfg = AlembicConfig("alembic.ini")
    loop = asyncio.get_event_loop()

    if not has_alembic:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await loop.run_in_executor(None, lambda: alembic_command.stamp(alembic_cfg, "head"))
        logger.info("Fresh DB: schema created and migrations stamped at head")
    else:
        await loop.run_in_executor(None, lambda: alembic_command.upgrade(alembic_cfg, "head"))
        logger.info("Existing DB: migrations applied")


async def main() -> None:
    os.makedirs("data", exist_ok=True)

    engine = create_engine()
    session_factory = create_session_factory(engine)
    await _setup_db(engine)

    bot = create_bot(settings.telegram_bot_token)
    await bot.set_my_commands(
        [
            BotCommand(command="list", description="Активные задачи"),
            BotCommand(command="done", description="Выполненные задачи"),
            BotCommand(command="scheduled", description="Повторяющиеся задачи"),
            BotCommand(command="timezone", description="Текущий часовой пояс"),
            BotCommand(command="set_timezone", description="Установить таймзону (напр. Moscow)"),
            BotCommand(command="help", description="Справка"),
        ]
    )
    container = Container(session_factory)
    scheduler = ReminderScheduler(container, bot)
    container.scheduler = scheduler
    scheduler.start()

    # Re-schedule pending reminders on startup
    # Build user_id_map from all active tasks
    user_id_map: dict[int, str] = {}
    async with session_factory() as session:
        result = await session.execute(select(Task).where(Task.status == TaskStatus.ACTIVE))
        for task in result.scalars().all():
            if task.id:
                user_id_map[task.id] = task.user_id

    await scheduler.load_pending(user_id_map)

    if settings.enable_recurring_tasks:
        scheduler.start_recurring_generator(settings.recurring_task_generator_interval_seconds)

    dp = create_dispatcher(container, bot)
    fastapi_app = create_app(container)

    config = uvicorn.Config(
        fastapi_app, host="0.0.0.0", port=8000, log_level=settings.log_level.lower()
    )
    server = uvicorn.Server(config)

    await asyncio.gather(
        dp.start_polling(bot, handle_signals=False),
        server.serve(),
    )


if __name__ == "__main__":
    asyncio.run(main())
