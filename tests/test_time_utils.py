from datetime import UTC, datetime, timedelta

import pytz

from app.utils.time_utils import (
    apply_time_keyword,
    ensure_time_set,
    format_remind_at,
    format_time_until,
    in_minutes,
    now_in_tz,
    parse_remind_at,
    tomorrow_morning,
)


def test_parse_remind_at_with_timezone():
    iso = "2025-06-01T09:00:00+02:00"
    dt = parse_remind_at(iso)
    assert dt is not None
    assert dt.tzinfo is not None


def test_parse_remind_at_naive_gets_localized():
    iso = "2025-06-01T09:00:00"
    dt = parse_remind_at(iso, tz_name="Europe/Amsterdam")
    assert dt is not None
    assert dt.tzinfo is not None


def test_parse_remind_at_none():
    assert parse_remind_at(None) is None


def test_parse_remind_at_invalid():
    assert parse_remind_at("not-a-date") is None


def test_apply_time_keyword_утром():
    tz = pytz.timezone("Europe/Amsterdam")
    dt = tz.localize(datetime(2025, 6, 1, 0, 0, 0))
    result = apply_time_keyword(dt, "Напомни утром")
    assert result.hour == 9
    assert result.minute == 0


def test_apply_time_keyword_вечером():
    tz = pytz.timezone("Europe/Amsterdam")
    dt = tz.localize(datetime(2025, 6, 1, 0, 0, 0))
    result = apply_time_keyword(dt, "Напомни вечером")
    assert result.hour == 19


def test_apply_time_keyword_после_работы():
    tz = pytz.timezone("Europe/Amsterdam")
    dt = tz.localize(datetime(2025, 6, 1, 0, 0, 0))
    result = apply_time_keyword(dt, "после работы")
    assert result.hour == 18
    assert result.minute == 30


def test_apply_time_keyword_no_match():
    tz = pytz.timezone("Europe/Amsterdam")
    dt = tz.localize(datetime(2025, 6, 1, 15, 30, 0))
    result = apply_time_keyword(dt, "без ключевых слов")
    assert result.hour == 15
    assert result.minute == 30


def test_ensure_time_set_midnight():
    tz = pytz.timezone("Europe/Amsterdam")
    dt = tz.localize(datetime(2025, 6, 1, 0, 0, 0))
    result = ensure_time_set(dt)
    assert result.hour == 9
    assert result.minute == 0


def test_ensure_time_set_already_has_time():
    tz = pytz.timezone("Europe/Amsterdam")
    dt = tz.localize(datetime(2025, 6, 1, 14, 30, 0))
    result = ensure_time_set(dt)
    assert result.hour == 14
    assert result.minute == 30


def test_tomorrow_morning():
    result = tomorrow_morning()
    now = now_in_tz()
    assert result.date() > now.date()
    assert result.hour == 9
    assert result.minute == 0


def test_in_minutes():
    result = in_minutes(30)
    now = now_in_tz()
    diff = (result - now).total_seconds()
    assert 25 * 60 <= diff <= 35 * 60


def test_format_remind_at_tomorrow():
    tz = pytz.timezone("Europe/Amsterdam")
    from datetime import timedelta

    tomorrow = datetime.now(tz).date() + timedelta(days=1)
    dt = tz.localize(datetime(tomorrow.year, tomorrow.month, tomorrow.day, 9, 0))
    text = format_remind_at(dt, "Europe/Amsterdam")
    assert "завтра" in text
    assert "09:00" in text


def test_format_remind_at_today():
    tz = pytz.timezone("Europe/Amsterdam")
    today = datetime.now(tz)
    dt = tz.localize(datetime(today.year, today.month, today.day, 14, 0))
    text = format_remind_at(dt, "Europe/Amsterdam")
    assert "сегодня" in text


def test_now_in_tz():
    dt = now_in_tz("Europe/Amsterdam")
    assert dt.tzinfo is not None


# ─── format_time_until ────────────────────────────────────────────────────────


def test_format_time_until_in_past():
    now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
    target = datetime(2025, 6, 1, 11, 0, 0, tzinfo=UTC)
    assert format_time_until(target, now_dt=now) is None


def test_format_time_until_30_minutes():
    now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
    target = now + timedelta(minutes=30)
    result = format_time_until(target, now_dt=now)
    assert result == "через 30 минут"


def test_format_time_until_2h_15min():
    now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
    target = now + timedelta(hours=2, minutes=15)
    result = format_time_until(target, now_dt=now)
    assert result == "через 2 ч 15 мин"


def test_format_time_until_exact_hours():
    now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
    target = now + timedelta(hours=3)
    result = format_time_until(target, now_dt=now)
    assert result == "через 3 часов"


def test_format_time_until_3_days():
    now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
    target = now + timedelta(days=3)
    result = format_time_until(target, now_dt=now)
    assert result == "через 3 дней"


def test_format_time_until_naive_utc_target():
    """Naive datetime is treated as UTC."""
    now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
    target = datetime(2025, 6, 1, 14, 0, 0)  # naive — 2 hours ahead in UTC
    result = format_time_until(target, now_dt=now)
    assert result == "через 2 часов"


def test_format_remind_at_naive_utc_bug():
    """format_remind_at with naive UTC should show local time, not treat as local."""
    # UTC midnight = 02:00 Amsterdam (CEST, UTC+2)
    dt_utc_naive = datetime(2025, 6, 1, 0, 0, 0)  # naive UTC
    text = format_remind_at(dt_utc_naive, "Europe/Amsterdam")
    assert "02:00" in text
