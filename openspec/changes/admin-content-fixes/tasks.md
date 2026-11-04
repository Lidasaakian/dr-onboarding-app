# Tasks

## 1. Resolve DataRobot bugs by hand

- [x] 1.1 Set `manualStatus` (and clear `autoResolved`) in the report status endpoint, and skip status changes for such reports in the Jira sync; verify tests for manual resolve, manual reopen and an untouched bug under the sync
- [x] 1.2 Show Mark resolved / Reopen for every report in `renderReports`, including bugs with a Jira key; verify in a local run that a Jira bug can be resolved and reopened

## 2. One list of paths in Content

- [x] 2.1 Remove `builtinCards`, `showDiff` and `srcText` from `tools/src/admin.html`; verify a local run shows AI Engineer and Agentic only as table rows with Edit, and the console has no errors
- [x] 2.2 Add Go back to the deployed version to the AI Engineer and Agentic edit bars, shown only when `api/admin/content` reports an uploaded source, with a confirmation, posting to `/revert`; verify locally that it appears after publishing an edit and that going back shows the deployed content

## 3. Back to Content from edit mode

- [x] 3.1 Make the back link read "← Content" and open Admin → Content in edit mode on app-made, AI Engineer and Agentic pages, and switch it back on leaving edit mode or entering preview; verify by hand on all three

## 4. Docs and build

- [x] 4.1 Update README ("Admin features", "Editing content in the app"); rebuild `static/` with `tools/build_pages.py`; verify the full test suite passes and README matches the screens
