# Design

## Context

See proposal.md. Enrollment is `record.enrolled[pid]`; an admin removal stores `{"removed": true, "at", "by"}`
through `PUT <path>/api/enroll` with `{"learner", "remove": true}` (managers only). `is_enrolled()` treats `removed`
as not enrolled, so every team view already drops removed learners, and ticks stay in the record. Saving progress
with ticks re-enrolls a removed learner (`api_put_progress`). The pace line on every path page comes from
`renderPace` in `static/assets/common.js`.

## Decisions

1. **Leaving reuses the removal marker** with `"left": true` added: `{"removed": true, "left": true, "at", "by"}`.
   Everything that ignores removed learners ignores leavers for free, and enrolling again overwrites the marker as it
   does after a removal. *Alternative:* a separate `left` map. Rejected: every view would need a second check.
2. **Same endpoint, `{"leave": true}`, for the learner themself only.** It refuses (400) when they aren't enrolled.
3. **The action lives in `renderPace`,** next to "Change", so built-in and app-made paths get it at once. It uses the
   page's own modal for the confirmation.
4. **"Left by themselves" in `api/team-summary`:** a `left` list of `{name, email, path, at}` for the managed paths,
   shown under the Team progress table in Admin.

## Risks / Trade-offs

- [A learner who left and ticks a step is re-enrolled silently] → the page asks them to enroll before saving a tick,
  as for anyone not enrolled; the server's re-enroll on save stays as a fallback.
