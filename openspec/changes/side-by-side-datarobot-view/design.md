# Design

## Context

See proposal.md. Every path page (app-made, AI Engineer, Agentic) builds its top tools (search, Report a problem)
through `DROnb.init({toolsMount})` in `static/assets/common.js`. The app runs as a DataRobot custom application, so in
production its pages are served from the DataRobot site itself (https://app.datarobot.com/custom_applications/<id>/).

## Goals / Non-Goals

**Goals:** the button, one reused window placed beside the path, and DataRobot links routed into it.

**Non-Goals:** the split view inside the page. It depends on whether DataRobot's pages load in a frame on the app's
page (`X-Frame-Options: SAMEORIGIN` allows it only from the same site, and sign-in cookies must also work), which
needs a test in a signed-in browser; it stays a follow-up.

## Decisions

1. **A named window (`"datarobot"`) opened with `window.open`.** Browsers reuse a window with the same name, so a second
   click or a DataRobot link lands in the same window; the page keeps the handle and calls `focus()`. Size and
   position come from the current window: the right half of the screen when the path window sits on the left,
   otherwise to the right of it if there's room. Browsers may ignore the position; that's acceptable.
2. **The DataRobot site is the app's own origin** when the host ends in `datarobot.com` and isn't `docs.` or another
   non-app host; otherwise https://app.datarobot.com. Computed once in `common.js`.
3. **Links are routed with one click handler** on the document (capture phase): a left click without modifier keys on
   an `<a>` whose host is the DataRobot site opens it in the named window. Ctrl/Cmd-click and middle-click keep the
   browser's own behavior.
4. **The button goes into `init`'s tools**, before Report a problem, so all three page kinds get it without changes
   to their own code.

## Risks / Trade-offs

- [Pop-up blockers] → `window.open` runs directly in the click handler, which browsers allow.
- [The DataRobot window is navigated away from the learner's work when they click a DataRobot link] → that's what a
  link does; the learner can still use the window's Back button.

## Open Questions

- Which DataRobot page the button opens per path (for example the Workbench for a lab). The home page for now; a
  per-path setting can come later without changing this design.
