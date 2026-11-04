# Spec Delta

## Purpose

Defines how the app records the days a learner learned something and turns them into the current and best streak.

## ADDED Requirements

### Requirement: Learning days
A day SHALL count as a learning day when the learner ticks a step or a checklist item in any path. Learning days
SHALL be kept even if the learner later unticks the step.

#### Scenario: Ticking then unticking
- **WHEN** a learner ticks a step on Tuesday and unticks it on Wednesday
- **THEN** Tuesday still counts as a learning day

### Requirement: Streaks count working days
The current streak SHALL be the number of consecutive working days (Monday to Friday) with a learning day, ending
today or, if the learner hasn't learned yet today, the previous working day. Saturdays and Sundays SHALL neither
count nor break a streak. The best streak SHALL be the longest such run ever.

#### Scenario: Over a weekend
- **WHEN** a learner learned on Thursday, Friday and Monday, and it's Monday
- **THEN** the current streak is 3

#### Scenario: Not yet today
- **WHEN** a learner learned on Tuesday and Wednesday and it's Thursday morning with no tick yet
- **THEN** the current streak is 2

#### Scenario: A missed day
- **WHEN** a learner learned on Monday and Wednesday but not Tuesday, and it's Wednesday
- **THEN** the current streak is 1

### Requirement: Progress saved before streaks existed
Ticks saved before this change SHALL count as learning days on the day they were ticked.

#### Scenario: Older ticks
- **WHEN** a learner's record has ticks from last week but no recorded learning days
- **THEN** the days of those ticks count toward the best streak
