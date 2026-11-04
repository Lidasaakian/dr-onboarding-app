# Tasks

## 1. Panel

- [x] 1.1 Build the panel in `static/assets/common.js` and `common.css`: same-site and width check, sandboxed frame, toolbar (collapse, back, forward, reload, open in new window), drag-to-resize, state kept in `localStorage`, failure message; verify locally with `onb.drSite` pointed at the local app: open, collapse, reopen on the same page, resize, reload restores it
- [x] 1.2 Route the Open DataRobot button and DataRobot step links to the panel when it can be used, and to the window otherwise; verify locally both with and without the override

## 2. Docs and check

- [x] 2.1 Update README (Open DataRobot); verify the full test suite passes

## Workflow follow-up

- On staging, in a browser signed in to DataRobot, open a path, click Open DataRobot and check that DataRobot loads and works in the panel (sign-in, Workbench, a codespace). If it doesn't, the panel shows the fallback message and the window still works.
