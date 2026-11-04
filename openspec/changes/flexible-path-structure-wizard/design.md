# Design

## Context

See proposal.md for why. Today a path's structure is three independent fields in its content
(`custom_paths.py`): `pace` ("weeks" | "days", anything else is reset to "weeks"), `level` (the top-level label) and
`useDays` (a second level always called "Day"). Section labels are built as `<level> <n>` in three places that must
stay in step: `where_label` in `custom_paths.py`, `gLabel`/`where` in `tools/src/path.html`, and the scope labels in
`generate.edit_draft`. The schedule comes from `custom_paths.model()`, which turns content into a `PathModel` with
`unit_name` "Week" or "Day"; `PathModel.pace()` in `paths.py` compares the learner's current unit with the unit of
their first open required step. The dashboard counts `pace.status` values (`app.py`, "on_track", "behind", …).

Creation lives in `tools/src/admin.html` (`chooseView`, `buildView`, `sourceView`, `foundView`, `generate`), keeps its
state in a page variable (`SRC`), and polls in-memory jobs (`generate.JOBS`, kept an hour). The generate job saves the
draft only when it finishes, via `new_path` + `save_path` in `app.py`. Uploaded files sit in the container's temp
folder for up to 3 hours. The app runs as a single instance and keeps paths in `CUSTOM`, backed by
`docs/path-<id>.json` in the Files item.

## Goals / Non-Goals

**Goals:**
- One structure model that every label, the schedule, the editor, the LLM and the .xlsx all read from.
- Old stored paths load without a batch migration, and the code can be rolled back without corrupting them.
- Creation state that survives leaving the page, a refresh and an app restart (as a visible failure, not a silent loss).

**Non-Goals:**
- Making jobs survive a restart and resume. An interrupted generation fails and is retried.
- More than two levels.
- Changing the built-in paths (Agentic, AI Engineer); they keep their own models in `paths.py`.
- Running more than one app instance.

## Decisions

### 1. Content fields: `cadence`, `levels`, per-section `numbered`

New content fields:

```
"cadence": "weeks" | "days" | "self",
"levels":  {"top": "Week", "sub": "Day"}      # sub "" = no second level
groups[]:  {"id", "title", "numbered": true, "days": [...]}
```

`groups[].days` stays the storage for second-level sections, whatever they're called, so step ids, the editor's
data shape and learners' ticks don't move. `normalize()` reads the new fields when present and otherwise derives them
from the old ones (`pace` → `cadence`, `level` → `levels.top`, `useDays` → `levels.sub` = "Day" or ""), with
`numbered` defaulting to true.

*Alternative:* rename `days` to `children` or similar. Rejected: touches every reader and the stored data for no
behavior gain.

### 2. Keep writing the old fields during the transition

`normalize()` also writes `pace`, `level` and `useDays`, derived from the new fields (self-paced → `pace` "weeks").
If the deploy is rolled back, the old code still reads a sensible structure; only unnumbered sections and the
second-level name are lost visually. The old fields are dropped in a later change once this one has run in
production.

*Alternative:* a one-off batch migration of every `docs/path-*.json`. Rejected: needs a script against the Files
item, has no rollback, and gains nothing because `normalize()` already runs on every load and save.

### 3. One labelling function per side

Python: `custom_paths.section_label(content, gi)` and `sub_label(content, gi, di)`, used by `where_label`, `model()`
and `generate.edit_draft`. JavaScript: the same two functions in `path.html`, used everywhere `gLabel` and the
hard-coded "Day " appear today. Numbered sections get `<top> <n>` where `n` counts only numbered sections; unnumbered
ones use their title (fallback "Section"). Second-level labels are `<sub> <n>` within their section.

### 4. Schedule mapping in `custom_paths.model()`

- `weeks`: each numbered section is one unit; `unit_name` "Week".
- `days`: each second-level section is one unit (each numbered section when `sub` is ""); `unit_name` "Day".
  Second-level sections inside an unnumbered section share that section's unit.
- `self`: units are irrelevant; `PathModel` gets `unit_name` "" and `units` = 1.
- An unnumbered section takes the unit of the next numbered section, or the last unit when none follows (spec:
  Schedule mapping).

`PathModel.pace()` returns `{"status": "self_paced", "label": "<done> of <total> steps"}` when `unit_name` is "",
before any date maths. The dashboard already counts only known statuses, so "self_paced" falls out of "on track"
and "behind" without extra code; the team table shows its label.

### 5. Cadence change updates default names

Defaults: weeks → {Week, Day}; days → {Day, ""}; self → {Module, ""}. When the cadence changes (wizard or
Settings), each level name that equals the previous cadence's default is replaced by the new default; anything
else is kept. This lives in the page (wizard and Settings) because it's a UI convenience; the server stores what it's
given.

### 6. Generation record is the path document

When generation starts, `app.py` creates the path document immediately with `status: "generating"`, an empty draft
in the chosen structure, and a `wizard` object (name, audience, structure, links, upload ids, notes, more options).
When the job finishes it replaces the draft and sets `status: "draft"`; on error it sets `status: "failed"` with
`error`. On startup, any document still "generating" becomes "failed" with "Generation was interrupted by an app
restart". Admin → Content lists all three statuses for owners and admins; "Try again" sends the `wizard` object
back to the page.

Every place that lists or serves paths to learners must treat only "published" (and later "archived") as visible;
"generating" and "failed" join "draft" as owner-only. A test covers the hub, `api/summary`, path pages and
`/verify`.

*Alternative:* a separate `docs/gen-<id>.json` record. Rejected: two records to keep in sync, and the Content list
would have to merge them.

### 7. Wizard state in the browser, sources in the existing job

The wizard keeps its answers in `localStorage` under `onb.wizard.<user id>`: step, name, audience, structure,
links, upload ids, the find job id and unticked sources. On Admin → Content it offers "Continue creating <name>".
If the find job has expired (over an hour) the wizard re-reads the sources automatically; uploads older than three
hours are listed as "expired, upload again". Storage failures (private mode) are caught and the wizard works without
resume.

*Alternative:* store wizard drafts on the server. Rejected for now: more API surface for a convenience that the
browser covers; can be revisited if authors switch machines mid-creation.

### 8. The LLM gets the structure as constraints

`SYSTEM_GENERATE` loses the length-to-structure rules. The user message states the cadence, top and second level
names, whether there is a second level, and whether to start with an unnumbered "Before you start" section; the
schema adds `numbered` per group. After the LLM answers, the server overwrites `cadence` and `levels` with the
author's choice, so a model that ignores the instruction can't change them. "Approximate length" stays as guidance
for how many sections to make.

### 9. Ready notice

Admin and hub pages check `api/admin/paths?generating=1` every 20 seconds, only while the browser has a
"generating" flag for this user in `localStorage` (set when generation starts). When a path moves to "draft" the
page shows a toast with "Open the draft". If `SLACK_BOT_TOKEN` is set, the job also sends a DM through
`notify.SlackBot.dm`. No polling happens for users with nothing generating.

### 10. .xlsx carries structure on the Path sheet

The Path sheet gains "Cadence" (Calendar weeks / Working days / Self-paced), "Second level is called" (empty for
none) and "Unnumbered sections" (positions in the Group column, for example "1"). "Days inside each group" is still
read from old files. The Steps sheet's columns don't change, so old templates still import.

## Risks / Trade-offs

- [A deploy is a rolling restart: for a minute the old and new instance both run. A path still generating on the old
  instance is marked "failed" by the new one at startup, then saved as a draft by the old one, while the new instance
  keeps showing "failed"] → found on staging (check 8.3). Decided not to change the code: the README's deploy steps
  say to deploy only when nothing is generating, and to restart once more (not delete or retry) if a path shows as
  interrupted after a deploy. A heartbeat on generating paths would fix it if this becomes a problem.

- [A "generating" or "failed" path leaks to learners through a view that only checks for "draft"] → audit every
  `status` check in `app.py`; add a test that a generating path is invisible on the hub, summary, path page and verify.
- [Unnumbered sections shift the meaning of `Item.unit` and pace for existing learners] → existing paths have no
  unnumbered sections, so their units don't change; a test compares `model()` output for a stored path before and
  after.
- [Rollback loses unnumbered sections and second-level names] → old fields are still written (decision 2); the loss
  is cosmetic and is restored when the change is redeployed.
- [localStorage resume points at expired uploads or jobs] → decision 7 re-reads sources or asks for files again.
- [Polling for the ready notice adds load] → only while this user has a generation running; 20-second interval.
- [LLM still returns a different structure] → server overwrites `cadence` and `levels`; sections beyond what the
  structure allows are flattened by `normalize()`.

## Migration Plan

1. Deploy to a staging app with a copy of the production Files item; open every existing path and compare labels,
   pace and team progress with production.
2. Deploy to production. No data migration step: documents are upgraded the next time an owner saves them.
3. Rollback: redeploy the previous source version. Paths saved in the meantime still carry the old fields.
4. A later change removes the old fields once no rollback is expected.

## Open Questions

- The exact wording of the self-paced progress label on the hub card ("12 of 40 steps" or "30% done"). Either fits
  the spec; settle it during implementation.
