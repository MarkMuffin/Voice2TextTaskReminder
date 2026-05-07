import logging
from typing import TYPE_CHECKING

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.adapters.telegram.callbacks import setup_callbacks
from app.adapters.telegram.handlers import setup_handlers

if TYPE_CHECKING:
    from app.container import Container

logger = logging.getLogger(__name__)


def create_bot(token: str) -> Bot:
    return Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def create_dispatcher(container: "Container", bot: Bot) -> Dispatcher:
    dp = Dispatcher()
    setup_handlers(dp, container, bot)
    setup_callbacks(dp, container)
    return dp
