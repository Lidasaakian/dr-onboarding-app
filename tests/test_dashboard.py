"""What the home dashboard gets from api/summary (specs learner-dashboard, learning-streaks)."""

from conftest import make_path

ME = {"x-user-email": "dash@example.com"}
OTHER = {"x-user-email": "someone.else@example.com"}


def summary(client, headers=ME):
    return client.get("/api/summary", headers=headers).json()


def step_ids(client, pid):
    live = client.get(f"/api/admin/paths/{pid}").json()["path"]["live"]
    return [st["id"] for g in live["groups"] for d in g["days"] for st in d["steps"]]


def test_ticking_records_a_learning_day_that_unticking_keeps(client, app_module):
    pid = make_path(client, "Streak path", steps=2)
    client.put(f"/{pid}/api/enroll", headers=ME, json={})
    a, _ = step_ids(client, pid)
    client.put(f"/{pid}/api/progress", headers=ME, json={"state": {"done": {a: 1}}})
    s = summary(client)["streak"]
    assert s["lastDay"] == app_module.today().isoformat()
    client.put(f"/{pid}/api/progress", headers=ME, json={"state": {"done": {}}})
    assert summary(client)["streak"]["lastDay"] == app_module.today().isoformat()


def test_checklist_tick_is_a_learning_day(client, app_module):
    pid = make_path(client, "Streak checks", steps=1)
    headers = {"x-user-email": "checks@example.com"}
    client.put(f"/{pid}/api/enroll", headers=headers, json={})
    client.put(f"/{pid}/api/progress", headers=headers, json={"state": {"done": {}, "checks": {"s1": {"0": 1}}}})
    assert summary(client, headers)["streak"]["lastDay"] == app_module.today().isoformat()


def test_my_reports_are_only_mine(client, app_module):
    me_id = client.get("/agentic/api/me", headers=ME).json()["id"]
    app_module.docs.put("reports", [
        {"id": "m1", "kind": "bug", "learnerId": me_id, "email": "dash@example.com", "path": "agentic", "pathTitle": "Agentic",
         "message": "Broken wizard", "createdAt": 2, "status": "open", "jira": {"key": "DR-1", "url": "https://x/DR-1", "status": "Open"},
         "files": [{"name": "secret.png"}]},
        {"id": "o1", "kind": "path", "learnerId": "someone-else", "email": "someone.else@example.com", "path": "agentic",
         "message": "Not mine", "createdAt": 3, "status": "open"},
    ])
    mine = summary(client)["myReports"]
    assert [r["id"] for r in mine] == ["m1"]
    assert mine[0]["jira"] == {"key": "DR-1", "url": "https://x/DR-1", "status": "Open"}
    assert "files" not in mine[0] and "email" not in mine[0]
