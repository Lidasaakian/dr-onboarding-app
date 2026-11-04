# Tasks

## 1. Rendering

- [x] 1.1 Replace `rich()` in `tools/src/path.html` with a block and inline renderer for lists, checklists, bold, italic, links, code and bare links that only builds DOM nodes; verify with a Node test of the renderer covering every spec scenario, including the HTML and javascript: cases
- [x] 1.2 Add `plain()` and use it for search entries and problem report text; verify the Node test covers it

## 2. Checklist ticks

- [x] 2.1 Render checklist items as checkboxes bound to `S.checks`, saved with progress, read-only in edit, preview and archived; verify locally that a tick survives a reload and doesn't change the step's tick
- [x] 2.2 Validate `state.checks` on `PUT <path>/api/progress`; verify a pytest that a bad shape is refused and a good one is kept

## 3. Editor toolbar

- [x] 3.1 Add the toolbar (bullet, numbered, checklist, bold, italic, link) to each details field in edit mode; verify locally the two toolbar scenarios and that Undo reverts a toolbar change

## 4. LLM, .xlsx, docs

- [x] 4.1 Describe the syntax in the generation and edit prompts and in the .xlsx template note; verify a pytest that the prompts mention it and that details with formatting survive normalize and an .xlsx round trip
- [x] 4.2 Update README (editing a draft); rebuild `static/`; verify the full test suite passes
