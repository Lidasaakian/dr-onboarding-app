"""Learning streaks (spec learning-streaks)."""

import datetime as dt

from streaks import learning_days, streak

D = lambda s: dt.date.fromisoformat(s)  # noqa: E731
# 2026-11-02 is a Monday


def test_over_a_weekend():
    days = {D("2026-10-29"), D("2026-10-30"), D("2026-11-02")}  # Thu, Fri, Mon
    assert streak(days, D("2026-11-02"))["current"] == 3


def test_not_yet_today():
    days = {D("2026-11-03"), D("2026-11-04")}  # Tue, Wed
    assert streak(days, D("2026-11-05"))["current"] == 2  # Thursday, nothing yet


def test_a_missed_day():
    days = {D("2026-11-02"), D("2026-11-04")}  # Mon, Wed
    assert streak(days, D("2026-11-04"))["current"] == 1


def test_broken_streak_and_best():
    days = {D("2026-10-26"), D("2026-10-27"), D("2026-10-28"), D("2026-10-29"), D("2026-11-04")}
    s = streak(days, D("2026-11-05"))
    assert (s["current"], s["best"]) == (1, 4)


def test_weekend_days_alone_dont_count():
    days = {D("2026-10-31"), D("2026-11-01")}  # Sat, Sun
    assert streak(days, D("2026-11-02")) == {"current": 0, "best": 0, "lastDay": "2026-11-01"}


def test_on_a_weekend_the_friday_streak_holds():
    days = {D("2026-10-29"), D("2026-10-30")}  # Thu, Fri
    assert streak(days, D("2026-11-01"))["current"] == 2  # Sunday


def test_learning_days_from_activity_and_older_ticks():
    tz = dt.timezone.utc
    ts = int(dt.datetime(2026, 10, 27, 12, tzinfo=tz).timestamp() * 1000)
    rec = {"activity": ["2026-11-02"], "paths": {"p": {"done": {"a": ts, "b": 1}, "checks": {"a": {"0": ts}}}},
           "state": {"done": {"x": ts}}}
    assert learning_days(rec, tz) == {D("2026-11-02"), D("2026-10-27")}
