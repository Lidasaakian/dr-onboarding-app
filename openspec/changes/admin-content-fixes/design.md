# Design

## Context

See proposal.md for why. Report status changes go through `POST api/reports/{id}` (`app.py`); the Jira sync
(`sync_jira`) resolves a bug when its issue is done and reopens it only if the sync resolved it (`autoResolved`).
`renderReports` in `tools/src/admin.html` hides the status button for bugs with a Jira key. Built-in paths save
in-app edits and uploads the same way: `api/admin/content/{id}/preview` then `/publish` write
`docs/content-<id>.json`; `/revert` writes `{"reverted": true}`. The built-in path cards (`builtinCards`, `showDiff`)
in Admin → Content are the only file upload, download and revert UI.

## Goals / Non-Goals

**Goals:** the three behaviors in the specs, with no change to how content is stored.

**Non-Goals:** removing API endpoints (the preview, publish and export endpoints are still used by in-app editing and
the edit bar's .xlsx download); changing the Jira sync schedule.

## Decisions

1. **A `manualStatus` flag on reports.** The status endpoint sets `manualStatus: true` and clears `autoResolved`. The
   sync skips status changes for reports with `manualStatus`, but still refreshes their Jira details. *Alternative:*
   only skip when resolved by hand. Rejected: a bug reopened by hand would be resolved again by the next sync.
2. **Remove the UI only.** `builtinCards`, `showDiff` and `srcText` go from `admin.html`; the endpoints stay because
   in-app editing uses them. The upload-from-file branch of `preview` becomes unused but harmless; it stays so an
   older admin page can't break mid-deploy.
3. **Undo in the edit bar, from `GET api/admin/content`.** On entering edit mode, the AI Engineer and Agentic pages
   ask `api/admin/content` (admins only) for `source.kind`; when it's "uploaded" they show the button, which posts to
   `/revert` and reloads. Built-in editing is already admin-only, so the call never fails for someone who can edit.
4. **Back link set on mode change.** `path.html` sets the link in `setMode`; the built-in pages set it in
   `enterEdit` / `leaveEdit`. Preview mode counts as not editing.

## Risks / Trade-offs

- [Admins who relied on .xlsx upload for AI Engineer lose it] → in-app editing covers the same content, and the
  edit bar still downloads .xlsx; called out as BREAKING in the proposal.
- [A report changed by hand no longer follows Jira] → that's the intent; Reopen or Mark resolved changes it again.
