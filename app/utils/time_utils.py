import re
from datetime import UTC, datetime, timedelta

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
    for keyword in sorted(_TIME_KEYWORDS, key=len, reverse=True):
        hour, minute = _TIME_KEYWORDS[keyword]
        if re.search(rf"\b{re.escape(keyword)}\b", text_lower):
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
        # naive dt is treated as UTC, then convert to local
        dt = pytz.utc.localize(dt).astimezone(tz)
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


def format_time_until(target_dt: datetime, now_dt: datetime | None = None) -> str | None:
    """Return human-readable relative time until target_dt (Russian).

    Returns None if target is in the past.
    Accepts naive UTC or tz-aware datetimes.
    """
    now = now_dt or datetime.now(UTC)
    if now.tzinfo is None:
        now = pytz.utc.localize(now)
    if target_dt.tzinfo is None:
        target_dt = pytz.utc.localize(target_dt)

    delta = target_dt - now
    total_minutes = int(delta.total_seconds() // 60)
    if total_minutes <= 0:
        return None

    total_hours = total_minutes // 60
    remaining_minutes = total_minutes % 60

    if total_minutes < 60:
        return f"через {total_minutes} минут"
    elif total_hours < 24:
        if remaining_minutes == 0:
            return f"через {total_hours} часов"
        return f"через {total_hours} ч {remaining_minutes} мин"
    else:
        days = total_hours // 24
        return f"через {days} дней"
