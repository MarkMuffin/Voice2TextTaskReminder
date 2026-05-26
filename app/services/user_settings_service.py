import zoneinfo

from app.config import settings
from app.storage.repositories import UserSettingsRepository

# Preferred region order when multiple timezones match the same city name
_REGION_ORDER = [
    "Europe",
    "America",
    "Asia",
    "Pacific",
    "Atlantic",
    "Indian",
    "Africa",
    "Arctic",
]


def find_timezone_by_city(city: str) -> str | None:
    """Find IANA timezone by city name (case-insensitive, spaces=underscores).

    Returns the best-matching IANA timezone string, or None if not found.
    Example: "Moscow" -> "Europe/Moscow", "New York" -> "America/New_York"
    """
    normalized = city.strip().replace(" ", "_").lower()
    all_tzs = zoneinfo.available_timezones()

    matches = [tz for tz in all_tzs if tz.split("/")[-1].lower() == normalized]

    if not matches:
        return None

    def sort_key(tz: str) -> int:
        region = tz.split("/")[0]
        try:
            return _REGION_ORDER.index(region)
        except ValueError:
            return len(_REGION_ORDER)

    matches.sort(key=sort_key)
    return matches[0]


class UserSettingsService:
    def __init__(self, repo: UserSettingsRepository) -> None:
        self._repo = repo

    async def get_user_timezone(self, user_id: str) -> str:
        """Return user's timezone, fallback to settings.default_timezone."""
        obj = await self._repo.get(user_id)
        if obj is not None:
            return obj.timezone
        return settings.default_timezone

    async def set_user_timezone(self, user_id: str, tz_input: str) -> str:
        """Accept IANA name or English city name. Returns the resolved IANA timezone.

        Raises ValueError if the input cannot be resolved.
        """
        # Try as a direct IANA timezone name first
        try:
            zoneinfo.ZoneInfo(tz_input)
            resolved = tz_input
        except (zoneinfo.ZoneInfoNotFoundError, KeyError):
            # Fall back to city name search
            city_tz = find_timezone_by_city(tz_input)
            if city_tz is None:
                raise ValueError(f"Cannot resolve timezone for: {tz_input!r}") from None
            resolved = city_tz

        await self._repo.upsert(user_id, resolved)
        return resolved
