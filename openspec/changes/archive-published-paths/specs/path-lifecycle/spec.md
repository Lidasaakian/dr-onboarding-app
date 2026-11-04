# Spec Delta

## Purpose

Defines the states a learning path made in the app goes through (generating, failed, draft, published, archived) and
what each allows: who sees it, who can enroll and tick, who can edit, delete, archive and restore it.

## ADDED Requirements

### Requirement: Archive a published path
The owners of a published path and admins SHALL be able to archive it from Admin → Content, after a confirmation.
Built-in paths SHALL NOT be archivable.

#### Scenario: Owner archives a path
- **WHEN** an owner clicks Archive on a published path in Admin → Content and confirms
- **THEN** the path shows as Archived in Admin → Content

#### Scenario: Built-in path
- **WHEN** an admin looks at the AI Engineer or Agentic row in Admin → Content
- **THEN** there is no Archive action

### Requirement: Restore an archived path
Owners and admins SHALL be able to restore an archived path, which makes it published again with the same content.

#### Scenario: Restore
- **WHEN** an owner clicks Restore on an archived path
- **THEN** the path is published again, appears on the hub, and takes new enrollments

### Requirement: Archived paths are closed to newcomers
An archived path SHALL NOT appear on the hub for learners who aren't enrolled in it, and SHALL refuse new
enrollments.

#### Scenario: Learner who never enrolled
- **WHEN** a learner who never enrolled opens the hub
- **THEN** the archived path isn't listed

#### Scenario: Enrolling in an archived path
- **WHEN** someone opens an archived path's page directly and tries to enroll
- **THEN** enrolling is refused and the page says new enrollments are closed

### Requirement: Archived paths are read-only for enrolled learners
Learners already enrolled SHALL still see an archived path on the hub and open it, with their ticks, badge and
certificate, but SHALL NOT be able to change their ticks. The path page SHALL say it's archived.

#### Scenario: Enrolled learner opens an archived path
- **WHEN** an enrolled learner opens an archived path
- **THEN** they see their progress and a note that the path is archived, and the step checkboxes can't be changed

#### Scenario: Saving ticks is refused
- **WHEN** a request tries to save ticks on an archived path
- **THEN** it's refused and the stored ticks don't change

#### Scenario: Certificate of an archived path
- **WHEN** someone opens the verify link of a certificate for an archived path
- **THEN** the certificate still verifies

### Requirement: Archived paths leave the dashboard
The dashboard SHALL leave archived paths out. Team progress SHALL keep showing them, marked as archived.

#### Scenario: Dashboard
- **WHEN** an admin opens the dashboard after a path is archived
- **THEN** the archived path's numbers aren't shown

### Requirement: Only unpublished paths can be deleted
Drafts, failed and generating paths SHALL be deletable by their owners and admins. Published and archived paths
SHALL NOT be deletable, and archived paths SHALL NOT be editable until restored.

#### Scenario: Deleting an archived path
- **WHEN** a request tries to delete an archived path
- **THEN** it's refused
