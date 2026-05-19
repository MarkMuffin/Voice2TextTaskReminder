import calendar
from datetime import datetime, timedelta
from typing import cast

import pytz
import pytz.exceptions

from app.domain.enums import RecurrenceType

_WEEKDAY_RU = {
    0: "понедельник",
    1: "вторник",
    2: "среду",
    3: "четверг",
    4: "пятницу",
    5: "субботу",
    6: "воскресенье",
}


def _clamp_day(year: int, month: int, day: int) -> int:
    return min(day, calendar.monthrange(year, month)[1])


def _localize_safe(tz: pytz.BaseTzInfo, naive_dt: datetime) -> datetime:
    """Localize a naive datetime, handling DST transitions explicitly."""
    try:
        result: datetime = cast(datetime, tz.localize(naive_dt, is_dst=None))
    except pytz.exceptions.AmbiguousTimeError:
        # Clocks go back: take the first (summer-time) occurrence
        result = cast(datetime, tz.localize(naive_dt, is_dst=True))
    except pytz.exceptions.NonExistentTimeError:
        # Clocks go forward: move past the gap
        result = cast(datetime, tz.localize(naive_dt + timedelta(hours=1), is_dst=False))
    return result


def calculate_next_run(
    recurrence_type: str,
    interval: int,
    time_of_day: str,
    timezone: str,
    day_of_week: int | None,
    day_of_month: int | None,
    after_utc: datetime,
    apply_interval: bool = True,
) -> datetime:
    """
    Calculate next run time (UTC-aware) after after_utc.

    apply_interval=False: find the nearest natural occurrence (used for the
    first run after create/resume so interval doesn't delay the initial slot).
    apply_interval=True (default): advance by the full interval (used when
    advancing after a completed run).
    """
    """Calculate next run time (UTC-aware) after after_utc."""
    tz = pytz.timezone(timezone)
    after_local = after_utc.astimezone(tz)

    hour, minute = (int(p) for p in time_of_day.split(":"))

    if recurrence_type == RecurrenceType.DAILY:
        candidate = after_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= after_local:
            candidate += timedelta(days=1)
        if apply_interval:
            candidate += timedelta(days=(interval - 1))
        return cast(
            datetime,
            _localize_safe(tz, candidate.replace(tzinfo=None)).astimezone(pytz.utc),
        )

    elif recurrence_type == RecurrenceType.WEEKLY:
        target_dow = day_of_week if day_of_week is not None else 0
        candidate = after_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        days_ahead = (target_dow - after_local.weekday()) % 7
        if days_ahead == 0 and candidate <= after_local:
            days_ahead = 7
        candidate += timedelta(days=days_ahead)
        if apply_interval:
            candidate += timedelta(weeks=(interval - 1))
        return cast(
            datetime,
            _localize_safe(tz, candidate.replace(tzinfo=None)).astimezone(pytz.utc),
        )

    elif recurrence_type == RecurrenceType.MONTHLY:
        target_day = day_of_month if day_of_month is not None else 1
        year = after_local.year
        month = after_local.month
        day = _clamp_day(year, month, target_day)
        candidate = after_local.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= after_local:
            month += 1
            if month > 12:
                month = 1
                year += 1
            day = _clamp_day(year, month, target_day)
            candidate = after_local.replace(
                year=year,
                month=month,
                day=day,
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )
        if apply_interval:
            for _ in range(interval - 1):
                month += 1
                if month > 12:
                    month = 1
                    year += 1
                day = _clamp_day(year, month, target_day)
                candidate = candidate.replace(year=year, month=month, day=day)
        return cast(
            datetime,
            _localize_safe(tz, candidate.replace(tzinfo=None)).astimezone(pytz.utc),
        )

    else:
        raise ValueError(f"Unknown recurrence_type: {recurrence_type}")


def format_recurrence_human_readable(
    recurrence_type: str,
    interval: int,
    time_of_day: str,
    day_of_week: int | None,
    day_of_month: int | None,
) -> str:
    """Return Russian human-readable schedule string."""
    if recurrence_type == RecurrenceType.DAILY:
        if interval == 1:
            return f"каждый день в {time_of_day}"
        else:
            return f"каждые {interval} дня в {time_of_day}"

    elif recurrence_type == RecurrenceType.WEEKLY:
        dow_name = _WEEKDAY_RU.get(day_of_week or 0, "понедельник")
        if interval == 1:
            return f"каждую {dow_name} в {time_of_day}"
        else:
            return f"каждые {interval} недели по {dow_name} в {time_of_day}"

    elif recurrence_type == RecurrenceType.MONTHLY:
        day = day_of_month or 1
        if interval == 1:
            return f"каждый месяц {day}-го в {time_of_day}"
        else:
            return f"каждые {interval} месяца {day}-го в {time_of_day}"

    return f"{recurrence_type} в {time_of_day}"
