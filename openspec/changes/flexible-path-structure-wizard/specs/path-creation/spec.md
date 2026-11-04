# Spec Delta

## Purpose

Defines how admins and authors create a new learning path in the app: the guided wizard, optional sources, LLM
generation that runs in the background, and the draft it produces.

## ADDED Requirements

### Requirement: One guided creation flow
"+ Create learning path" SHALL open a single wizard with these steps in order: Basics, Structure, Sources, Review,
Generate. A progress indicator SHALL show the current step. There SHALL be no separate choice between building by
hand and creating from sources before the wizard starts.

#### Scenario: Starting a path
- **WHEN** an author clicks "+ Create learning path" in Admin → Content
- **THEN** the wizard opens on Basics and shows all five steps with Basics as current

### Requirement: Basics step
The Basics step SHALL ask for the path name and who it's for. The name SHALL be required. Skill growth and owners
SHALL be under "More options", defaulting to "Decide later" and the author as the only owner.

#### Scenario: Missing name
- **WHEN** an author tries to continue from Basics without a name
- **THEN** the wizard stays on Basics and says the path needs a name

#### Scenario: Defaults for more options
- **WHEN** an author continues from Basics without opening "More options"
- **THEN** the path will be created with skill growth off and the author as its only owner

### Requirement: Structure step
The Structure step SHALL let the author choose the cadence, the top-level name, the second level (or none) and the
approximate length, and whether to start with a "Before you start" section. It SHALL default to calendar weeks, top
level "Week", second level "Day", and no "Before you start" section.

#### Scenario: Choosing cadence fills in the level names
- **WHEN** an author picks working days on the Structure step without having edited the level names
- **THEN** the top level changes to "Day" and the second level to none

#### Scenario: Adding a Before you start section
- **WHEN** an author turns on "Start with a Before you start section"
- **THEN** the created draft begins with an unnumbered section titled "Before you start"

### Requirement: Sources are optional
The Sources step SHALL accept links and files as today. The author SHALL be able to skip it, which creates an empty
draft with the chosen structure and opens it in the editor.

#### Scenario: Skipping sources
- **WHEN** an author clicks "Skip and start empty" on the Sources step
- **THEN** an empty draft is created with the name, cadence, level names and optional "Before you start" section from earlier steps, and the editor opens it

#### Scenario: Importing the .xlsx template
- **WHEN** the only source is a filled-in .xlsx template
- **THEN** it is imported exactly as it is, without the LLM, using the structure in the file, and the editor opens the new draft

### Requirement: Review sources before generating
After the sources are read, the Review step SHALL list what was found, let the author untick sources, and let them
add more files or links, as today. Adding more SHALL read only the new sources and keep the author's ticks on the
existing ones.

#### Scenario: Adding a link on Review
- **WHEN** an author unticks one source and then adds another link on the Review step
- **THEN** the new link's content is added to the list and the unticked source stays unticked

### Requirement: Generation follows the chosen structure
LLM generation SHALL produce a path with the cadence, level names and "Before you start" choice from the Structure
step. The LLM SHALL decide only how many sections and steps there are and what they contain.

#### Scenario: Working-days path from a Jira epic
- **WHEN** an author chooses working days with no second level and generates from a Jira epic
- **THEN** the draft has cadence working days, sections labelled "Day 1", "Day 2", and no sub-sections

### Requirement: Generation runs in the background
Once generation starts, the author SHALL be able to leave the page. Admin → Content SHALL list the path as
"Generating…" until it finishes, and the author SHALL be told when the draft is ready, in the app and in a Slack DM
when Slack DMs are set up.

#### Scenario: Leaving during generation
- **WHEN** an author starts generating and then navigates to the hub
- **THEN** generation continues, and Admin → Content shows the path as "Generating…" until the draft is ready

#### Scenario: Draft is ready
- **WHEN** generation finishes while the author is elsewhere in the app
- **THEN** the author sees a notice with a link that opens the draft

### Requirement: Failed or interrupted generation
If generation fails, or the app restarts while it runs, Admin → Content SHALL show the path as failed with the
reason and a "Try again" action that reopens the wizard with the earlier answers filled in.

#### Scenario: App restarts mid-generation
- **WHEN** the app restarts while a path is generating
- **THEN** Admin → Content shows that generation was interrupted, and "Try again" reopens the wizard on Sources with the name, structure and links filled in

### Requirement: Wizard keeps the author's work
Going back to an earlier step SHALL keep everything entered. Refreshing the page or returning to Admin → Content
SHALL offer to continue an unfinished wizard with its answers, links and uploaded files.

#### Scenario: Refresh on the Review step
- **WHEN** an author refreshes the page while on the Review step
- **THEN** Admin → Content offers "Continue creating <name>", which returns to the wizard with the same answers and sources

#### Scenario: Back from Sources
- **WHEN** an author goes back from Sources to Structure and changes the cadence
- **THEN** the name, links and files they already entered are still there

### Requirement: Generation report stays with the draft
The generation report (sources used and not used, links that didn't open, warnings) SHALL be available from the
draft until the path is published, not only on the screen shown when generation finishes.

#### Scenario: Checking the report later
- **WHEN** an owner opens a generated draft the next day
- **THEN** they can open the generation report from the draft and see which sources weren't used and which links didn't open
