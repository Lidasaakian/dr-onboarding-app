# Proposal

## Why

The working area beside the steps shows DataRobot, but every other link in a step (a video, docs, a practice site)
still opens a separate tab, so learners keep switching back and forth. Many of those sites can be shown inside a
page; some refuse (each site decides, through its X-Frame-Options and Content-Security-Policy headers).

## What Changes

- Links in a path's steps open in the working area when the site allows being shown inside another page: for
  example DataRobot docs, Python docs, CodingBat.
- YouTube and Vimeo links open in their video players inside the working area.
- Links to sites that refuse (for example Anthropic Academy, Anthropic docs, GitHub, Confluence, Coursera) open in a
  new tab as before, with a short note saying the site can't be shown inside the path.
- The working area's toolbar shows which site it's showing; back and forward work for DataRobot pages, and every page
  has reload and Open in new window.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `learner-workspace`: the working area shows any link from a path that its site allows, not only DataRobot. (Its
  requirements are still in the `side-by-side-datarobot-view` and `embedded-datarobot-panel` changes.)

## Impact

- New `framing.py`: decides from a site's headers whether it can be shown in a frame, turns YouTube and Vimeo links
  into player links, and remembers answers; `app.py`: `POST api/frameable`.
- `static/assets/common.js` / `common.css`: link handling and the working area toolbar on every path page.
- The server fetches the headers of public links from steps (never private addresses), once per link per day.
