# Design

## Context

See proposal.md. Learner records hold `enrolled[pid]`, per-path state and (from `learner-home-dashboard`) learning
days. `learner_path_view` gives progress, badge and `nowOn` (a label like "Week 2 · Day 1: title"). Every path page
shows a pace line built by `renderPace` in `static/assets/common.js`.

## Decisions

1. **`record.sharing[pid] = true`** when sharing; removing the key turns it off. Leaving or removal doesn't clear it,
   but only enrolled learners are listed, so a learner who comes back shares again as before.
2. **Endpoints:** `PUT <path>/api/sharing {"share": bool}` (enrolled learners only) and `GET <path>/api/peers`
   (enrolled learners only; returns other enrolled learners who share: `name`, `done`, `total`, `streak`,
   `finished`, `section`). `section` is the part of `nowOn` before the colon, so step titles don't leak more than the
   section. Status payloads gain `sharing`.
3. **UI on the pace line,** for enrolled learners: a "Share my progress" checkbox and an "Others on this path (N)" link
   that opens a dialog with the list. One implementation for the built-in and app-made pages.

## Risks / Trade-offs

- [Names are shown] → only for learners who opted in, and only to people enrolled in the same path; the label next
  to the checkbox says exactly what's shared.
