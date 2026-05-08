import pytest
import pytest_asyncio

from app.config import settings
from app.services.user_settings_service import UserSettingsService, find_timezone_by_city
from app.storage.repositories import UserSettingsRepository


@pytest_asyncio.fixture
async def user_settings_service(session_factory):
    repo = UserSettingsRepository(session_factory)
    return UserSettingsService(repo)


@pytest.mark.asyncio
async def test_get_user_timezone_default(user_settings_service):
    """Returns default_timezone when no setting saved for user."""
    tz = await user_settings_service.get_user_timezone("unknown_user_999")
    assert tz == settings.default_timezone


@pytest.mark.asyncio
async def test_set_and_get_timezone(user_settings_service):
    """Can save and retrieve a timezone."""
    await user_settings_service.set_user_timezone("user_tz_1", "Europe/Moscow")
    tz = await user_settings_service.get_user_timezone("user_tz_1")
    assert tz == "Europe/Moscow"


@pytest.mark.asyncio
async def test_set_timezone_updates_existing(user_settings_service):
    """Upsert updates an existing timezone."""
    await user_settings_service.set_user_timezone("user_tz_2", "Europe/London")
    await user_settings_service.set_user_timezone("user_tz_2", "Asia/Tokyo")
    tz = await user_settings_service.get_user_timezone("user_tz_2")
    assert tz == "Asia/Tokyo"


@pytest.mark.asyncio
async def test_set_invalid_timezone(user_settings_service):
    """Raises ValueError when neither IANA name nor city is recognized."""
    with pytest.raises(ValueError):
        await user_settings_service.set_user_timezone("user_tz_3", "NotACityOrZone")


@pytest.mark.asyncio
async def test_set_timezone_by_city_name(user_settings_service):
    """City name resolves to correct IANA timezone."""
    resolved = await user_settings_service.set_user_timezone("user_tz_4", "Moscow")
    tz = await user_settings_service.get_user_timezone("user_tz_4")
    assert tz == "Europe/Moscow"
    assert resolved == "Europe/Moscow"


@pytest.mark.asyncio
async def test_set_timezone_by_city_name_spaces(user_settings_service):
    """City name with spaces resolves correctly."""
    resolved = await user_settings_service.set_user_timezone("user_tz_5", "New York")
    assert resolved == "America/New_York"


# ─── find_timezone_by_city unit tests ─────────────────────────────────────────


def test_find_timezone_moscow():
    assert find_timezone_by_city("Moscow") == "Europe/Moscow"


def test_find_timezone_london():
    assert find_timezone_by_city("London") == "Europe/London"


def test_find_timezone_tokyo():
    assert find_timezone_by_city("Tokyo") == "Asia/Tokyo"


def test_find_timezone_new_york():
    assert find_timezone_by_city("New York") == "America/New_York"


def test_find_timezone_case_insensitive():
    assert find_timezone_by_city("moscow") == "Europe/Moscow"


def test_find_timezone_unknown():
    assert find_timezone_by_city("NotACity") is None
