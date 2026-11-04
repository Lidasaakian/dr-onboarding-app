# Spec Delta

## Purpose

Defines how a learner works through a path next to DataRobot: the Open DataRobot button on every path page, the
DataRobot window it opens beside the path, and how DataRobot links in steps open in that window.

## ADDED Requirements

### Requirement: Open DataRobot from any path
Every path page (built-in and app-made) SHALL show an **Open DataRobot** button with the page's top tools, for every
visitor, enrolled or not.

#### Scenario: Learner opens DataRobot
- **WHEN** a learner clicks Open DataRobot on a path page
- **THEN** DataRobot opens in a separate window, and the path page stays where it was

### Requirement: One DataRobot window, beside the path
The DataRobot window SHALL be placed beside the path window where the browser allows it, and clicking Open DataRobot
again SHALL bring the same window to the front instead of opening another one. Where the browser opens it as a tab
instead (for example on phones), the button SHALL still work.

#### Scenario: Clicking twice
- **WHEN** a learner clicks Open DataRobot, goes back to the path, and clicks it again
- **THEN** the same DataRobot window comes to the front; no second window opens

### Requirement: DataRobot links open in the DataRobot window
Links in steps that point to the DataRobot application (the same DataRobot site the onboarding app runs on, or
app.datarobot.com when it runs elsewhere) SHALL open in the DataRobot window. Other links, including
docs.datarobot.com, SHALL keep opening in a new tab.

#### Scenario: A step links to a DataRobot page
- **WHEN** a learner clicks a step's link to a page on app.datarobot.com
- **THEN** that page opens in the DataRobot window beside the path

#### Scenario: A step links to the docs
- **WHEN** a learner clicks a step's link to docs.datarobot.com
- **THEN** it opens in a new tab as before

### Requirement: The right DataRobot site
The button SHALL open the DataRobot site the onboarding app is served from; when the app isn't served from a
DataRobot site (for example running locally), it SHALL open https://app.datarobot.com/.

#### Scenario: App on app.datarobot.com
- **WHEN** the onboarding app runs at https://app.datarobot.com/custom_applications/…
- **THEN** Open DataRobot opens https://app.datarobot.com/
