# Proposal

## Why

Learners going through the same path have no way to see how others are doing. Seeing a colleague's progress and
streak motivates, and helps people find someone at the same point to compare notes with, but it has to be each
learner's own choice.

## What Changes

- On every path page, enrolled learners get **Share my progress with others on this path** (off by default). They can
  switch it off again at any time.
- Enrolled learners see **Others on this path**: the learners who chose to share, with their progress, current
  streak, whether they finished, and the section they're in.
- Only learners enrolled in the path see the list, and it never shows emails or anything not listed above.

## Capabilities

### New Capabilities
- `stats-sharing`: how learners opt in to sharing their stats for a path and what others enrolled in it see.

### Modified Capabilities
- None (no specs have been archived into `openspec/specs/` yet).

## Impact

- `app.py`: a sharing flag per learner and path; endpoints to set it and to list who shares; the status payload says
  whether the learner shares.
- `static/assets/common.js`: the switch and the list on the pace line of every path page.
- Uses the streaks from `learner-home-dashboard`.
