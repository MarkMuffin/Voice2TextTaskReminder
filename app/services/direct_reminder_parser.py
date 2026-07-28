"""Fast, literal parsing for simple reminder commands.

This path deliberately avoids an LLM: for a clear "напомни" command we
preserve the user's wording and only remove the command and time fragments.
"""

import re
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import cast

import pytz

from app.domain.enums import IntentType
from app.domain.schemas import ParsedIntent
from app.utils.time_utils import _TIME_KEYWORDS

_REMINDER_RE = re.compile(r"\bнапомни(?:ть)?(?:-ка)?\b", re.IGNORECASE)
_RECURRING_RE = re.compile(r"\b(?:кажд(?:ый|ую|ое)|ежедневно|еженедельно|раз\s+в)\b", re.IGNORECASE)
_CLOCK_RE = re.compile(r"\b(?:в\s+)?([01]?\d|2[0-3])(?::([0-5]\d))?\b", re.IGNORECASE)
_IN_MINUTES_RE = re.compile(r"\bчерез\s+(\d+)\s+(?:минут(?:у|ы)?|мин)\b", re.IGNORECASE)
_IN_HOURS_RE = re.compile(r"\bчерез\s+(\d+)\s+(?:час(?:а|ов)?|ч)\b", re.IGNORECASE)
_COMPOUND_DURATION_RE = re.compile(
    r"\bчерез\s+(\d+)\s+(?:час(?:а|ов)?|ч)\s+(?:и\s+)?(\d+)\s+(?:минут(?:у|ы)?|мин)\b",
    re.IGNORECASE,
)
_CLOCK_PERIOD_SUFFIXES = {"утра", "дня", "вечера", "ночи"}

_WEEKDAYS = {
    "понедельник": 0,
    "понедельника": 0,
    "вторник": 1,
    "вторника": 1,
    "среду": 2,
    "среда": 2,
    "среды": 2,
    "четверг": 3,
    "четверга": 3,
    "пятницу": 4,
    "пятница": 4,
    "пятницы": 4,
    "субботу": 5,
    "суббота": 5,
    "субботы": 5,
    "воскресенье": 6,
    "воскресенья": 6,
}


class DirectReminderParser:
    """Parse unambiguous one-off Russian reminder commands without an LLM."""

    def __init__(self, now: Callable[[pytz.BaseTzInfo], datetime] | None = None) -> None:
        self._now = now or datetime.now

    def parse(self, text: str, timezone: str) -> ParsedIntent | None:
        """Return a literal reminder intent, or None when the LLM should handle it."""
        if not _REMINDER_RE.search(text) or _RECURRING_RE.search(text):
            return None

        tz = pytz.timezone(timezone)
        now = self._now(tz)
        if now.tzinfo is None:
            now = tz.localize(now)

        remind_at, fragments = self._extract_datetime(text, now, tz)
        title = self._extract_title(text, fragments)
        # A missing title needs an answer from the user/LLM. A missing time does
        # not: create an ordinary task without a scheduled reminder instead.
        if not title:
            return None

        return ParsedIntent(
            intent=IntentType.CREATE_REMINDER,
            title=title,
            remind_at=remind_at.isoformat() if remind_at else None,
            timezone=timezone,
            confidence=1.0,
        )

    def _extract_datetime(
        self, text: str, now: datetime, tz: pytz.BaseTzInfo
    ) -> tuple[datetime | None, list[str]]:
        lower = text.lower()
        fragments: list[str] = []

        relative = self._relative_datetime(lower, now, tz)
        has_relative_duration = bool(
            _COMPOUND_DURATION_RE.search(lower)
            or _IN_MINUTES_RE.search(lower)
            or _IN_HOURS_RE.search(lower)
        )
        has_calendar_date = relative is not None and not has_relative_duration
        if relative is not None:
            dt, phrase = relative
            fragments.append(phrase)
        else:
            dt = None

        clock = _CLOCK_RE.search(lower)
        has_clock = clock is not None and self._is_clock_match(clock)
        if has_clock:
            assert clock is not None
            hour, minute = int(clock.group(1)), int(clock.group(2) or 0)
            if dt is None:
                dt = self._at_local_time(tz, now.date(), hour, minute)
                if dt <= now:
                    dt = self._at_local_time(tz, now.date() + timedelta(days=1), hour, minute)
            else:
                dt = self._at_local_time(tz, dt.date(), hour, minute)
            fragments.append(clock.group(0))

        matched_time_keyword = False
        for phrase, (hour, minute) in _TIME_KEYWORDS.items():
            if re.search(rf"\b{re.escape(phrase)}\b", lower):
                matched_time_keyword = True
                if dt is None:
                    dt = self._at_local_time(tz, now.date(), hour, minute)
                    if dt <= now:
                        dt = self._at_local_time(tz, now.date() + timedelta(days=1), hour, minute)
                elif not has_clock:
                    dt = self._at_local_time(tz, dt.date(), hour, minute)
                fragments.append(phrase)
                break

        period_suffix = self._find_clock_period_suffix(lower) if has_clock else None
        if period_suffix:
            assert clock is not None and dt is not None
            clock_hour = int(clock.group(1))
            hour_with_period = self._hour_with_period(clock_hour, period_suffix)
            target_date = dt.date() if has_calendar_date else now.date()
            dt = self._at_local_time(tz, target_date, hour_with_period, int(clock.group(2) or 0))
            if not has_calendar_date and dt <= now:
                dt = self._at_local_time(
                    tz,
                    now.date() + timedelta(days=1),
                    hour_with_period,
                    int(clock.group(2) or 0),
                )
            fragments.append(period_suffix)

        if (
            dt is not None
            and not has_clock
            and not has_relative_duration
            and not matched_time_keyword
        ):
            dt = self._at_local_time(tz, dt.date(), 9, 0)
        return dt, fragments

    def _relative_datetime(
        self, lower: str, now: datetime, tz: pytz.BaseTzInfo
    ) -> tuple[datetime, str] | None:
        compound_duration = _COMPOUND_DURATION_RE.search(lower)
        if compound_duration:
            hours, minutes = int(compound_duration.group(1)), int(compound_duration.group(2))
            return (
                tz.normalize(now + timedelta(hours=hours, minutes=minutes)),
                compound_duration.group(0),
            )

        for regex, unit in ((_IN_MINUTES_RE, "minutes"), (_IN_HOURS_RE, "hours")):
            match = regex.search(lower)
            if match:
                return tz.normalize(now + timedelta(**{unit: int(match.group(1))})), match.group(0)

        if "послезавтра" in lower:
            return self._at_local_time(
                tz, now.date() + timedelta(days=2), now.hour, now.minute
            ), "послезавтра"
        if "завтра" in lower:
            return self._at_local_time(
                tz, now.date() + timedelta(days=1), now.hour, now.minute
            ), "завтра"
        if "сегодня" in lower:
            return now, "сегодня"
        if "на выходных" in lower or "в выходные" in lower:
            days = (5 - now.weekday()) % 7
            if days == 0:
                days = 7
            phrase = "на выходных" if "на выходных" in lower else "в выходные"
            return self._at_local_time(
                tz, now.date() + timedelta(days=days), now.hour, now.minute
            ), phrase

        for word, weekday in _WEEKDAYS.items():
            match = re.search(rf"\b(?:в\s+(?:следующ(?:ий|ую)\s+)?)?{word}\b", lower)
            if not match:
                continue
            days = (weekday - now.weekday()) % 7
            if "следующ" in match.group(0):
                days += 7
            elif days == 0:
                days = 7
            return self._at_local_time(
                tz, now.date() + timedelta(days=days), now.hour, now.minute
            ), match.group(0)
        return None

    @staticmethod
    def _find_clock_period_suffix(text: str) -> str | None:
        for suffix in _CLOCK_PERIOD_SUFFIXES:
            if re.search(rf"\b{re.escape(suffix)}\b", text):
                return suffix
        return None

    @staticmethod
    def _hour_with_period(hour: int, period: str) -> int:
        """Convert Russian 12-hour suffixes such as ``вечера`` to a 24-hour hour."""
        if period == "вечера":
            return hour + 12 if hour < 12 else hour
        if period == "ночи":
            return 0 if hour == 12 else hour
        if period == "дня":
            return hour + 12 if hour < 12 else hour
        return 0 if hour == 12 else hour  # утра

    @staticmethod
    def _at_local_time(tz: pytz.BaseTzInfo, day: date, hour: int, minute: int) -> datetime:
        """Build a wall-clock time in ``tz`` without retaining a stale DST offset."""
        local_naive = datetime.combine(day, time(hour, minute))
        try:
            return cast(datetime, tz.localize(local_naive, is_dst=None))
        except pytz.AmbiguousTimeError:
            # For the repeated hour at the end of DST, choose standard time.
            return cast(datetime, tz.localize(local_naive, is_dst=False))
        except pytz.NonExistentTimeError:
            # A requested wall-clock time in the skipped spring-forward hour
            # becomes the next valid local time.
            return cast(datetime, tz.normalize(tz.localize(local_naive, is_dst=False)))

    @staticmethod
    def _is_clock_match(match: re.Match[str]) -> bool:
        """Bare one-digit numbers are only clocks when introduced by 'в'."""
        return match.group(2) is not None or match.group(0).lower().startswith("в ")

    @staticmethod
    def _extract_title(text: str, fragments: list[str]) -> str:
        title = _REMINDER_RE.sub(" ", text)
        for fragment in fragments:
            title = re.sub(re.escape(fragment), " ", title, flags=re.IGNORECASE)
        title = re.sub(r"\s+", " ", title).strip(" ,.;:!?")
        title = re.sub(r"^(?:мне\s+|пожалуйста\s+)", "", title, flags=re.IGNORECASE)
        return title.strip(" ,.;:!?")
