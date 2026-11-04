# Spec Delta

## ADDED Requirements

### Requirement: Links open in the working area when their site allows it
On a wide screen, a learner's click on a link in a path's content SHALL open it in the working area beside the steps
when the linked site allows being shown inside another page. Links to sites that refuse SHALL open in a new tab.
Clicks with a modifier key or the middle button SHALL keep the browser's own behavior.

#### Scenario: Docs that allow framing
- **WHEN** a learner clicks a step's link to docs.datarobot.com
- **THEN** the page opens in the working area beside the steps

#### Scenario: A site that refuses
- **WHEN** a learner clicks a step's link to anthropic.skilljar.com
- **THEN** it opens in a new tab, and the path page notes that this site can't be shown inside the path

#### Scenario: Ctrl or Cmd click
- **WHEN** a learner Ctrl-clicks a step link
- **THEN** the browser opens it in a background tab as usual

### Requirement: Videos play in the working area
YouTube (watch, youtu.be and shorts links) and Vimeo links SHALL open in the site's own video player inside the
working area, with fullscreen allowed.

#### Scenario: YouTube watch link
- **WHEN** a learner clicks a link to https://www.youtube.com/watch?v=abc123
- **THEN** the working area plays it through https://www.youtube.com/embed/abc123

### Requirement: The toolbar shows where the working area is
The working area's toolbar SHALL show the site of the page it's showing. Back and forward SHALL be available for
DataRobot pages; reload and Open in new window SHALL be available for every page.

#### Scenario: Docs page
- **WHEN** the working area shows a page from docs.python.org
- **THEN** the toolbar shows docs.python.org, with reload and Open in new window

### Requirement: Only public links are checked
To decide whether a site can be shown, the app SHALL only contact public http and https addresses, including after
redirects, and SHALL treat anything else as "open in a new tab". The answer for a link SHALL be remembered for a day.

#### Scenario: A link to a private address
- **WHEN** a step links to http://10.0.0.5/admin
- **THEN** the app doesn't contact it, and the link opens in a new tab

### Requirement: Open the working area from the rail
The working area SHALL open from a single icon button on a slim rail at the right edge of the path's working area,
not from an "Open DataRobot" button among the page's tools. It SHALL open on the page it showed last, or DataRobot the
first time. While it's open, its toolbar's first, highlighted button SHALL close it and bring the rail back.

#### Scenario: Opening and closing
- **WHEN** a learner clicks the rail's button, then the highlighted first button of the toolbar
- **THEN** the working area opens on the page it showed last, then closes and the rail is shown again

#### Scenario: No text button
- **WHEN** a learner looks at a path's top tools
- **THEN** there is no "Open DataRobot" button; the rail's icon opens the working area

### Requirement: Working area toolbar and frame
The working area's toolbar SHALL use icon buttons: close, back and forward (DataRobot pages), reload, and Open in a
new window on the far right. The page SHALL be shown in a bordered, rounded area.

#### Scenario: Toolbar on a DataRobot page
- **WHEN** the working area shows a DataRobot page
- **THEN** the toolbar shows close, back, forward and reload icons on the left and an open-in-new-window icon on the right
