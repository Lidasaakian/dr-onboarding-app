"""Leaving a path (spec enrollment)."""

from conftest import make_path

LEARNER = {"x-user-email": "leaver@example.com"}
OTHER = {"x-user-email": "removed@example.com"}


def learner_id(client, pid, headers):
    return client.get(f"/{pid}/api/me", headers=headers).json()["id"]


def test_leave_keeps_progress_and_leaves_team_views(client):
    pid = make_path(client, "Leave check", steps=2)
    client.put(f"/{pid}/api/enroll", headers=LEARNER, json={"date": "2026-01-05"})
    state = client.get(f"/{pid}/api/progress", headers=LEARNER).json()["state"] or {}
    draft = client.get(f"/api/admin/paths/{pid}").json()["path"]["live"]
    ids = [st["id"] for g in draft["groups"] for d in g["days"] for st in d["steps"]]
    state["done"] = {ids[0]: 1793700000000, ids[1]: 1793700000000}
    assert client.put(f"/{pid}/api/progress", headers=LEARNER, json={"state": state}).status_code == 200
    assert client.get("/api/dashboard").json()["paths"][pid]["tiles"]["enrolled"] == 1

    r = client.put(f"/{pid}/api/enroll", headers=LEARNER, json={"leave": True})
    assert r.status_code == 200 and r.json()["status"]["enrolled"] is False
    assert client.get("/api/dashboard").json()["paths"][pid]["tiles"]["enrolled"] == 0
    assert not any(pid in row["paths"] and row["paths"][pid]["enrolled"] for row in client.get("/api/team-summary").json()["learners"])
    assert set((client.get(f"/{pid}/api/progress", headers=LEARNER).json()["state"] or {}).get("done") or {}) == set(ids)

    back = client.put(f"/{pid}/api/enroll", headers=LEARNER, json={"date": "2026-02-02"}).json()["status"]
    assert back["enrolled"] is True and back["done"] == 2 and back["badge"]["earned"] is True


def test_cannot_leave_when_not_enrolled(client):
    pid = make_path(client, "Leave refuse")
    assert client.put(f"/{pid}/api/enroll", headers=LEARNER, json={"leave": True}).status_code == 400


def test_team_summary_lists_only_learners_who_left(client):
    pid = make_path(client, "Leave list")
    for h in (LEARNER, OTHER):
        client.put(f"/{pid}/api/enroll", headers=h, json={})
    client.put(f"/{pid}/api/enroll", headers=LEARNER, json={"leave": True})
    client.put(f"/{pid}/api/enroll", json={"learner": learner_id(client, pid, OTHER), "remove": True})
    left = [x for x in client.get("/api/team-summary").json()["left"] if x["path"] == pid]
    assert [x["email"] for x in left] == ["leaver@example.com"]
