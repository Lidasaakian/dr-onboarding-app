# Proposal

## Why

"Open DataRobot" opens DataRobot in another window or tab, so learners still switch back and forth. They want
DataRobot inside the path page: the step on the left, DataRobot on the right, like the clinic tools they're used to.
Both the app and DataRobot are served from app.datarobot.com and send `X-Frame-Options: SAMEORIGIN` with no stricter
policy, so the browser allows the app to show DataRobot in a frame.

## What Changes

- **Open DataRobot** opens a DataRobot panel on the right side of the path page, next to the steps. The panel has a
  button to collapse it, back, forward, reload, "Open in new window", and a handle to make it wider or narrower.
- DataRobot links in steps open in the panel.
- The panel stays open, with its width and the last DataRobot page, while the learner moves between sections and
  when they come back to the path.
- Where the panel can't work (the app isn't served from the DataRobot site, a narrow screen, or DataRobot doesn't
  load in it), the button and links open DataRobot in a separate window as today.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `learner-workspace`: DataRobot opens in a panel inside the path page instead of a separate window, with the window
  kept as the fallback. (Its requirements are still in the `side-by-side-datarobot-view` change; this change adds to
  them.)

## Impact

- `static/assets/common.js` and `common.css`: the panel, its toolbar and resizing, link routing; every path page
  (app-made, AI Engineer, Agentic) gets it through `DROnb.init`.
- Depends on DataRobot's pages running inside a frame; checked on staging in a signed-in browser before release.
