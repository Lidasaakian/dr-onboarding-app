# Tasks

## 1. Open DataRobot

- [x] 1.1 Add the DataRobot site lookup, the named side window (placed beside the path, reused and focused) and the Open DataRobot button to the shared top tools in `static/assets/common.js`; verify locally on an app-made, the AI Engineer and the Agentic page that the button is there and calls `window.open` once per window name with a position and size
- [x] 1.2 Route left clicks on links to the DataRobot site into the same window, leaving docs links and modified clicks alone; verify locally with a step linking to app.datarobot.com and one to docs.datarobot.com

## 2. Docs

- [x] 2.1 Update README ("Features in every path"); verify the full test suite passes

## Workflow follow-up

- Split view: on the staging app, in a browser signed in to DataRobot, check whether a DataRobot page loads in an iframe on a path page (for example from the browser console). If it does, plan the split view as its own change.
