# Design

## Context

See proposal.md. A path made in the app has `status` in its document; `activate_content()` builds `PATHS` (what
learners can open) from published documents only. The hub (`api/summary`), enrollment, progress, team views and
certificate verification all go through `PATHS`. Admin → Content rows come from `path_row`.

## Decisions

1. **`status: "archived"`, still in `PATHS`.** `activate_content()` loads published and archived documents, and marks
   the model `archived`. Enrolled learners keep their page, progress and certificates; every learner-facing rule then
   checks `p.archived`. *Alternative:* drop archived paths from `PATHS`. Rejected: enrolled learners would lose the
   page and certificate lookups would need a second source.
2. **Rules on the server.** `api/summary` skips archived paths the learner isn't enrolled in; `PUT enroll` refuses
   enrolling (leaving and admin removal still work); `PUT progress` refuses (409); the dashboard skips archived
   paths; team-summary marks them `archived`. `path_doc(editable=True)` refuses archived documents; delete refuses
   published and archived.
3. **Endpoints:** `POST api/admin/paths/{pid}/archive` (published → archived) and `/restore` (archived → published),
   for owners and admins (`require_manage`), then `activate_content()`.
4. **UI.** Admin → Content: Archive on published app-made rows, Restore on archived rows (with a confirmation), an
   "Archived" pill, no Edit while archived. Path page: a note under the title, checkboxes disabled, and the pace line
   says new enrollments are closed instead of offering Enroll (`status.archived` from `learner_path_view`). Hub cards
   of archived paths show "Archived".

## Risks / Trade-offs

- [A learner mid-path is frozen when the path is archived] → that's the chosen behavior; Restore unfreezes it, and
  the confirmation says enrolled learners can't tick any more.
