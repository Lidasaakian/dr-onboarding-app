# Spec Delta

## Purpose

Defines what Admin → Content offers for each learning path, how admins undo in-app edits of the built-in paths, and
how authors move between a path's editor and Admin → Content.

## ADDED Requirements

### Requirement: One list of paths
Admin → Content SHALL list every path the visitor manages in one table, with an Edit action for each. It SHALL NOT
show separate cards for the built-in paths or offer uploading, downloading or replacing their content from files.

#### Scenario: Admin opens Content
- **WHEN** an admin opens Admin → Content
- **THEN** AI Engineer and Agentic appear as rows in the paths table with Edit, and no built-in path cards are shown

#### Scenario: Edit a built-in path
- **WHEN** an admin clicks Edit on the AI Engineer row
- **THEN** the AI Engineer path opens in edit mode

### Requirement: Saved edits of built-in paths stay live
Content saved for a built-in path, by an in-app edit or an earlier upload, SHALL stay what learners see.

#### Scenario: After this change is deployed
- **WHEN** a built-in path has saved edits and the new version of the app starts
- **THEN** learners see the edited content, not the deployed files

### Requirement: Undo all edits of a built-in path
While a built-in path with saved edits is in edit mode, admins SHALL see **Go back to the deployed version** in the
edit bar. After a confirmation it SHALL make the deployed files live again.

#### Scenario: Going back
- **WHEN** an admin clicks Go back to the deployed version on an edited built-in path and confirms
- **THEN** the page reloads showing the deployed content, and learners see the deployed content too

#### Scenario: Nothing to undo
- **WHEN** a built-in path shows its deployed version
- **THEN** the edit bar doesn't show Go back to the deployed version

### Requirement: Back to Content from edit mode
On every path page in edit mode, the back link SHALL read "← Content" and open Admin → Content. Outside edit mode,
including Preview as learner, it SHALL read "← All learning paths" and open the hub.

#### Scenario: Leaving a draft
- **WHEN** an author editing a draft clicks the back link
- **THEN** Admin → Content opens

#### Scenario: Learner view
- **WHEN** a learner on a path page clicks the back link
- **THEN** the hub opens
