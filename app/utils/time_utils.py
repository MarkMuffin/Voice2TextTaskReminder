from datetime import datetime, timedelta

import pytz

from app.config import settings

# Natural language time mappings (Russian)
_TIME_KEYWORDS: dict[str, tuple[int, int]] = {
    "утром": (9, 0),
    "утро": (9, 0),
    "днём": (14, 0),
    "днем": (14, 0),
    "после обеда": (14, 0),
    "вечером": (19, 0),
    "вечер": (19, 0),
    "после работы": (18, 30),
    "ночью": (22, 0),
    "ночь": (22, 0),
}

_DEFAULT_TIME = (9, 0)


def get_default_timezone() -> pytz.BaseTzInfo:
    return pytz.timezone(settings.default_timezone)


def now_in_tz(tz_name: str | None = None) -> datetime:
    tz = pytz.timezone(tz_name or settings.default_timezone)
    return datetime.now(tz)


def parse_remind_at(iso_str: str | None, tz_name: str | None = None) -> datetime | None:
    """Parse ISO datetime string with timezone normalization."""
    if not iso_str:
        return None
    tz = pytz.timezone(tz_name or settings.default_timezone)
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = tz.localize(dt)
        return dt
    except ValueError:
        return None


def apply_time_keyword(dt: datetime, text: str, tz_name: str | None = None) -> datetime:
    """
    If text contains a time keyword, override time component.
    Returns dt unchanged if no keyword matched.
    """
    text_lower = text.lower()
    for keyword, (hour, minute) in _TIME_KEYWORDS.items():
        if keyword in text_lower:
            return dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return dt


def ensure_time_set(dt: datetime, tz_name: str | None = None) -> datetime:
    """If dt has midnight time (00:00:00), apply default time 09:00."""
    if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
        return dt.replace(hour=_DEFAULT_TIME[0], minute=_DEFAULT_TIME[1])
    return dt


def tomorrow_morning(tz_name: str | None = None) -> datetime:
    now = now_in_tz(tz_name)
    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(hour=_DEFAULT_TIME[0], minute=_DEFAULT_TIME[1], second=0, microsecond=0)


def in_minutes(minutes: int, tz_name: str | None = None) -> datetime:
    return now_in_tz(tz_name) + timedelta(minutes=minutes)


def to_utc_naive(dt: datetime) -> datetime:
    """Convert any datetime to naive UTC — safe for SQLite storage."""
    if dt.tzinfo is None:
        return dt  # assume already UTC naive
    return dt.astimezone(pytz.utc).replace(tzinfo=None)


def format_remind_at(dt: datetime, tz_name: str | None = None) -> str:
    """Format datetime for human-readable Russian output."""
    tz = pytz.timezone(tz_name or settings.default_timezone)
    if dt.tzinfo is None:
        dt = tz.localize(dt)
    else:
        dt = dt.astimezone(tz)

    now = now_in_tz(tz_name)
    today = now.date()
    tomorrow = today + timedelta(days=1)

    if dt.date() == today:
        return f"сегодня в {dt.strftime('%H:%M')}"
    elif dt.date() == tomorrow:
        return f"завтра в {dt.strftime('%H:%M')}"
    else:
        return dt.strftime("%-d %B в %H:%M")
