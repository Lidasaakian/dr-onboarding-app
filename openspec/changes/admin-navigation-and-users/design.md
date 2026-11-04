# Design

## Context

See proposal.md. Path pages set their back link in different places: `tools/src/path.html` (`setMode`) and
`DROnb.builtinEditing` in `static/assets/common.js` for the built-in pages. The Admin page links to path pages from
Team progress, Problem reports, Content and the Users tab's "Owns" column.

## Decisions

1. **The Admin page records where a path was opened from** in `sessionStorage` (`onb.from`: Admin URL with its tab,
   the tab's name, time), from one capture-phase click handler on links to other pages of the app. *Alternative:*
   adding `?from=` to every link. Rejected: every link builder would need it, and new links would forget.
2. **Path pages use it only when they were reached from Admin** (`document.referrer` is the Admin page, or the same
   page after a reload), and only for a few hours, so an old entry never redirects a learner. `DROnb.backLink(root)`
   returns `{href, text}`; `common.js` applies it on load, `path.html` and `builtinEditing` use it when leaving edit
   mode.
3. **Users toolbar:** a `<select>` and a search `<input>`; typing re-draws only the rows, so focus stays put.
