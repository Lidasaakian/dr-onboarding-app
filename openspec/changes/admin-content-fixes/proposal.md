# Proposal

## Why

Three small things get in admins' and authors' way. A DataRobot bug that went to Jira can't be marked resolved in
Admin → Problem reports: it only resolves when its Jira issue is done, so a bug fixed some other way stays open
forever. The Content tab shows two separate cards for the built-in paths (AI Engineer and Agentic) with upload,
download and "go back to the deployed version" tools, which is a second, confusing way to edit content that the app
already edits in place. And the back arrow in a path's edit mode goes to the hub, so authors lose their place in
Admin → Content.

## What Changes

- **Resolve DataRobot bugs by hand:** bug reports with a Jira issue get **Mark resolved** and **Reopen** in
  Admin → Problem reports, like learning-path reports. A bug marked resolved by hand stays resolved when the Jira
  sync runs; a bug resolved by the sync still reopens if its Jira issue reopens, as today.
- **One way to edit built-in paths:** the two built-in path cards (upload a sheet or page, download, go back to the
  deployed version) are removed from the Content tab. AI Engineer and Agentic stay in the paths list with an **Edit**
  button that opens in-app editing, like app-made paths. **BREAKING** for admins who upload .xlsx or .html files for
  the built-in paths: that is no longer possible from the app.
- **Back to Content from edit mode:** while a path is in edit mode (drafts and "Edit content" on a published path),
  the back arrow reads "← Content" and opens Admin → Content. Learners and preview mode keep "← All learning paths".

## Capabilities

### New Capabilities
- `problem-reports`: how problem reports and DataRobot bugs are listed, resolved and reopened in Admin → Problem
  reports, including how manual resolution and the Jira sync interact.
- `content-management`: what Admin → Content lists and offers for each path, and how authors move between it and a
  path's editor.

### Modified Capabilities
- None. No specs exist yet in this project.

## Impact

- `tools/src/admin.html`: the report actions (`renderReports`), the Content list (`contentHome`), removal of
  `builtinCards` and `showDiff`; built `static/` pages are regenerated.
- `tools/src/path.html`: the back link in edit mode.
- `app.py`: the report status endpoint and the Jira sync (`autoResolved` handling). The built-in content preview and
  publish endpoints stay: in-app editing of the built-in paths saves through them. Only the file-upload handling and
  the revert endpoint stop being used.
- README: "Editing content in the app" and "Admin features" sections.
- Saved content for the built-in paths (`content-ai-engineer`, `content-agentic`, written by both uploads and in-app
  edits) stays live. Today both paths show the deployed version, so nothing changes for learners.
- Open question: removing "Go back to the deployed version" leaves no one-click way to undo all in-app edits of a
  built-in path. Keep that action somewhere (for example in the path's edit bar), or drop it?
