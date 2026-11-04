# Spec Delta

## Purpose

Defines how admins find and filter people in Admin → Users when assigning roles.

## ADDED Requirements

### Requirement: Role filter as a dropdown
Admin → Users SHALL offer one dropdown with All, Admins, Authors and No role, each with its count, instead of
separate buttons.

#### Scenario: Only authors
- **WHEN** an admin picks "Authors (3)" in the dropdown
- **THEN** the list shows only the three users with the Author role

### Requirement: Search users
Admin → Users SHALL have a search box that narrows the list, as the admin types, to users whose name or email
contains the text, ignoring case, combined with the role filter. Typing SHALL NOT lose focus or the cursor position.

#### Scenario: Searching by name
- **WHEN** an admin types "maria" with the dropdown on All
- **THEN** only users whose name or email contains "maria" are listed

#### Scenario: Nothing matches
- **WHEN** the search and the role filter match nobody
- **THEN** the list says no users match
