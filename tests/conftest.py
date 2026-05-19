import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.container import Container
from app.domain.enums import IntentType
from app.domain.schemas import ParsedIntent
from app.providers.llm.mock import MockIntentParser
from app.providers.stt.mock import MockTranscriptionProvider
from app.services.recurring_service import RecurringTaskService
from app.storage.db import drop_db, init_db
from app.storage.repositories import RecurringTaskRepository, TaskRepository

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    e = create_async_engine(TEST_DB_URL, echo=False)
    await init_db(e)
    yield e
    await drop_db(e)
    await e.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def container(session_factory):
    stt = MockTranscriptionProvider()
    llm = MockIntentParser()
    c = Container(session_factory, stt=stt, llm=llm)
    # Stub scheduler
    c.scheduler = _StubScheduler()
    return c


@pytest_asyncio.fixture
async def recurring_service(session_factory):
    repo = RecurringTaskRepository(session_factory)
    task_repo = TaskRepository(session_factory)
    return RecurringTaskService(repo, task_repo)


class _StubScheduler:
    def schedule_reminder(self, *a, **kw):
        pass

    def reschedule_reminder(self, *a, **kw):
        pass

    def cancel_reminder(self, *a, **kw):
        pass


@pytest.fixture
def create_intent_factory():
    """Helper to build ParsedIntent with defaults."""

    def factory(**kwargs) -> ParsedIntent:
        defaults = dict(intent=IntentType.CREATE_REMINDER, confidence=0.9)
        defaults.update(kwargs)
        return ParsedIntent(**defaults)

    return factory
