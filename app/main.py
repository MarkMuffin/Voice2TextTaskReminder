import asyncio
import logging
import os

import uvicorn
from fastapi import FastAPI

from app.adapters.http.api import router as capture_router, set_container
from app.adapters.telegram.bot import create_bot, create_dispatcher
from app.config import settings
from app.container import Container
from app.scheduler.scheduler import ReminderScheduler
from app.storage.db import create_engine, create_session_factory, init_db

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app(container: Container) -> FastAPI:
    app = FastAPI(title="Voice2Text Task Reminder", version="0.1.0")
    app.include_router(capture_router)
    set_container(container)
    return app


async def main() -> None:
    os.makedirs("data", exist_ok=True)

    engine = create_engine()
    session_factory = create_session_factory(engine)
    await init_db(engine)

    bot = create_bot(settings.telegram_bot_token)
    container = Container(session_factory)
    scheduler = ReminderScheduler(container, bot)
    container.scheduler = scheduler
    scheduler.start()

    # Re-schedule pending reminders on startup
    tasks = await container.task_service.list_all("*")  # won't work — load all tasks
    # Build user_id_map from all active tasks
    user_id_map: dict[int, str] = {}
    from app.domain.enums import TaskStatus
    from sqlalchemy import select
    from app.domain.models import Task
    async with session_factory() as session:
        result = await session.execute(
            select(Task).where(Task.status == TaskStatus.ACTIVE)
        )
        for task in result.scalars().all():
            if task.id:
                user_id_map[task.id] = task.user_id

    await scheduler.load_pending(user_id_map)

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
