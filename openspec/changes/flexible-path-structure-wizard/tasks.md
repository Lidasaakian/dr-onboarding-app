# Tasks

## 1. Test setup

- [x] 1.1 Add `requirements-dev.txt` with pytest and a `tests/` folder with a `conftest.py` that loads stored-path fixtures from JSON; verify `pytest` runs and collects zero failures
- [x] 1.2 Add fixtures copied from real path documents: a weeks path with days, a days path without days, and a custom-level path; verify they load through `custom_paths.normalize()` in a smoke test

## 2. Structure model (`custom_paths.py`)

- [x] 2.1 Extend `normalize()` and `blank_content()` with `cadence`, `levels` and per-group `numbered`, deriving them from `pace`/`level`/`useDays` when missing and still writing the old fields (design decisions 1–2); verify with tests that each fixture gets the equivalent structure and unchanged step ids
- [x] 2.2 Add `section_label()` and `sub_label()` and use them in `where_label()`; verify tests for numbered, unnumbered (title only, not counted) and custom names
- [x] 2.3 Rework `model()` for the schedule mapping of weeks, days and self-paced, with unnumbered sections taking the next numbered section's unit (design decision 4); verify tests for each scenario under "Schedule mapping" and that every fixture's `Item.unit` values match the pre-change output
- [x] 2.4 Merge second-level sections into their section when `levels.sub` becomes "" without changing step ids; verify a test for "Remove days from a week"
- [x] 2.5 Update `.xlsx` export, template and import for "Cadence", "Second level is called" and "Unnumbered sections", still reading "Days inside each group" (design decision 10); verify the round-trip test and that an old-format template still imports
- [x] 2.6 Update the module docstring and README's "Creating a learning path" section for the new structure; verify the documented fields match `normalize()`

## 3. Pace for self-paced paths (`paths.py`, `app.py`)

- [x] 3.1 Return `{"status": "self_paced", "label": ...}` from `PathModel.pace()` when there is no schedule unit; verify unit tests for a self-paced learner and that existing statuses are unchanged
- [x] 3.2 Check the dashboard tiles, team table, CSV export and inactive-learner summary handle "self_paced"; verify a test that self-paced learners are in neither the on-track nor the behind count

## 4. Learner page and editor (`tools/src/path.html`)

- [x] 4.1 Replace `gLabel`, `where` and the hard-coded "Day " with shared label functions; verify by building the pages and checking a fixture path shows "Before you start", "Week 1", "Week 2" with modules inside
- [x] 4.2 Add a "numbered / unnumbered" toggle to each section's menu in the editor; verify that turning it off renumbers the following sections immediately
- [x] 4.3 Rework Settings: cadence (weeks, days, self-paced), top-level name, second-level name or none, with default names following the cadence (design decision 5) and a confirmation before merging sub-sections; verify the "Labels follow the cadence" scenarios by hand on a draft
- [x] 4.4 Show the self-paced progress label in the header instead of the schedule; verify on a self-paced draft in preview
- [x] 4.5 Add a "Generation report" panel to generated drafts, read from the stored `generation` field; verify it appears on a generated draft and not on a hand-built one
- [x] 4.6 Rebuild with `tools/build_pages.py` and commit the regenerated `static/` pages; verify `git diff` shows matching changes in `tools/src/` and `static/`

## 5. Generation follows the structure (`generate.py`)

- [x] 5.1 Remove the length-to-structure rules from `SYSTEM_GENERATE`, pass cadence, level names and the "Before you start" choice in the request, add `numbered` to the schema, and overwrite `cadence`/`levels` with the author's choice after parsing (design decision 8); verify a test with a stubbed LLM that returns weeks when days were asked for
- [x] 5.2 Use the shared label functions in `edit_draft()` scope labels; verify a test that the scope label for an unnumbered section is its title

## 6. Background generation (`app.py`, `generate.py`)

- [x] 6.1 Create the path document with `status: "generating"` and the `wizard` object when generation starts; on success set "draft", on error "failed" with the reason (design decision 6); verify with a stubbed LLM that the status moves through generating → draft and generating → failed
- [x] 6.2 On startup, mark documents still "generating" as "failed" with "Generation was interrupted by an app restart"; verify with a test that loads such a document
- [x] 6.3 Make every learner-facing view treat "generating" and "failed" like "draft" (hub, `api/summary`, path pages, `/verify`, dashboard); verify a test that a generating path is invisible on each of them
- [x] 6.4 List generating and failed paths in Admin → Content data for owners and admins, with the reason and the `wizard` object for "Try again"; verify the `api/admin/paths` response in a test
- [x] 6.5 Send a Slack DM through `SlackBot.dm` when a draft is ready and `SLACK_BOT_TOKEN` is set; verify with a stubbed bot that one DM is sent on success and none on failure
- [x] 6.6 Accept the structure fields in `POST api/admin/paths` and create the "Before you start" section when asked; verify a test that "Skip and start empty" creates the right empty draft

## 7. Creation wizard (`tools/src/admin.html`)

- [x] 7.1 Replace `chooseView`, `buildView` and the long `sourceView` form with a wizard shell: stepper, Back/Continue, state object; verify by hand that "+ Create learning path" opens Basics with five steps shown
- [x] 7.2 Build Basics (name required, who it's for, "More options" with skill growth and owners); verify the "Missing name" and "Defaults for more options" scenarios by hand
- [x] 7.3 Build Structure (cadence, level names following the cadence, approximate length, "Before you start" toggle); verify the two Structure scenarios by hand
- [x] 7.4 Build Sources (links, files, .xlsx template, GitHub token) with "Skip and start empty"; verify skipping opens an empty draft and an .xlsx-only source imports without the LLM
- [x] 7.5 Move "What we found" into the Review step, keeping unticked sources when more are added; verify the "Adding a link on Review" scenario and replace the `alert()` calls with inline messages
- [x] 7.6 Start generation and hand off to the Content list with a "Generating…" row instead of a blocking progress page; verify by leaving the page mid-generation and seeing the row update
- [x] 7.7 Save wizard state to `localStorage`, offer "Continue creating <name>" on Content, re-read expired sources and flag expired uploads (design decision 7); verify the refresh and Back scenarios by hand, and that the wizard still works with storage blocked
- [x] 7.8 Show "Generating…", "Failed" with reason and "Try again" rows in the Content list; verify "Try again" reopens the wizard on Sources with earlier answers
- [x] 7.9 Add the ready notice on admin and hub pages, polling only while a generation is running for this user (design decision 9); verify the toast appears on the hub when a draft finishes
- [x] 7.10 Rebuild with `tools/build_pages.py`, commit `static/`, and update README "Creating a learning path" for the wizard; verify the README steps match the screens

## 8. End-to-end checks on staging

- [x] 8.1 Deploy to a staging app with a copy of the production Files item and open every existing path; verify labels, pace and Team progress match production
- [x] 8.2 Create one path of each kind through the wizard (weeks with modules, working days, self-paced with "Before you start", from an .xlsx, skipped sources); verify each against the path-structure and path-creation scenarios
- [x] 8.3 Restart the staging app during a generation; verify no generated draft is lost, and document the rolling-restart limit in the README's deploy steps (a restart that cuts a generation off is covered by the tests in 6.2)

## Workflow follow-up

- Archive the change with `/opsx:archive` after it's merged and deployed.
- Plan a later change to drop the old `pace`, `level` and `useDays` fields once rollback is no longer expected.
