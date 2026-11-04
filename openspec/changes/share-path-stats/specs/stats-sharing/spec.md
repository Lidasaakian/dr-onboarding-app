# Spec Delta

## Purpose

Defines how learners choose to share their progress on a learning path with others enrolled in it, and what those
others can see.

## ADDED Requirements

### Requirement: Opt in per path
Enrolled learners SHALL be able to switch sharing on and off for each path from the path page. Sharing SHALL be off
until they switch it on.

#### Scenario: Default
- **WHEN** a learner enrolls in a path
- **THEN** their stats aren't shared

#### Scenario: Switching it off
- **WHEN** a learner who shares switches sharing off
- **THEN** they no longer appear to anyone in Others on this path

### Requirement: What others see
Learners enrolled in a path SHALL see the other enrolled learners who share, with their name, progress (percent and
steps), current streak, whether they finished, and the section they're in. Learners who don't share, who left the
path or were removed SHALL NOT be listed. Emails SHALL NOT be shown.

#### Scenario: Two colleagues, one sharing
- **WHEN** a learner opens Others on this path, and of two colleagues enrolled only one shares
- **THEN** only that colleague is listed, with progress, streak, finished or not, and section

### Requirement: Only for people on the path
The list SHALL only be available to learners enrolled in the path.

#### Scenario: Not enrolled
- **WHEN** someone who isn't enrolled asks for the list
- **THEN** it's refused
