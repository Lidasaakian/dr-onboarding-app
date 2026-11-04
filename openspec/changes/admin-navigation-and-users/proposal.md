# Proposal

## Why

Admins and authors open paths from every Admin tab (a learner's progress in Team progress, "Edit this step" in Problem
reports, a path in Content), and the path's back arrow then takes them to the learning paths instead of back to the
tab they were working in. The Users tab shows its role filter as a row of buttons and has no way to find one person
in a long list.

## What Changes

- A path page opened from any Admin tab shows a back link to that tab ("← Admin · Problem reports"), outside edit
  mode too. Opened any other way, it keeps its usual back link. Edit mode keeps "← Content".
- Admin → Users: the All / Admins / Authors / No role buttons become one dropdown with counts, next to a search box
  that matches a user's name or email as you type.

## Capabilities

### New Capabilities
- `admin-navigation`: how admins and authors move between the Admin tabs and the path pages they open from them.
- `admin-users`: how admins find and filter people in Admin → Users.

### Modified Capabilities
- None (no specs have been archived into `openspec/specs/` yet).

## Impact

- `static/assets/common.js`: the back link on every path page; `tools/src/path.html`: its edit-mode switch uses it.
- `tools/src/admin.html`: remembers which tab a path was opened from; the Users toolbar. Built `static/` pages are
  regenerated.
