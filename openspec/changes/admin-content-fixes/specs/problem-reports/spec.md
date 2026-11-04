# Spec Delta

## Purpose

Defines how admins and path owners handle problem reports and DataRobot bug reports in Admin → Problem reports:
listing them, resolving and reopening them, and how that interacts with the Jira sync.

## ADDED Requirements

### Requirement: Resolve any report by hand
Every report in Admin → Problem reports, including a DataRobot bug that has a Jira issue, SHALL offer **Mark
resolved** while open and **Reopen** while resolved, to the people who can see that report.

#### Scenario: Resolving a Jira bug by hand
- **WHEN** an admin clicks Mark resolved on a DataRobot bug whose Jira issue is still open
- **THEN** the report moves to Resolved and shows who resolved it and when

#### Scenario: Reopening a Jira bug by hand
- **WHEN** an admin clicks Reopen on a resolved DataRobot bug
- **THEN** the report moves back to Open

### Requirement: Manual status wins over the Jira sync
Once someone resolves or reopens a report by hand, the Jira sync SHALL NOT change that report's status. Reports
nobody has changed by hand SHALL keep following their Jira issue: resolved when it's done, reopened when a done
issue reopens.

#### Scenario: Sync after a manual resolve
- **WHEN** a bug was marked resolved by hand and the Jira sync runs while its Jira issue is still open
- **THEN** the report stays resolved

#### Scenario: Sync after a manual reopen
- **WHEN** a bug was reopened by hand and the Jira sync runs while its Jira issue is done
- **THEN** the report stays open

#### Scenario: Bug nobody touched
- **WHEN** the Jira sync runs and a bug's Jira issue has become done
- **THEN** the report is resolved by "Jira", as before
