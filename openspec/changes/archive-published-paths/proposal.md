# Proposal

## Why

Once a learning path is published there's no way to retire it: the app refuses to delete a published path, and
there's no other option. Out-of-date paths stay on the hub and keep taking new enrollments.

## What Changes

- Published paths can be **archived**: hidden from the hub, closed to new enrollments, and marked as archived in
  Admin → Content.
- Learners who already enrolled keep their progress, badges and certificates; certificate verification keeps
  working for archived paths.
- Archived paths can be **restored** to published.
- Drafts can still be deleted, as today. Published and archived paths still can't be deleted, because that would
  break learners' progress and certificates.
- Dashboard and Team progress either leave out archived paths or label them, so current numbers aren't skewed.
- Open question: can owners archive their own paths, or only admins?
- Open question: can learners who already enrolled still open and finish an archived path?

## Capabilities

### New Capabilities
- `path-lifecycle`: the states a learning path goes through (draft, published, archived) and what each allows:
  editing, enrolling, deleting, restoring.

### Modified Capabilities
- None. No specs exist yet in this project.

## Impact

- `app.py`: path status, archive and restore endpoints, hub and enrollment rules, dashboard and team views,
  certificate verification for archived paths.
- `custom_paths.py`: the `status` field gains "archived".
- `tools/src/admin.html` (Content list and path actions) and `tools/src/hub.html` (hiding archived paths); built
  `static/` pages are regenerated.
- Built-in paths (Agentic, AI Engineer) are out of scope: they come from the deployed files.
