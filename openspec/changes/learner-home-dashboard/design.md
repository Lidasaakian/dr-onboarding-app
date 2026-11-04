# Design

## Context

See proposal.md. Ticks are stored per path as `{step id: timestamp ms}` (`state.done`, plus `state.checks` for
checklist items); the Agentic path keeps its state in `record.state`, others in `record.paths[pid]`. `api/summary`
returns every path with the learner's view (progress, pace, badge, starred steps). Reports live in the `reports`
document with the reporter's `learnerId` and `email`. The home page is `tools/src/hub.html`.

## Decisions

1. **`record.activity`: dates the learner added a tick**, written in `PUT progress` when the new state has a step or
   checklist tick the old one didn't (today's date in the app's time zone; kept unique, last 400). Unticking doesn't
   remove days. For history from before this change, the dates of timestamps in `done` and `checks` are added when
   counting. *Alternative:* only timestamps. Rejected: unticking would erase days.
2. **`streak_of(record, today)`** in a small pure module (`streaks.py`) so the rules are unit-tested without the app:
   working-day walk back from today (or the previous working day when today has none yet), and the longest run over
   all working days.
3. **`api/summary` gains `streak` ({current, best, lastDay}) and `myReports`** (the learner's own reports by
   `learnerId`, or email for old ones; only display fields, never files or other people's data).
4. **Home page tabs** like the Admin page: `#dashboard` (default) and `#paths` switch sections in the page; Admin is a
   link. The dashboard is built from the same `api/summary` call.
5. **Certificates from a link:** a path page opened with `#certificate` opens the certificate dialog once the
   learner's status has loaded and the badge is earned.
6. **Default back link "← Home"** in `DROnb.backLink`; the Admin page's own link reads "← Home" too.
