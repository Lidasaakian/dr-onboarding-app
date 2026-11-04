# Tasks

## 1. Server

- [x] 1.1 Load archived paths into `PATHS` with an `archived` flag; add archive and restore endpoints for owners and admins; refuse editing archived paths and deleting published or archived ones; verify tests for archive, restore, built-in refusal and delete/edit refusal
- [x] 1.2 Hide archived paths from `api/summary` for learners not enrolled, refuse enrolling and saving ticks, keep leaving and certificates working, leave them out of the dashboard and mark them in team-summary; verify tests for each

## 2. Pages

- [x] 2.1 Admin → Content: Archived pill, Archive on published app-made rows and Restore on archived rows with confirmations; verify locally
- [x] 2.2 Path page and hub: archived note, disabled checkboxes, "new enrollments are closed" in place of Enroll, Archived label on hub cards; verify locally as an enrolled and a non-enrolled learner

## 3. Docs and build

- [x] 3.1 Update README ("Creating a learning path" end, "Admin features"); rebuild `static/`; verify the full test suite passes
