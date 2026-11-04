# Design

## Context

See proposal.md. `static/assets/common.js` already has `DR_SITE` (the DataRobot site), `openDataRobot()` (the named
window) and a click handler that sends DataRobot links to it. Every path page builds its top tools through
`DROnb.init`.

## Decisions

1. **A fixed panel on the right, the page shrinks beside it.** `body.onb-dr-open` gets `padding-right` equal to the
   panel width (CSS variable `--onb-dr-w`), so every page layout keeps working without changes. The panel is a
   `<iframe>` with a toolbar above it and a drag handle on its left edge (pointer events; 360 px to 75% of the window).
2. **Only same-site.** The panel is used when `DR_SITE === location.origin` and the window is at least 900 px wide;
   otherwise the old window. `localStorage["onb.drSite"]` can override `DR_SITE`, so the panel can be tried locally
   by pointing it at the local app itself.
3. **Sandboxed frame:** `sandbox="allow-scripts allow-same-origin allow-forms allow-popups
   allow-popups-to-escape-sandbox allow-modals allow-downloads"` (no top navigation), so a frame-busting script can't
   navigate the path page away. Same-site content can read its own history, so back, forward and reload call the
   frame's `history` and `location`.
4. **Failure detection:** if the frame's document can't be read after it loads (another site, refused), or it's still
   empty after 15 seconds, the panel shows "DataRobot didn't load here" with Open in new window.
5. **State in `localStorage`** (`onb.drPanel`: open, width, last URL), updated on frame loads; wrapped in try/catch.
   The last URL is only reused if it's on `DR_SITE`.

## Risks / Trade-offs

- [DataRobot's own UI may refuse to run in a frame, or its sign-in may not work there] → can't be checked without a
  signed-in browser; the failure message and the window fallback cover it, and staging is checked before release.
- [Narrow laptops] → the panel starts at 45% of the window and can be resized; under 900 px the window is used.
