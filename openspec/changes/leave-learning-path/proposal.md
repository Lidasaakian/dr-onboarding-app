# Proposal

## Why

Once learners enroll in a path they can't leave it: only an admin can remove them (Admin → Team progress →
Remove). Someone who enrolled by mistake, or whose plans changed, keeps showing up as behind in team views and the
dashboard, and has to ask an admin to fix it.

## What Changes

- Enrolled learners get **Leave this path** on the path page, next to their start date. It asks for confirmation
  first.
- Leaving works like an admin removing them today: the learner drops out of Team progress, the dashboard, cohorts,
  inactivity reminders and the CSV export, and the path shows as not enrolled for them.
- Their ticks, stars, skill growth, badge and certificate are kept. Certificates already issued stay valid at
  `/verify`. If they enroll again, everything comes back.
- Team progress shows who left by themselves, separate from who an admin removed.

## Capabilities

### New Capabilities
- `enrollment`: how learners enroll in a path, leave it, and are removed by admins, and what each does to their
  progress and to team views.

### Modified Capabilities
- None. No specs exist yet in this project.

## Impact

- `app.py`: the enroll endpoint (`PUT <path>/api/enroll`) accepts leaving for the learner themself; the enrollment
  record notes who removed it.
- `static/assets/common.js`: the pace line on every path page (built-in and app-made) gets the leave action.
- `tools/src/path.html` and `tools/src/ai-engineer.html` only if the pace line needs space; built `static/` pages are
  regenerated.
- README: "Features in every path" says learners can't leave a path; that changes.
- Related to `archive-published-paths`, which also changes who can enroll; the two can land in either order.
