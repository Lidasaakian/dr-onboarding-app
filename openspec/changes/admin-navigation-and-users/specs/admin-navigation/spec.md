# Spec Delta

## Purpose

Defines how admins and authors move between the Admin tabs and the learning path pages they open from them, so they
can always get back to the tab they were working in.

## ADDED Requirements

### Requirement: Back to the Admin tab a path was opened from
A path page opened from an Admin tab SHALL show a back link to that tab, named after it (for example "← Admin ·
Problem reports"), on built-in and app-made paths. A path page opened any other way SHALL keep its usual back link.

#### Scenario: From Problem reports
- **WHEN** an admin clicks Edit this step on a report in Admin → Problem reports and then clicks the path's back link
- **THEN** Admin → Problem reports opens

#### Scenario: From Team progress
- **WHEN** an admin opens a path from Admin → Team progress
- **THEN** the path's back link reads "← Admin · Team progress"

#### Scenario: Opened from the hub
- **WHEN** someone opens the same path from the hub
- **THEN** the back link doesn't point to Admin

### Requirement: Edit mode still returns to Content
In edit mode the back link SHALL read "← Content" and open Admin → Content; leaving edit mode SHALL bring back the
link the page had before.

#### Scenario: Leaving edit mode
- **WHEN** an admin opens a path from Admin → Team progress, enters edit mode and leaves it again
- **THEN** the back link reads "← Admin · Team progress" again
