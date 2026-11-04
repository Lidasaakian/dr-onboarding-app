# Spec Delta

## Purpose

Defines the formatting allowed in the details of a step on paths made in the app: how authors write it, how the
editor helps, how learners see it, and how checklist ticks are kept.

## ADDED Requirements

### Requirement: Lists in step details
Step details SHALL support bullet lists (lines starting "- "), numbered lists (lines starting "1. ", "2. "…) and
checklists (lines starting "- [ ] " or "- [x] "). Learners SHALL see them as lists; other lines stay paragraphs with
their line breaks.

#### Scenario: Bullet list
- **WHEN** a step's details contain three lines starting with "- "
- **THEN** learners see a bulleted list with three items

#### Scenario: Numbered list
- **WHEN** a step's details contain lines "1. Open Console", "2. Pick a deployment"
- **THEN** learners see a numbered list with those two items

### Requirement: Inline formatting
Step details SHALL support **bold** (`**text**`), *italic* (`*text*`), links with their own text (`[text](https://…)`),
`code` in backticks, and bare https links, inside paragraphs and list items.

#### Scenario: Link with its own text
- **WHEN** a step's details contain `[the docs](https://docs.datarobot.com/)`
- **THEN** learners see "the docs" as a link that opens https://docs.datarobot.com/ in a new tab

#### Scenario: Bold and italic
- **WHEN** a step's details contain `**Required:** read *all* of it`
- **THEN** learners see "Required:" in bold and "all" in italic

### Requirement: Nothing an author writes runs as code
Step details SHALL never be inserted into the page as HTML. Tags SHALL appear as text, and links SHALL only open
http or https addresses.

#### Scenario: HTML in details
- **WHEN** a step's details contain `<img src=x onerror=alert(1)>`
- **THEN** learners see that text literally and no script runs

#### Scenario: Script link
- **WHEN** a step's details contain `[click](javascript:alert(1))`
- **THEN** it isn't shown as a link

### Requirement: Checklist ticks are saved per learner
Enrolled learners SHALL be able to tick checklist items, and their ticks SHALL be saved with their progress and come
back on any device. Checklist ticks SHALL NOT count toward progress, pace or badges; only the step's own tick does.
Checklists SHALL be read-only in edit mode, in preview and on archived paths.

#### Scenario: Ticking a checklist item
- **WHEN** an enrolled learner ticks the second item of a step's checklist and reloads the page
- **THEN** the second item is still ticked and the step itself is not

### Requirement: Formatting toolbar in the editor
While editing a step's details, authors SHALL have buttons for bullet list, numbered list, checklist, bold, italic and
link, which add the syntax around the selection or at the cursor.

#### Scenario: Making a list
- **WHEN** an author selects three lines of details and clicks Bulleted list
- **THEN** each of the three lines starts with "- "

#### Scenario: Adding a link
- **WHEN** an author selects "the docs", clicks Link and enters https://docs.datarobot.com/
- **THEN** the details contain `[the docs](https://docs.datarobot.com/)`

### Requirement: Plain text where formatting doesn't fit
Search and problem reports SHALL use step details without the formatting syntax.

#### Scenario: Searching
- **WHEN** a learner searches for "docs" and a step's details contain `[the docs](https://…)`
- **THEN** the result shows "the docs", not the brackets and URL
