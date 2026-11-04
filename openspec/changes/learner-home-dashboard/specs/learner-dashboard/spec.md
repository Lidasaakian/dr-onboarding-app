# Spec Delta

## Purpose

Defines the learner's home page: the My dashboard tab with their progress, achievements, starred steps and reports,
and the tabs that lead to the learning path catalog and Admin.

## ADDED Requirements

### Requirement: Home page tabs
The home page SHALL have tabs **My dashboard** (shown by default), **Learning paths** and, for admins and authors
only, **Admin**. The selected tab SHALL be kept in the address (`#dashboard`, `#paths`).

#### Scenario: Learner opens the app
- **WHEN** a learner opens the home page
- **THEN** My dashboard is shown, with Learning paths as a second tab and no Admin tab

#### Scenario: Author opens the app
- **WHEN** an author opens the home page
- **THEN** an Admin tab is shown and leads to the Admin page

### Requirement: Achievements at a glance
My dashboard SHALL show the learner's current streak, paths completed, certificates earned and paths enrolled in.

#### Scenario: Learner with one finished path
- **WHEN** a learner has finished one path and is enrolled in two others
- **THEN** the dashboard shows 1 path completed, 1 certificate earned and 2 in progress

### Requirement: Paths in progress
My dashboard SHALL list the paths the learner is enrolled in and hasn't finished, with their progress, pace and the
step they're on, each with a way to continue.

#### Scenario: Continue a path
- **WHEN** a learner clicks Continue on a path in progress
- **THEN** that path opens

#### Scenario: Not enrolled anywhere
- **WHEN** a learner isn't enrolled in any path
- **THEN** the dashboard points them to the Learning paths tab

### Requirement: Certificates from the dashboard
My dashboard SHALL list the paths the learner finished, each with a link that opens its certificate.

#### Scenario: Opening a certificate
- **WHEN** a learner clicks the certificate link of a finished path
- **THEN** the path opens with its certificate dialog

### Requirement: Starred steps on the dashboard
The learner's starred steps SHALL be on My dashboard, grouped by path, and no longer below the path catalog.

#### Scenario: Starred step
- **WHEN** a learner who starred a step opens My dashboard
- **THEN** the step is listed under its path and opens it when clicked

### Requirement: My problem reports
My dashboard SHALL list the problems the learner reported, newest first, with the path, the start of the message,
when, whether it's open or resolved, and the Jira key and status for DataRobot bugs. Other people's reports SHALL NOT
be shown.

#### Scenario: Learner reported a bug
- **WHEN** a learner who filed a DataRobot bug opens My dashboard
- **THEN** the bug is listed with its Jira key and whether it's open or resolved

### Requirement: Back to the home page
Path pages SHALL link back to the home page ("← Home") unless they were opened from Admin.

#### Scenario: Back from a path
- **WHEN** a learner opens a path from the dashboard and clicks the back link
- **THEN** the home page opens
