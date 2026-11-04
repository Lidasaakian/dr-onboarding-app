# Design

## Context

See proposal.md. Step details are plain strings (`custom_paths.normalize` keeps up to 4,000 characters). The learner
page renders them with `rich()` in `tools/src/path.html`, which builds DOM nodes for `code` and bare links. The
editor edits details in a `contenteditable="plaintext-only"` span. Progress state is a JSON object the page saves
whole (`PUT <path>/api/progress`); the server only checks `done`.

## Decisions

1. **A small Markdown-like syntax, rendered by building DOM nodes.** Block level: lines starting `- [ ] `/`- [x] `,
   `- `, `N. `; everything else is a paragraph keeping line breaks. Inline: `` `code` ``, `**bold**`, `*italic*`,
   `[text](url)`, bare URLs. No HTML is ever parsed; only `http(s)` URLs become links. *Alternative:* a Markdown
   library with sanitizing. Rejected: a CDN dependency on every path page for a handful of rules, and sanitizers are
   easy to misconfigure.
2. **Checklist ticks in `state.checks`:** `{"<step id>": {"<item index>": timestamp}}`, saved with the rest of the
   state. Items are keyed by their position among that step's checklist items, so reordering checklist lines moves
   ticks with the position; the trade-off is acceptable for short checklists. The server checks `checks` is an object
   of objects when present. Progress, pace and badges never read it.
3. **Toolbar per details field in edit mode.** Buttons edit the text of the plaintext span (selection offsets within
   its single text node) and fire the existing `input` handling, so undo and autosave work unchanged.
4. **One `plain()` helper** strips the syntax for search entries and problem reports.
5. **The LLM and the .xlsx know the syntax.** The generation and edit prompts list it; the .xlsx template note
   mentions it; details pass through unchanged.

## Risks / Trade-offs

- [`*` used for other things, like "5 * 3"] → italic needs a non-space right after the opening `*` and right before
  the closing one, so "5 * 3" stays as text.
- [Checklist ticks drift when an author reorders items] → documented; the step's own tick, which counts, is
  unaffected.
