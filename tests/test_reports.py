"""Resolving DataRobot bugs by hand and the Jira sync (spec problem-reports)."""

import types

import pytest


class StubJira:
    enabled = True

    def __init__(self, category):
        self.category = category

    def statuses(self, keys):
        return {k: {"category": self.category, "status": "Done" if self.category == "done" else "Open"} for k in keys}


def bug(rid, status="open", **extra):
    return {"id": rid, "kind": "bug", "status": status, "path": "admin", "message": "broken", "createdAt": 1,
            "jira": {"key": f"DR-{rid}"}, **extra}


@pytest.fixture
def reports(app_module, monkeypatch):
    def seed(*rs, jira="indeterminate"):
        app_module.docs.put("reports", list(rs))
        monkeypatch.setattr(app_module, "atl", StubJira(jira))
    return seed


def status_of(app_module, rid):
    return next(r for r in app_module.docs.get("reports", []) if r["id"] == rid)["status"]


def test_jira_bug_resolved_by_hand_stays_resolved(client, app_module, reports):
    reports(bug("b1"), jira="indeterminate")
    r = client.post("/api/reports/b1", json={"status": "resolved"})
    assert r.status_code == 200 and r.json()["report"]["status"] == "resolved"
    app_module.sync_jira()
    assert status_of(app_module, "b1") == "resolved"


def test_jira_bug_reopened_by_hand_stays_open(client, app_module, reports):
    reports(bug("b2", status="resolved", autoResolved=True, resolvedBy="Jira"), jira="done")
    assert client.post("/api/reports/b2", json={"status": "open"}).json()["report"]["status"] == "open"
    app_module.sync_jira()
    assert status_of(app_module, "b2") == "open"


def test_untouched_bug_follows_jira(app_module, reports):
    reports(bug("b3"), jira="done")
    app_module.sync_jira()
    assert status_of(app_module, "b3") == "resolved"
    app_module.atl.category = "indeterminate"
    app_module.sync_jira()
    assert status_of(app_module, "b3") == "open"
