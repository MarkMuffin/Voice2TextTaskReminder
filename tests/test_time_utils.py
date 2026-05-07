from datetime import datetime

import pytz

from app.utils.time_utils import (
    apply_time_keyword,
    ensure_time_set,
    format_remind_at,
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
