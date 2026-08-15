from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, settings

if TYPE_CHECKING:
    from app.scheduler.scheduler import ReminderScheduler
from app.providers.llm.base import BaseIntentParser
from app.providers.stt.base import BaseTranscriptionProvider
from app.services.action_router import ActionRouter
from app.services.capture_service import CaptureService
from app.services.list_session import ListSessionStore
from app.services.recurring_service import RecurringTaskService
from app.services.reminder_service import ReminderService
from app.services.renderer import Renderer
from app.services.task_service import TaskService
from app.services.user_settings_service import UserSettingsService
from app.storage.repositories import (
    CaptureLogRepository,
    RecurringTaskRepository,
    ReminderRepository,
    TaskRepository,
    UserSettingsRepository,
)


def _build_fallback_stt(cfg: Settings) -> BaseTranscriptionProvider:
    providers: list[tuple[str, BaseTranscriptionProvider]] = []

    if cfg.groq_api_key:
        from app.providers.stt.groq import GROQ_DEFAULT_MODEL, GroqWhisperProvider

        providers.append(
            (
                "groq",
                GroqWhisperProvider(
                    api_key=cfg.groq_api_key,
                    model=cfg.groq_stt_model or GROQ_DEFAULT_MODEL,
                ),
            )
        )

    if cfg.openrouter_api_key:
        from app.providers.stt.openrouter import (
            OPENROUTER_DEFAULT_STT_MODEL,
            OpenRouterSTTProvider,
        )

        providers.append(
            (
                "openrouter",
                OpenRouterSTTProvider(
                    api_key=cfg.openrouter_api_key,
                    model=cfg.openrouter_stt_model or OPENROUTER_DEFAULT_STT_MODEL,
                ),
            )
        )

    if cfg.stt_api_key:
        from app.providers.stt.openai_compatible import OpenAICompatibleSTTProvider

        providers.append(
            (
                "openai",
                OpenAICompatibleSTTProvider(
                    api_key=cfg.stt_api_key,
                    model=cfg.stt_model,
                    base_url=cfg.stt_base_url,
                ),
            )
        )

    if providers:
        from app.providers.stt.fallback import FallbackTranscriptionProvider

        return FallbackTranscriptionProvider(providers)

    from app.providers.stt.mock import MockTranscriptionProvider

    return MockTranscriptionProvider()


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
            from app.providers.stt.groq import GROQ_DEFAULT_MODEL, GroqWhisperProvider

            return GroqWhisperProvider(
                api_key=cfg.groq_api_key or cfg.stt_api_key,
                model=cfg.groq_stt_model or GROQ_DEFAULT_MODEL,
            )
        case "openrouter":
            from app.providers.stt.openrouter import (
                OPENROUTER_DEFAULT_STT_MODEL,
                OpenRouterSTTProvider,
            )

            return OpenRouterSTTProvider(
                api_key=cfg.openrouter_api_key or cfg.stt_api_key,
                model=cfg.openrouter_stt_model or OPENROUTER_DEFAULT_STT_MODEL,
            )
        case "fallback" | "auto" | "route":
            return _build_fallback_stt(cfg)
        case _:
            from app.providers.stt.mock import MockTranscriptionProvider

            return MockTranscriptionProvider()


def _build_fallback_llm(cfg: Settings) -> BaseIntentParser:
    providers: list[tuple[str, BaseIntentParser]] = []

    if cfg.groq_api_key:
        from app.providers.llm.groq import GroqIntentParser

        providers.append(
            (
                "groq",
                GroqIntentParser(
                    api_key=cfg.groq_api_key,
                    model=cfg.groq_model,
                    base_url=cfg.groq_base_url,
                    raise_on_failure=True,
                ),
            )
        )

    if cfg.openrouter_api_key:
        from app.providers.llm.openrouter import OpenRouterIntentParser

        providers.append(
            (
                "openrouter",
                OpenRouterIntentParser(
                    api_key=cfg.openrouter_api_key,
                    model=cfg.openrouter_model,
                    base_url=cfg.openrouter_base_url,
                    raise_on_failure=True,
                ),
            )
        )

    if providers:
        from app.providers.llm.fallback import FallbackIntentParser

        return FallbackIntentParser(providers)

    from app.providers.llm.mock import MockIntentParser

    return MockIntentParser()


def _build_llm(cfg: Settings) -> BaseIntentParser:
    match cfg.llm_provider.lower():
        case "groq":
            from app.providers.llm.groq import GroqIntentParser

            return GroqIntentParser(
                api_key=cfg.groq_api_key,
                model=cfg.groq_model,
                base_url=cfg.groq_base_url,
            )
        case "openrouter":
            from app.providers.llm.openrouter import OpenRouterIntentParser

            return OpenRouterIntentParser(
                api_key=cfg.openrouter_api_key,
                model=cfg.openrouter_model,
                base_url=cfg.openrouter_base_url,
            )
        case "fallback" | "auto" | "route":
            return _build_fallback_llm(cfg)
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
        recurring_repo = RecurringTaskRepository(session_factory)

        self.task_service = TaskService(task_repo)
        self.reminder_service = ReminderService(reminder_repo)
        self.capture_service = CaptureService(stt, llm, capture_log_repo)
        self.recurring_service: RecurringTaskService | None = (
            RecurringTaskService(recurring_repo, task_repo) if cfg.enable_recurring_tasks else None
        )
        self.action_router = ActionRouter(
            self.task_service, self.reminder_service, self.recurring_service
        )
        self.renderer = Renderer()
        self.user_settings_service = UserSettingsService(user_settings_repo)
        self.list_session_store = ListSessionStore()
        self.scheduler: ReminderScheduler | None = None  # set after bot is created
