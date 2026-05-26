"""Tests for recurrence calculation utilities (sync)."""

from datetime import datetime

import pytz

from app.utils.recurrence import calculate_next_run, format_recurrence_human_readable


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return pytz.utc.localize(datetime(year, month, day, hour, minute))


TZ = "Europe/Amsterdam"


class TestCalculateNextDaily:
    def test_calculate_next_daily_same_day_before_time(self):
        # It's 08:00 UTC (= 10:00 Amsterdam/CEST), daily at 11:00 → today at 11:00 local
        after = _utc(2026, 5, 18, 8, 0)
        result = calculate_next_run("daily", 1, "11:00", TZ, None, None, after)
        local = result.astimezone(pytz.timezone(TZ))
        assert local.hour == 11
        assert local.minute == 0
        assert local.day == 18

    def test_calculate_next_daily_same_day_after_time(self):
        # It's 10:00 UTC (= 12:00 Amsterdam/CEST), daily at 11:00 → tomorrow at 11:00 local
        after = _utc(2026, 5, 18, 10, 0)
        result = calculate_next_run("daily", 1, "11:00", TZ, None, None, after)
        local = result.astimezone(pytz.timezone(TZ))
        assert local.hour == 11
        assert local.day == 19

    def test_calculate_next_daily_interval_2_advance(self):
        # apply_interval=True (default): advancing after a run — adds full interval
        after = _utc(2026, 5, 18, 8, 0)
        result = calculate_next_run("daily", 2, "11:00", TZ, None, None, after, apply_interval=True)
        local = result.astimezone(pytz.timezone(TZ))
        assert local.day == 19  # today 11:00 + 1 extra day = day 19

    def test_calculate_next_daily_interval_2_first_run(self):
        # apply_interval=False: first run — nearest slot, no offset
        after = _utc(2026, 5, 18, 8, 0)
        result = calculate_next_run(
            "daily", 2, "11:00", TZ, None, None, after, apply_interval=False
        )
        local = result.astimezone(pytz.timezone(TZ))
        assert local.day == 18  # today (time not yet passed)

    def test_calculate_next_daily_interval_2_after_time(self):
        after = _utc(2026, 5, 18, 10, 0)  # already past 11:00 local
        result = calculate_next_run("daily", 2, "11:00", TZ, None, None, after, apply_interval=True)
        local = result.astimezone(pytz.timezone(TZ))
        assert local.day == 20  # tomorrow (19) + 1 extra day = 20


class TestCalculateNextWeekly:
    def test_calculate_next_weekly_friday(self):
        # It's Monday 2026-05-18, next Friday = 2026-05-22
        after = _utc(2026, 5, 18, 8, 0)  # Monday
        result = calculate_next_run("weekly", 1, "17:00", TZ, 4, None, after)  # 4 = Friday
        local = result.astimezone(pytz.timezone(TZ))
        assert local.weekday() == 4  # Friday
        assert local.hour == 17

    def test_calculate_next_weekly_same_day_after_time(self):
        # It's Friday 2026-05-22 at 18:00 UTC (= 20:00 local), rule at 17:00 Friday → next Friday
        after = _utc(2026, 5, 22, 16, 0)  # Friday, past 17:00 local
        result = calculate_next_run("weekly", 1, "17:00", TZ, 4, None, after)
        local = result.astimezone(pytz.timezone(TZ))
        assert local.weekday() == 4
        assert local.day == 29  # next Friday

    def test_calculate_next_weekly_interval_2_advance(self):
        # apply_interval=True: advancing after a run → nearest Friday + 1 extra week
        after = _utc(2026, 5, 18, 8, 0)
        result = calculate_next_run("weekly", 2, "17:00", TZ, 4, None, after, apply_interval=True)
        local = result.astimezone(pytz.timezone(TZ))
        assert local.weekday() == 4
        assert local.day == 29  # 2026-05-22 + 7 days = 2026-05-29

    def test_calculate_next_weekly_interval_2_first_run(self):
        # apply_interval=False: first run → nearest Friday, no extra skip
        after = _utc(2026, 5, 18, 8, 0)
        result = calculate_next_run("weekly", 2, "17:00", TZ, 4, None, after, apply_interval=False)
        local = result.astimezone(pytz.timezone(TZ))
        assert local.weekday() == 4
        assert local.day == 22  # nearest Friday


class TestCalculateNextMonthly:
    def test_calculate_next_monthly(self):
        # It's 2026-05-18, monthly on day 25 → 2026-05-25
        after = _utc(2026, 5, 18, 8, 0)
        result = calculate_next_run("monthly", 1, "10:00", TZ, None, 25, after)
        local = result.astimezone(pytz.timezone(TZ))
        assert local.month == 5
        assert local.day == 25

    def test_calculate_next_monthly_past_day(self):
        # It's 2026-05-26, monthly on day 25 → 2026-06-25
        after = _utc(2026, 5, 26, 8, 0)
        result = calculate_next_run("monthly", 1, "10:00", TZ, None, 25, after)
        local = result.astimezone(pytz.timezone(TZ))
        assert local.month == 6
        assert local.day == 25

    def test_monthly_day_31_february_fallback(self):
        # day_of_month=31, but February only has 28 days → clamp to 28
        after = _utc(2026, 1, 31, 23, 0)
        result = calculate_next_run("monthly", 1, "10:00", TZ, None, 31, after)
        local = result.astimezone(pytz.timezone(TZ))
        assert local.month == 2
        assert local.day == 28  # clamped


class TestFormatHumanReadable:
    def test_format_human_readable_daily(self):
        text = format_recurrence_human_readable("daily", 1, "09:00", None, None)
        assert "день" in text
        assert "09:00" in text

    def test_format_human_readable_daily_interval(self):
        text = format_recurrence_human_readable("daily", 3, "09:00", None, None)
        assert "3" in text

    def test_format_human_readable_weekly(self):
        text = format_recurrence_human_readable("weekly", 1, "17:00", 4, None)
        assert "пятницу" in text
        assert "17:00" in text

    def test_format_human_readable_weekly_interval(self):
        text = format_recurrence_human_readable("weekly", 2, "17:00", 4, None)
        assert "2" in text

    def test_format_human_readable_monthly(self):
        text = format_recurrence_human_readable("monthly", 1, "10:00", None, 15)
        assert "месяц" in text
        assert "15" in text
        assert "10:00" in text
