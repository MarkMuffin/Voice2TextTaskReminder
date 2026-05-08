from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, settings

if TYPE_CHECKING:
    from app.scheduler.scheduler import ReminderScheduler
from app.providers.llm.base import BaseIntentParser
from app.providers.stt.base import BaseTranscriptionProvider
from app.services.action_router import ActionRouter
from app.services.capture_service import CaptureService
from app.services.reminder_service import ReminderService
from app.services.renderer import Renderer
from app.services.task_service import TaskService
from app.services.user_settings_service import UserSettingsService
from app.storage.repositories import (
    CaptureLogRepository,
    ReminderRepository,
    TaskRepository,
    UserSettingsRepository,
)


def _build_stt(cfg: Settings) -> BaseTranscriptionProvider:
    match cfg.stt_provider.lower():
        case "openai":
            from app.providers.stt.openai_compatible import OpenAICompatibleSTTProvider

            return OpenAICompatibleSTTProvider(
                api_key=cfg.stt_api_key,
                model=cfg.stt_model,
                base_url=cfg.stt_base_url,
            )
        case "groq":
            from app.providers.stt.groq import GroqWhisperProvider

            return GroqWhisperProvider(api_key=cfg.stt_api_key, model=cfg.stt_model)
        case "openrouter":
            from app.providers.stt.openrouter import OpenRouterSTTProvider

            return OpenRouterSTTProvider(
                api_key=cfg.stt_api_key or cfg.openrouter_api_key,
                model=cfg.stt_model,
            )
        case _:
            from app.providers.stt.mock import MockTranscriptionProvider

            return MockTranscriptionProvider()


def _build_llm(cfg: Settings) -> BaseIntentParser:
    match cfg.llm_provider.lower():
        case "openrouter":
            from app.providers.llm.openrouter import OpenRouterIntentParser

            return OpenRouterIntentParser(
                api_key=cfg.openrouter_api_key,
                model=cfg.openrouter_model,
                base_url=cfg.openrouter_base_url,
            )
        case _:
            from app.providers.llm.mock import MockIntentParser

            return MockIntentParser()


class Container:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        cfg: Settings | None = None,
        stt: BaseTranscriptionProvider | None = None,
        llm: BaseIntentParser | None = None,
    ) -> None:
        cfg = cfg or settings
        stt = stt or _build_stt(cfg)
        llm = llm or _build_llm(cfg)

        task_repo = TaskRepository(session_factory)
        reminder_repo = ReminderRepository(session_factory)
        capture_log_repo = CaptureLogRepository(session_factory)
        user_settings_repo = UserSettingsRepository(session_factory)

        self.task_service = TaskService(task_repo)
        self.reminder_service = ReminderService(reminder_repo)
        self.capture_service = CaptureService(stt, llm, capture_log_repo)
        self.action_router = ActionRouter(self.task_service, self.reminder_service)
        self.renderer = Renderer()
        self.user_settings_service = UserSettingsService(user_settings_repo)
        self.scheduler: ReminderScheduler | None = None  # set after bot is created
