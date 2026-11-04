# Tasks

## 1. Server

- [x] 1.1 Accept `{"leave": true}` on `PUT <path>/api/enroll` for the learner themself (400 when not enrolled), storing the removal marker with `left: true`; verify tests: leaving drops them from team-summary and the dashboard, keeps ticks and badge, and enrolling again restores them
- [x] 1.2 Add `left` (learners who left themselves, not admin removals) to `api/team-summary`; verify a test with one leaver and one removed learner

## 2. Pages

- [x] 2.1 Add Leave this path, with a confirmation, to the pace line in `static/assets/common.js`; verify in a local run on an app-made path and the AI Engineer path that leaving shows Enroll again and ticks come back after enrolling
- [x] 2.2 Show "Left by themselves" under the Team progress table in `tools/src/admin.html`; verify locally after leaving a path

## 3. Docs and build

- [x] 3.1 Update README ("Features in every path"); rebuild `static/`; verify the full test suite passes
