from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.domain.models import Base


def create_engine(database_url: str | None = None):
    url = database_url or settings.database_url
    return create_async_engine(url, echo=False, future=True)


def create_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine) -> None:
    """Create all tables. Used on startup and in tests."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db(engine) -> None:
    """Drop all tables. Used in tests."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
