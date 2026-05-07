import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.container import Container
from app.domain.enums import IntentType
from app.domain.schemas import ParsedIntent
from app.providers.llm.mock import MockIntentParser
from app.providers.stt.mock import MockTranscriptionProvider
from app.storage.db import init_db, drop_db

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


class _StubScheduler:
    def schedule_reminder(self, *a, **kw): pass
    def reschedule_reminder(self, *a, **kw): pass
    def cancel_reminder(self, *a, **kw): pass


@pytest.fixture
def create_intent_factory():
    """Helper to build ParsedIntent with defaults."""
    def factory(**kwargs) -> ParsedIntent:
        defaults = dict(intent=IntentType.CREATE_REMINDER, confidence=0.9)
        defaults.update(kwargs)
        return ParsedIntent(**defaults)
    return factory
