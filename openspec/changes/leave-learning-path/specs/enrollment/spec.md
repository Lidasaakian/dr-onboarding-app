# Spec Delta

## Purpose

Defines how learners enroll in a learning path, leave it, and are removed by admins, and what each does to their
progress, certificates and the team views.

## ADDED Requirements

### Requirement: Learners can leave a path
An enrolled learner SHALL see **Leave this path** on the path page. After a confirmation, the path SHALL show them as
not enrolled.

#### Scenario: Leaving
- **WHEN** an enrolled learner clicks Leave this path and confirms
- **THEN** the page shows them as not enrolled, with Enroll in this path

#### Scenario: Changing their mind
- **WHEN** a learner clicks Leave this path and cancels the confirmation
- **THEN** they stay enrolled

### Requirement: Leaving keeps progress
Leaving SHALL keep the learner's ticks, stars, skill growth, badge and certificate. A certificate already issued SHALL
still verify. Enrolling again SHALL bring their progress back.

#### Scenario: Enrolling again
- **WHEN** a learner who left with 12 steps ticked enrolls in the same path again
- **THEN** the 12 steps are still ticked and their badge, if earned, is still shown

#### Scenario: Certificate after leaving
- **WHEN** someone opens the verify link of a certificate whose holder later left the path
- **THEN** the certificate still verifies

### Requirement: Left learners leave the team views
A learner who left SHALL NOT count in Team progress, the dashboard, cohorts, inactivity reminders or the CSV export
for that path, the same as a learner an admin removed.

#### Scenario: Dashboard after leaving
- **WHEN** a learner leaves a path
- **THEN** the dashboard's enrolled count for that path goes down by one

### Requirement: Admins see who left
Admin → Team progress SHALL list learners who left a path themselves, with the path and when, separately from the
learners shown in the table. Learners an admin removed SHALL NOT appear in that list.

#### Scenario: One learner left, one was removed
- **WHEN** one learner leaves a path and an admin removes another
- **THEN** Team progress lists only the first under "Left by themselves"
