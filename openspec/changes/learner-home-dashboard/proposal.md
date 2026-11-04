# Proposal

## Why

The home page is a catalog of learning paths. A learner who comes back can't see at a glance what they're working
on, what they've finished, which steps they starred, what happened to the problems they reported, or whether they're
keeping a learning habit.

## What Changes

- The home page becomes the learner's **My dashboard**: streak, paths completed, certificates earned, the paths
  they're enrolled in with progress and where they left off, their starred steps (moved here from the bottom of the
  page), and the problems they reported with their status.
- **Streaks:** consecutive working days on which the learner ticked something (a step or a checklist item) in any
  path; weekends neither count nor break a streak. The dashboard shows the current and best streak.
- The home page gets tabs: **My dashboard** (default), **Learning paths** (the catalog of path cards) and **Admin**
  (a link, for admins and authors only).
- A path's certificate can be opened straight from the dashboard.

## Capabilities

### New Capabilities
- `learner-dashboard`: the learner's home page and what it shows.
- `learning-streaks`: how learning days and streaks are recorded and counted.

### Modified Capabilities
- None (no specs have been archived into `openspec/specs/` yet).

## Impact

- `app.py`: activity days recorded on progress saves; `api/summary` adds the streak and the learner's own reports.
- `tools/src/hub.html` (home page) rebuilt with tabs; `static/assets/common.js`: open the certificate from a link,
  default back link to the home page. Built `static/` pages are regenerated.
- Progress records gain an `activity` list of dates.
