# Proposal

## Why

Step details are plain text: the learner page only turns `code` and bare links into anything other than text.
Authors can't write a list of things to install, numbered instructions, or a checklist, can't stress a word, and
can't link a phrase instead of pasting a raw URL, so longer steps turn into hard-to-follow paragraphs.

## What Changes

- Step details support bullet lists, numbered lists and checklists, using a small, predictable syntax that also
  works in the .xlsx template and in LLM-generated content.
- Step details also support **bold**, *italic* and links with their own text (a phrase that links to a URL), in the
  same syntax.
- The learner page renders all of it; existing `code` and bare-link handling keeps working, and nothing an author
  writes can inject HTML or scripts into the page.
- The editor has a small toolbar for the details field (bullet list, numbered list, checklist, bold, italic, link),
  so authors don't have to remember the syntax.
- LLM generation and "Ask the LLM to change the draft" may use the same formatting.
- Open question: are checklist ticks inside a step saved per learner, or only visual? Saving them means storing
  more progress data; leaving them visual keeps the step's own tick as the only thing tracked.

## Capabilities

### New Capabilities
- `step-formatting`: the formatting allowed in step details and how it's written, edited and shown to learners.

### Modified Capabilities
- None. No specs exist yet in this project.

## Impact

- `tools/src/path.html`: the `rich()` renderer, the step editor and its toolbar, and their styles; built `static/`
  pages are regenerated.
- Search and problem-report text should use the plain words, not the formatting syntax.
- `generate.py`: the generation and edit prompts describe the allowed formatting.
- `custom_paths.py`: the .xlsx template note; normalization must keep the formatting intact.
- If checklist ticks are saved: progress storage and the progress API in `app.py`.
- Should land after `flexible-path-structure-wizard`, which edits the same editor files.
