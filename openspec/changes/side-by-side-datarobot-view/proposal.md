# Proposal

## Why

Learners read a step in the onboarding app, then switch to DataRobot to do it, then switch back. Showing the steps
on the left and DataRobot on the right would let them follow along without losing their place.

## What Changes

- **Spike first**: find out whether DataRobot can load inside a frame in the app. `app.datarobot.com` sends
  `X-Frame-Options: SAMEORIGIN`, so it only works if the app's pages are served from the same origin as DataRobot
  and DataRobot's own pages and sign-in also allow it. The spike checks this on the deployed app, across the pages
  learners actually use.
- If embedding works: a split view on the path page with the steps on the left and DataRobot on the right. A step's
  link opens in the right-hand pane, and the learner can resize or close it.
- If it doesn't: a fallback that opens DataRobot in a second window sized and placed beside the path, with step
  links opening in that window.
- The rest of the path page keeps working as it does now: ticks, stars, search and problem reports.

## Capabilities

### New Capabilities
- `learner-workspace`: how a learner works through a path next to DataRobot: the split view or side window, and
  how step links open in it.

### Modified Capabilities
- None. No specs exist yet in this project.

## Impact

- `tools/src/path.html` and shared `static/assets/common.js` / `common.css`: layout, the DataRobot pane or window,
  link handling; built `static/` pages are regenerated.
- Possibly `app.py` if links need rewriting to same-origin URLs.
- Depends on DataRobot's framing and cookie rules, which this app doesn't control; the spike decides which option
  is built.
- Independent of the other changes; it can be explored at any time.
