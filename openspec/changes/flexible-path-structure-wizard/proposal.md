# Proposal

## Why

Authors can't shape a learning path the way they teach it. Changing the cadence seems to do nothing: pace and the
top-level label are separate settings, so a "working days" path still shows "Week 1, Week 2". The second level can
only be "Day". Every section is numbered, so a path can't open with "Prerequisites" or "Before you start". On top
of that, creating a path from sources means filling in a long form, picking a route before starting, and waiting on
a page that loses everything when it's refreshed.

## What Changes

- **Cadence** becomes one clear choice: calendar weeks, working days, or self-paced. It drives both the labels
  learners see and the on-track / behind-schedule status. Self-paced paths have no schedule.
- **Structure** gets two named levels. The author names the top level (Week, Module, Phase, Day or their own name)
  and picks an optional second level (none, Days, Modules or their own name), replacing the fixed "Day".
- **Unnumbered sections**: a section can have its own title ("Prerequisites", "Before you start") instead of a
  number. It isn't counted in the schedule or in the numbering of the sections after it.
- **Creation wizard** replaces the two-route choice and the long form: Basics (name, who it's for) → Structure
  (cadence, levels, optional "Before you start" section) → Sources (optional; skipping it starts an empty draft)
  → Review what was found → Generate → Open the draft. Back keeps what was entered, and skill growth and owners
  move to "More options" because they can be changed later in Settings.
- **Generation follows the author's structure**: the cadence and levels chosen in the wizard are passed to the LLM
  as constraints instead of being inferred from the length.
- **Generation in the background**: the author can leave the page. The draft shows as "Generating…" in Admin →
  Content and the author is told when it's ready. Work in progress in the wizard survives a page refresh.
- **Existing paths are converted** to the new structure fields without changing their step ids, so learners'
  ticks, badges and certificates are untouched.
- The .xlsx template import and export carry the new structure fields.

## Capabilities

### New Capabilities
- `path-structure`: how a path's content is organized and scheduled: cadence, level names, numbered and unnumbered
  sections, and how that maps to learners' pace and progress.
- `path-creation`: how authors create a learning path: the guided wizard, sources, LLM generation in the
  background, and the resulting draft.

### Modified Capabilities
- None. No specs exist yet in this project.

## Impact

- `custom_paths.py`: the content format (`pace`, `level`, `useDays` → cadence, level names, per-section
  numbering), normalization, conversion of stored paths, the PathModel mapping, and the .xlsx template.
- `paths.py`: pace and unit handling for self-paced paths and unnumbered sections.
- `generate.py`: the generation prompt and schema take the chosen structure; job status needs to outlive the page.
- `app.py`: create, find and generate endpoints; listing paths that are still generating.
- `tools/src/admin.html`: the create flow is rebuilt as a wizard. `tools/src/path.html`: section labels, the
  editor's structure controls and Settings. The built `static/` pages are regenerated.
- Stored paths in the Files item (`docs/path-<id>.json`) are converted, so the change needs a tested migration.
- Open question: what learners see for "pace" on a self-paced path (nothing, or progress only).
