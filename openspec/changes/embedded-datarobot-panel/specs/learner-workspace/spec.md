# Spec Delta

## ADDED Requirements

### Requirement: DataRobot panel in the path page
On a wide screen, when the app is served from the DataRobot site, **Open DataRobot** SHALL open DataRobot in the
path's working area: the page header (path title, the learner's name, progress and pace) SHALL stay across the full
width at the top, and below it the steps SHALL be on the left and DataRobot on the right.

#### Scenario: Opening the panel
- **WHEN** a learner on a laptop clicks Open DataRobot on a path page served from app.datarobot.com
- **THEN** the header stays at the top at full width, and below it DataRobot appears on the right of the steps

#### Scenario: Scrolling the steps
- **WHEN** the learner scrolls down past the header
- **THEN** DataRobot fills the right side from the top of the window, and the steps scroll on the left

#### Scenario: Narrow working area
- **WHEN** less than 1000 pixels are left beside the panel
- **THEN** the list of sections moves above the steps so the steps keep a readable width

### Requirement: Panel controls
The panel SHALL have buttons to collapse it, go back, go forward, reload, and open the current DataRobot page in a new
window, and a handle on its left edge to change its width.

#### Scenario: Collapse and reopen
- **WHEN** a learner collapses the panel and clicks Open DataRobot again
- **THEN** the panel opens again on the DataRobot page it showed before

#### Scenario: Resize
- **WHEN** a learner drags the panel's left edge
- **THEN** the panel gets wider or narrower and the steps use the rest of the page

### Requirement: DataRobot links open in the panel
While the panel can be used, links in steps to the DataRobot site SHALL open in the panel, opening it if it's
collapsed.

#### Scenario: Step link
- **WHEN** a learner clicks a step's link to a DataRobot page
- **THEN** the page opens in the panel

### Requirement: The panel is remembered
The panel's open state, width and last DataRobot page SHALL be kept when the learner moves between sections of the
path and when they reload or come back to it later in the same browser.

#### Scenario: Coming back
- **WHEN** a learner who left the panel open on a Workbench page reloads the path
- **THEN** the panel is open on that Workbench page at the same width

### Requirement: The path page stays in control
DataRobot in the panel SHALL NOT be able to navigate the path page away.

#### Scenario: DataRobot tries to take over the page
- **WHEN** the page in the panel tries to navigate the whole window
- **THEN** the path page stays where it is

### Requirement: Fall back to a window
Where the panel can't be used (the app isn't served from the DataRobot site, the screen is narrower than 900 pixels,
or the page in the panel doesn't load), Open DataRobot and DataRobot links SHALL open DataRobot in the separate
window as before.

#### Scenario: Running locally
- **WHEN** the app runs on localhost and a learner clicks Open DataRobot
- **THEN** DataRobot opens in the separate window
