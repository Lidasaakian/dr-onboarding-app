# Proposal

## Why

Learners read a step in the onboarding app, then switch to DataRobot to do it, then switch back. There's no way to
get to DataRobot from a path except a step's own link, so learners hunt for the right tab and lose their place.

## What Changes

- **Open DataRobot button (first):** every path page (built-in and app-made) gets an **Open DataRobot** button in its
  top tools. It opens DataRobot in a second window sized and placed beside the path, and reuses that window when
  clicked again, so a learner can open it whenever they need it.
- Step links that point to DataRobot (`app.datarobot.com`) open in that same window instead of a new tab each time.
- **Split view (second, only if possible):** a spike checks whether DataRobot can load inside a frame in the app.
  `app.datarobot.com` sends `X-Frame-Options: SAMEORIGIN`, so it only works if the app's pages are served from the
  same origin as DataRobot and DataRobot's own pages and sign-in also allow it. If it does, the button can instead
  show DataRobot in a resizable pane on the right with the steps on the left; if not, the side window stays the only
  option.
- The rest of the path page keeps working as it does now: ticks, stars, search and problem reports.

## Capabilities

### New Capabilities
- `learner-workspace`: how a learner works through a path next to DataRobot: the Open DataRobot button, the side
  window or split view, and how DataRobot links open in it.

### Modified Capabilities
- None. No specs exist yet in this project.

## Impact

- `static/assets/common.js` / `common.css` (shared top tools on every path page) and `tools/src/path.html`; built
  `static/` pages are regenerated.
- Which DataRobot page the button opens: the DataRobot home by default; it could be set per path later.
- Browsers decide where a new window goes; placing it beside the path works on most desktop browsers but not all,
  and not on phones, where it opens as a normal tab.
- The split view depends on DataRobot's framing and cookie rules, which this app doesn't control; the spike decides
  whether it's built.
- Independent of the other changes, though it touches the same shared files as `leave-learning-path`.
