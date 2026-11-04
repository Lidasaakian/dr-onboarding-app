# Spec Delta

## Purpose

Defines how a learning path made in the app is organized and scheduled: its cadence, the names of its levels,
numbered and unnumbered sections, and how that structure maps to what learners see about their pace.

## ADDED Requirements

### Requirement: Cadence
Every path made in the app SHALL have exactly one cadence: calendar weeks, working days, or self-paced. The cadence
SHALL decide how the learner's schedule is calculated and SHALL be changeable by the path's owners and admins in the
path's Settings.

#### Scenario: Author picks working days
- **WHEN** an author sets a path's cadence to working days and saves
- **THEN** the path's schedule counts working days from each learner's start date

#### Scenario: Author picks self-paced
- **WHEN** an author sets a path's cadence to self-paced and saves
- **THEN** the path has no schedule and learners are never shown as behind or ahead

### Requirement: Level names
A path SHALL have a top level and an optional second level. The author SHALL be able to name each level, choosing
Week, Day, Module or Phase, or typing a custom name. The second level SHALL be optional, and when present SHALL
appear inside every top-level section.

#### Scenario: Modules inside weeks
- **WHEN** an author sets the top level to "Week" and the second level to "Module"
- **THEN** the learner page and the editor show sections as "Week 1", "Week 2" and, inside each, "Module 1", "Module 2"

#### Scenario: No second level
- **WHEN** an author sets the second level to none
- **THEN** each top-level section holds its steps directly, with no sub-sections

#### Scenario: Custom level name
- **WHEN** an author types "Sprint" as the top-level name
- **THEN** sections are labelled "Sprint 1", "Sprint 2" everywhere the path's sections are named

### Requirement: Labels follow the cadence
When an author changes the cadence and a level name is still the default for the previous cadence, the system SHALL
change that level name to the new cadence's default. Level names the author customized SHALL be kept.

#### Scenario: Switching weeks to working days with default names
- **WHEN** a path with cadence calendar weeks, top level "Week" and second level "Day" is switched to working days
- **THEN** the top level becomes "Day", the second level becomes none, and learners see "Day 1", "Day 2"

#### Scenario: Custom names survive a cadence change
- **WHEN** a path whose top level is named "Module" is switched from calendar weeks to self-paced
- **THEN** the top level stays "Module"

### Requirement: Unnumbered sections
An author SHALL be able to mark any top-level section as unnumbered and give it its own title, such as
"Prerequisites" or "Before you start". An unnumbered section SHALL be shown by its title only and SHALL NOT count
toward the numbering of the other sections.

#### Scenario: Path starts with Before you start
- **WHEN** a path has an unnumbered section "Before you start" followed by two numbered sections with top level "Week"
- **THEN** learners see "Before you start", "Week 1", "Week 2", in that order

#### Scenario: Unnumbered section in the middle
- **WHEN** an unnumbered section "Midpoint review" sits between the second and third numbered sections
- **THEN** the numbered sections are still labelled 1, 2 and 3

### Requirement: Schedule mapping
For calendar weeks, each numbered top-level section SHALL be one week. For working days, each second-level section
SHALL be one working day, or each numbered top-level section when there is no second level. An unnumbered section
SHALL be scheduled with the next numbered section, or with the last one when none follows.

#### Scenario: Before you start belongs to week 1
- **WHEN** a learner on a calendar-weeks path has not finished the required steps in "Before you start" at the end of their first week
- **THEN** their pace shows them as behind, the same as for unfinished Week 1 steps

#### Scenario: Days inside weeks with working-days cadence
- **WHEN** a path has cadence working days, top level "Week" and second level "Day", with 5 days in each of 2 weeks
- **THEN** the schedule spans 10 working days and Week 2, Day 1 is due on working day 6

### Requirement: Self-paced progress
On a self-paced path, the learner's header, the hub and the team views SHALL show progress (steps done out of the
total, and required steps done) instead of a schedule status. Self-paced learners SHALL NOT be counted as on track,
behind or ahead in the dashboard.

#### Scenario: Learner on a self-paced path
- **WHEN** an enrolled learner opens a self-paced path
- **THEN** the header shows their progress, such as "12 of 40 steps", and no "behind" or "on track" label

#### Scenario: Dashboard counts
- **WHEN** the dashboard counts learners on track and behind
- **THEN** learners on self-paced paths are left out of both counts

### Requirement: Existing paths keep working
Paths created before this change SHALL open with an equivalent structure: their pace as the cadence, their level as
the top-level name, a "Day" second level if they had days, and every section numbered. Step ids SHALL NOT change, so
learners' ticks, stars, badges and certificates stay as they were.

#### Scenario: Old two-week path
- **WHEN** a path stored with pace "weeks", level "Week" and days inside is opened after the change
- **THEN** it shows cadence calendar weeks, top level "Week", second level "Day", and every learner's progress is unchanged

### Requirement: Removing the second level keeps steps
When an author removes the second level from a path that has steps in several sub-sections, the system SHALL ask for
confirmation and SHALL then move all steps of each top-level section into that section, in their existing order,
without changing step ids.

#### Scenario: Remove days from a week
- **WHEN** an author sets the second level to none on a path whose Week 1 has 3 days of steps, and confirms
- **THEN** Week 1 holds all those steps in the same order and learners' ticks on them are kept

### Requirement: Structure in the spreadsheet template
The .xlsx template, path export and import SHALL carry the cadence, both level names, and which sections are
unnumbered, so a path exported and imported again has the same structure.

#### Scenario: Round trip through .xlsx
- **WHEN** an author downloads a path with an unnumbered "Prerequisites" section as .xlsx and imports that file as a new path
- **THEN** the new path has the same cadence, level names, sections, numbering and steps
