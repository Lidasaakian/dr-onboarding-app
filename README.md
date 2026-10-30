# DataRobot onboarding hub: DataRobot custom application

One app with several learning paths. Learners browse a path, enroll, tick steps as they go and come back
to **Continue where I left off**, while their **skill growth** card grows stronger. Admins get an **Admin** page
(dashboard, team progress, problem reports, content, users) and can edit the paths in the app. Admins and authors
can **create new paths**: by hand, or from links and files with the LLM. Learners can report a **DataRobot bug**
straight to Jira.

| Path | URL | Content source |
| --- | --- | --- |
| Hub | `/` | `static/index.html` (built from `tools/src/hub.html`) |
| Admin | `/admin/` | `static/admin.html` (built from `tools/src/admin.html`) |
| AI Engineer Learning Plan | `/ai-engineer/` | Edited in the app; first imported from the Google Sheet "AI Engineer Learning Plan" (`static/ai-engineer/content.json`) |
| Agentic AI Learning Path | `/agentic/` | `static/agentic/index.html` (text from the Google Doc) |
| Paths created in the app | `/<path id>/` | Stored with the app's data (`docs/path-<id>.json`); page `static/path/index.html` (built from `tools/src/path.html`) |

## Files

| File | Purpose |
| --- | --- |
| `start-app.sh` | Entry point. Starts the FastAPI server on port 8080, as DataRobot requires. |
| `app.py` | Serves the pages and the API (see the docstring for every route). |
| `paths.py` | What counts in each path: required steps, pace, completion badge, cohorts, inactivity. |
| `storage.py` | Where data lives (DataRobot Files item, or `./data` locally). |
| `notify.py` | Slack messages (problem reports, Monday summary). |
| `roles.py` | Users and roles: system admins (MANAGER_EMAILS), admins and authors invited in the app. |
| `custom_paths.py` | Paths created in the app: content format, ids, the .xlsx template (import and export), change lists. |
| `sources.py` | Reads the links and files a path is created from: Jira/PBMP, Confluence, GitHub, web pages, PDF, Word, PowerPoint, Excel, HTML, Markdown. |
| `generate.py` | Background jobs with the LLM: read sources, generate a path, edit a draft, write a Jira bug. |
| `llm.py` | DataRobot LLM Gateway client (model choice from the catalog). |
| `atlassian.py` | Jira and Confluence client (service account): create bugs, read status, read issues and pages. |
| `ai_engineer_content.py` | Reads the AI Engineer sheet (.xlsx) into the app's content format. |
| `static/` | The pages, the AI Engineer content file, and `assets/`: shared code (search, pace, enroll, stars, reports, badge, skill growth) and the 10 growth stage pictures (`assets/mascots/year-01.png` … `year-10.png`; file names only, never shown to learners). |
| `requirements.txt` | Python dependencies, installed by DataRobot when the app is built. |
| `metadata.yaml` | Runtime parameters (see "Runtime parameters" below). |
| `tools/refresh_ai_engineer.py` | Regenerates `static/ai-engineer/content.json` from the sheet (needs `pip install openpyxl`). |
| `tools/build_pages.py` | Rebuilds the hub, admin, AI Engineer and app-made path pages from `tools/src/` with the shared brand styles. |
| `tools/extract_mascots.py` | Re-extracts the 10 growth stage pictures from the "Anniversary T-Shirt Designs" deck (.pptx; needs `pip install pillow`). |

## AI Engineer plan: what learners get

- Overview, week-by-week plan (Weeks 0–10), capstone tabs (options, roadmap, planning, worked example) and
  optional certifications, all from the sheet.
- Every plan step has a checkbox, plus one **capstone check** per week (from the Project Roadmap tab). All of
  them count toward the progress %. The header also shows Required steps done and gates passed.
- **Track:** learners record their skills-check result. On the fast-track, Week 1 Days 1–4 are labeled
  "Stretch for you" (they still count).
- **Capstone option:** learners pick A–G. Each week from Week 3 then shows that option's gate.
- **Evidence link** on every gate (PR, repo, results file, demo recording). Admins see the links in Team progress.
- Certifications have a checkbox too, but don't count toward progress.

## Features in every path

- **Enroll.** Anyone can browse a path. The first tick (or the **Enroll in this path** button) asks them to enroll and
  pick a start date. Only enrolled learners count in team views and the dashboard. Learners can't leave a path;
  admins can remove someone (Admin → Team progress → Remove), which keeps their ticks for if they enroll again.
  Everyone who had ticks before enrollment existed is enrolled automatically.
- **Skill growth.** Each path has a skill ("AI Engineering", "agentic") that grows through 10 stages: one stage per
  10% of the path's required steps. The card shows in the path header and on the hub. Before enrolling it says
  "Enroll to start growing your <skill> skill"; after, it shows how the skill is doing and how many required steps to the
  next stage, with 10 small squares. Click it to see all stages. Each new stage plays a short animation.
  Growth and badges never go back, even if admins add required steps later. The bar, squares and glow use DataRobot Blue (`#44BFFC`). For a new path, set `skill` in `paths.py`.
- **Stars.** ☆ Star under any step; starred steps are listed on the path's **Starred** page and on the hub, grouped
  by path (click a path to unfold its steps, click a step to open it).

- **Pace.** Each learner has a start date per path. It's set automatically on their first tick, and they can change
  it in the header. Admins can change it in the path's Team progress page. The header shows, for example,
  "Week 3 of 10 · Behind by 1 week": it compares the learner's first open required step with where they should be.
  - AI Engineer: 10 calendar weeks. Week 0 is done during the first week, together with Week 1.
  - Agentic: 7 working days (Monday to Friday).
- **Search** across the path (press `/`). Results jump straight to the step.
- **Report a problem**, on every step and in the header. The learner picks what kind of problem it is:
  - **Something is wrong in this learning path** (a broken link, an unclear step, stuck): goes to Admin → Problem reports
    for the path's owners and the admins, and to Slack if it's set up. Admins and owners mark it resolved.
  - **Something is broken in DataRobot**: the learner describes it, pastes screenshots (⌘V / Ctrl+V), drops files and
    adds links. The LLM writes the Jira summary and description and picks the project of the pod that owns the feature, from
    the engineering org page in Confluence (`JIRA_ROUTING_PAGE`, read every 3 hours, so reorgs are picked up without any
    change to the app); the app creates a **Bug** straight away, attaches the files, and sets the learner as reporter and watcher, so Jira emails them about it.
    If Jira isn't connected or the issue can't be created, the report (with its files) goes to the admins instead.
- **Completion badge** when every required step and every gate is ticked (Stretch and Optional steps don't block it;
  fast-track learners don't need Week 1 Days 1–4). It shows on the path page, on the hub and in the team views.

## Users and roles (Admin → Users)

- **System admins:** the emails in `MANAGER_EMAILS`. Always admins; they can't lose the Admin role or be removed in the
  app, so nobody gets locked out. Reports sent to the system admins (Users → Report a problem) are visible only to them.
- **Admins** see and manage every path, the dashboard, team progress and problem reports, and invite people.
- **Authors** create learning paths. Whoever creates a path is its **owner** and can add co-owners. Owners see that
  path's Dashboard, Team progress, Problem reports and Content, whatever their role.
- Step 1: **invite** someone by email (only @datarobot.com). Step 2: **assign roles** (Admin, Author, both, or none
  for now). People with no role use the hub as learners. Roles apply on the person's next click.
- An in-app role doesn't give access to the app itself: the person still needs the DataRobot share. The list shows when
  each person last opened the app, so an email that doesn't match their DataRobot account is easy to spot.
- **Telling people about a new role:** the next time they open the hub, a banner says which role they got, from whom,
  and what they can now do, until they click **Got it**. With `SLACK_BOT_TOKEN` set, they also get a Slack DM with the
  same text. Both are only about roles that are new to the person; removing a role sends nothing.
- Roles are saved in the Files item (`docs/users.json`), with a history of changes. Keep the Files item shared only
  with the app owner: anyone who can open it could edit the roles.

## Creating a learning path (Admin → Content → + Create learning path)

Both options make a **draft** that only its owners and the admins can see until it's published.

- **Create from source (LLM assisted):** paste links and upload files, in any mix:
  - **Jira / PBMP** (key or link): the issue, its child and linked issues, descriptions, comments, attachments
    (PDF, Word, screenshots, which the LLM can see too), and the Confluence pages, GitHub PRs and docs linked from them.
    Issues that aren't done yet are listed separately and left out by default.
  - **Confluence** pages and their child pages (two levels), with attached PDFs and Word files.
  - **GitHub** repos (README, docs and guides; example files are listed; source code is skipped) and pull requests.
    Private repos need the author's own GitHub token, which is used for that run only and never saved.
  - **Web pages** (for example docs.datarobot.com) and **files**: PDF, Word, PowerPoint, Excel/CSV, HTML, Markdown.
    Google Docs can't be read by the app: download them (File → Download) and upload the file.
  - **The .xlsx template** (download it from the form): it's imported exactly as it is, without the LLM.
  - **What we found** lists everything before generating; untick what's out of date, or upload more files and links.
    Restricted pages and Google Docs are flagged. The LLM summarizes each source first, then builds the path from all
    the summaries, so nothing is cut off for length. The result lists which sources weren't used, and links that
    didn't open. Every step keeps the source it came from.
- **Build in the app:** start empty with your structure: pace (calendar weeks or working days), what the top level is
  called (Week, Module, Phase or your own name), and whether it has days inside.
- **Skill growth:** "Add now" with a skill name, or "Decide later" and turn it on in Settings any time. Progress is
  tracked from the start, so the right stage shows straight away.
- **Editing a draft:** click any text; each step has Day, Type, Gate and Link controls, move up and down, delete;
  add steps, days and groups. **Ask the LLM to change the draft** works on the whole path, or on one group, day or step
  (the ✦ buttons). It shows the suggested changes; **Apply** or **Discard**. **Undo** covers both kinds of edit.
  **Preview as learner**, **Download as .xlsx**, **Settings** (name, who it's for, length, pace, structure, skill
  growth, owners; delete a draft) and **Publish**. A published path is edited the same way: learners keep seeing the
  published version until you publish again (**Discard changes** goes back to it).
- A published path can't be deleted in the app.

## Certificates

When a learner finishes a path (every required step and gate), the completion dialog and the badge on the path page
offer **Get your certificate**. The learner picks a look (green, or white with a green panel) and a shape (landscape,
or portrait for phones), then **Add to LinkedIn** (LinkedIn's "Add license or certification" form opens filled in),
**Download PNG** or **Download PDF**. The certificate is drawn in the browser.

- It shows the learner's name, the path, the completion date and a credential ID (`DR-XXXX-XXXX`, made the first time
  the learner opens the certificate and kept with their record). "Add to LinkedIn" fills in the ID too.
- Anyone who can open the app can check an ID at `<app>/verify/<credential ID>`.

## Path authors

Every path shows who made it, next to its length (on the hub cards and the path page): the creator of an app-made
path, and for the built-in paths the authors set in `BUILTIN_AUTHORS` in `app.py`. The name is the one in the app;
the round photo comes from the person's Slack profile (needs `SLACK_BOT_TOKEN`). Without a Slack photo, their
initials show instead.

## Admin features (hub → Admin, or `/admin/`)

- **Dashboard:** learners enrolled, active in the last 7 days, completions and open reports; per path: enrollments,
  activity, completions, average required progress and a pace split (on track / ahead / behind / not started);
  charts of weekly active learners, steps ticked and new enrollments over the last 12 weeks (each with a table view).
  Trends come from the tick timestamps, so they include progress made before the dashboard existed.
- **Team progress:** everyone, every path, with pace, badges and an "N days idle" flag after 7 days without a tick.
  Filter by cohort (the month a learner started their first path) or show only inactive learners.
  **Export CSV** downloads one row per learner and path (respects the cohort filter).
- **Problem reports:** Open / Resolved / All. Learning-path reports have Mark resolved, Edit this step and Reply by
  email. DataRobot bugs show the Jira key and status (assignee, resolution, fix version, "Duplicate of …"). The app
  reads every linked issue's status every 15 minutes (and on **Sync now**): resolved in Jira moves the report to
  Resolved, reopened moves it back to Open. Issues the service account can't see show "Can't see this issue in Jira".
- **Content:** every path you manage (status, steps, enrolled, owners), **+ Create learning path**, and for the
  built-in paths the upload and download tools (next section).
- **Users** (admins): invite people and assign roles (above).
- Authors and owners see the same tabs (except Users), limited to the paths they own.
- **Slack (optional):** every report as it arrives, and every Monday from 09:00 Dublin time a summary of inactive
  learners, completions in the last week and open reports.

## Editing content in the app

The app is the source of truth for content. Admins see **Edit content** on each path page (or Admin → Content →
**Edit in the app**). A yellow bar shows you're editing; nothing is live until **Review and publish**, which lists the
steps added or removed and how many learners ticked a removed step.

- **AI Engineer Learning Plan:** click any text to change it (every tab: overview, weeks, capstone pages,
  certifications); change links in the small link fields; add steps (**+ Add a Required step** / **+ Add a Stretch step**),
  delete them, move them up and down, and change their day, path, type and gate flag.
  **Download as .xlsx** gives the current content in the sheet's layout, to share or to edit offline; uploading
  that file again (Admin → Content → Upload a sheet) works too.
- **Agentic AI Learning Path:** click any text to change it; click a link to change or remove it. Each step keeps its
  checkbox, so ticks carry over. For bigger changes you can still **Download the live page**, edit the HTML and upload
  it (keep each step's `data-t="..."` attribute).
- **Go back to the deployed version** (Admin → Content) undoes all in-app edits and uploads for that path.

Edits and uploads are stored with the progress data, so they survive restarts and redeploys. For the AI Engineer plan,
a later deploy whose `content.json` is newer than the last edit wins; to keep in-app edits, don't run
`tools/refresh_ai_engineer.py` and redeploy.

Steps keep their ids when their title or link stays the same, so learners' ticks survive edits. If a step's title
**and** link both change, it counts as a new step. The importer expects the sheet's current tab names and column
order; if a tab is renamed or columns move, update the matching `read_*` function in `ai_engineer_content.py`.

To bake a sheet into the deployed app instead: `python3 tools/refresh_ai_engineer.py "AI Engineer Learning Plan.xlsx"`,
then upload the changed `static/ai-engineer/content.json` with the next app version.

## Runtime parameters

| Parameter | Needed for |
| --- | --- |
| `PROGRESS_FILES_ID` | Where all data lives (progress, reports, users, paths made in the app). |
| `MANAGER_EMAILS` | System admins. |
| `SLACK_WEBHOOK_URL`, `APP_URL` | Optional Slack messages. |
| `SLACK_BOT_TOKEN` | Optional: a DataRobot **credential** (API token type) with a Slack bot token, for DMs to people given a role and the photos of path authors. |
| `LINKEDIN_ORGANIZATION_ID` | Optional: DataRobot's LinkedIn company ID, so certificates added to LinkedIn link to the company page. |
| `JIRA_EMAIL`, `JIRA_API_TOKEN` | Atlassian service account: bugs to Jira, Jira status, reading Jira/PBMP and Confluence for new paths. `JIRA_API_TOKEN` is a DataRobot **credential**: API token type, or basic with the email as username and the token as password (then `JIRA_EMAIL` can stay empty). |
| `JIRA_FALLBACK_PROJECT` | Project used when the LLM can't tell, or when the project it picks isn't on the page or can't take Bugs. |
| `JIRA_ROUTING_PAGE` | Optional: the Confluence page with the pillars, pods and their Jira projects. Default: the ENG space overview. |
| `JIRA_PROJECTS` | Optional: extra projects on top of the page, as `KEY: what it owns`, one per line or separated by `;`. |
| `JIRA_URL` | Optional: the Atlassian site (default https://datarobot.atlassian.net). |
| `LLM_MODEL_GENERATE`, `LLM_MODEL_REPORTS` | Optional: LLM Gateway models. Empty = the strongest Claude model for generating and a fast one for reports, from the gateway catalog. |

The LLM Gateway is called with the app's own DataRobot API token, so it needs no key of its own.

### The Atlassian service account

Learners' reports are always filed as issue type **Bug**. Before filing, the app checks that the project the LLM picked
is named on the routing page, exists and takes Bugs; if not, the bug goes to `JIRA_FALLBACK_PROJECT`.

The service account needs read access to the routing page, and, in every project bugs can go to: **Browse projects**, **Create issues**, **Create attachments**,
**Modify reporter** (to set the learner as reporter; without it the app files the bug in its own name and adds the
learner's email to the description) and **Manage watchers**; **Browse users** (to find the learner's account);
and read access to PBMP and the Confluence spaces paths are created from. It reads only what it can see: restricted
pages are flagged, not read.

## Deploy or update

The app is deployed as custom application `6ac78331b1de870be92e2341` on app.datarobot.com.

1. **Registry → Application sources →** the app's source → **Create new version**. Upload every file in this
   folder, keeping the `static/` and `tools/` folders. Skip the `_backup_*` folders and `__pycache__/`. Keep the same base environment.
2. **Runtime parameters:** keep `PROGRESS_FILES_ID` as it is (that's where everyone's progress lives). For Jira, set
   `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECTS` and `JIRA_FALLBACK_PROJECT` (see "Runtime parameters").
   Set `MANAGER_EMAILS` to, for example,
   `lidiia.saakian@datarobot.com,andrew.velihotskyi@datarobot.com,raghavendran.nehru@datarobot.com`.
   For Slack, set `SLACK_WEBHOOK_URL` (see below) and `APP_URL` (the app's address, so messages link back to it).
3. Rebuild the application from the new source version, then open `<app URL>/api/health`: it should show
   `"storage": "datarobot-files"`, your `progressFilesId`, the number of steps per path, `"jira": {"connected": true, …}`,
   the LLM models in use (`"llm"`, with the gateway catalog) and no `problems`.
4. **Share:** Applications → actions menu → **Share**. For anyone with a datarobot.com email, turn on external
   sharing and allow the `datarobot.com` domain.

## Setting up Slack

1. In Slack, create an incoming webhook for the channel that should receive the messages
   (api.slack.com/apps → your app → **Incoming Webhooks** → **Add New Webhook to Workspace** → pick the channel).
   Your Slack admin may need to approve the app.
2. Copy the webhook URL (`https://hooks.slack.com/services/...`) into the `SLACK_WEBHOOK_URL` runtime parameter.
3. Restart the app. `api/health` shows `"slack": true`, and the next problem report appears in the channel.

### Slack DMs (`SLACK_BOT_TOKEN`)

1. In the same Slack app, open **OAuth & Permissions** and add the bot scopes `chat:write`, `users:read` and
   `users:read.email`. Reinstall the app to the workspace (your Slack admin may need to approve the new scopes).
2. Copy the **Bot User OAuth Token** (`xoxb-...`). In DataRobot, save it as an API-token credential and pick that
   credential for the `SLACK_BOT_TOKEN` runtime parameter.
3. Restart the app. `api/health` shows `"slackBot": true`. The app finds each person in Slack by their email, so their
   DataRobot email has to match their Slack email.

The weekly summary posts once per week, from Monday 09:00 Dublin time (or as soon as the app is running after that).
The first week after Slack is set up is skipped, so a new deploy never posts a surprise summary.

## How it works

- **Who is viewing:** DataRobot's application proxy adds `X-DataRobot-User-Id` and a visitor-scoped API key
  (`X-DATAROBOT-API-KEY`) for DataRobot users; the app reads their name and email from `api/v2/account/info/`.
  People who open an externally shared link arrive with `X-USER-EMAIL`. A learner who uses both ways in keeps
  one record: the app matches an existing record by user id first, then by email.
- **Where progress lives:** one JSON file per learner (`progress/<key>.json`) in the DataRobot Files item
  `PROGRESS_FILES_ID`, written with the app owner's credentials and batched every 5 seconds. The Agentic path
  keeps its original place in each file (`state`), so progress saved before the hub existed carries over. Other
  paths are stored under `paths.<path id>`.
- **Who sees the admin features:** system admins (`MANAGER_EMAILS`), admins and authors invited on the Users tab, and
  each path's owners for their own paths. Roles are read on every request.
- **Paths made in the app:** one document per path (`docs/path-<id>.json`) with the draft, the live version and the
  owners. Publishing copies the draft to live. Step ids never change, so learners' ticks survive edits.
- **Uploads** (bug screenshots, source files) are kept in the container's temp folder for up to 3 hours; files of a
  bug that couldn't go to Jira, and of reports to the system admins, are stored in the Files item (`blobs/`).
- **Jobs** (reading sources, generating, LLM edits) run in the background and are kept in memory for an hour, so the
  app must run as a single instance.
- **Other data:** problem reports, uploaded content and bookkeeping are JSON files under `docs/` in the same Files item.
- **Old links:** the first version of the app served the Agentic path at `/`. That URL now opens the hub; the
  Agentic path is one click away, and its saved progress is unchanged.

## Run locally

```bash
pip install -r requirements.txt
./start-app.sh            # http://localhost:8080 ; you are "Local developer" and an admin
```

Without `DATAROBOT_ENDPOINT` and `DATAROBOT_API_TOKEN` the app stores progress in `./data`.

## Fonts

The pages ask for the brand faces (STK Miso, Monument Grotesk Mono) first and fall back to Barlow and DM Mono
from Google Fonts. To use the brand faces, add the licensed font files to `static/` and declare them with
`@font-face` in the first `<style>` block of `static/agentic/index.html`, then run `tools/build_pages.py`.
