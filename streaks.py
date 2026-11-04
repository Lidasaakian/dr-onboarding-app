"""Learning streaks: consecutive working days (Monday to Friday) on which a learner ticked something.

Saturdays and Sundays neither count nor break a streak. Today only breaks the streak once it's over: a learner who
hasn't ticked anything yet today keeps the streak that ended on the previous working day.
"""

from __future__ import annotations

import datetime as dt


def _working(d: dt.date) -> bool:
    return d.weekday() < 5


def _prev_working(d: dt.date) -> dt.date:
    d -= dt.timedelta(days=1)
    while not _working(d):
        d -= dt.timedelta(days=1)
    return d


def streak(days: set[dt.date], today: dt.date) -> dict:
    """{"current", "best", "lastDay"} for a set of learning days."""
    work = {d for d in days if _working(d) and d <= today}
    if not work:
        return {"current": 0, "best": 0, "lastDay": max(days).isoformat() if days else None}
    # current: walk back over working days from today (or the last working day before it if today has nothing yet)
    d = today if _working(today) else _prev_working(today)
    if d not in work and d == today:
        d = _prev_working(today)
    current = 0
    while d in work:
        current += 1
        d = _prev_working(d)
    # best: longest run of consecutive working days
    best, run, prev = 0, 0, None
    for d in sorted(work):
        run = run + 1 if prev is not None and _prev_working(d) == prev else 1
        best = max(best, run)
        prev = d
    return {"current": current, "best": max(best, current), "lastDay": max(days).isoformat()}


def learning_days(record: dict | None, tz) -> set[dt.date]:
    """Days a learner learned: the recorded activity dates plus the days of every tick timestamp (steps and checklist
    items) in every path, so progress saved before activity was recorded still counts."""
    record = record or {}
    out: set[dt.date] = set()
    for s in record.get("activity") or []:
        try:
            out.add(dt.date.fromisoformat(s))
        except (TypeError, ValueError):
            pass
    states = list((record.get("paths") or {}).values()) + [record.get("state") or {}]
    for st in states:
        if not isinstance(st, dict):
            continue
        stamps = list((st.get("done") or {}).values())
        for m in (st.get("checks") or {}).values():
            if isinstance(m, dict):
                stamps += list(m.values())
        for ts in stamps:
            if isinstance(ts, (int, float)) and ts > 10**11:  # ms timestamps; older saves used true/1
                out.add(dt.datetime.fromtimestamp(ts / 1000, tz).date())
    return out
