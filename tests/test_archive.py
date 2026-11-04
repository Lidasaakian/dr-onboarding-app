"""Archiving and restoring published paths (spec path-lifecycle)."""

from conftest import make_path

ENROLLED = {"x-user-email": "enrolled@example.com"}
NEWCOMER = {"x-user-email": "newcomer@example.com"}


def hub_ids(client, headers):
    return [p["id"] for p in client.get("/api/summary", headers=headers).json()["paths"]]


def archived_path(client, title):
    pid = make_path(client, title, steps=2)
    client.put(f"/{pid}/api/enroll", headers=ENROLLED, json={})
    assert client.post(f"/api/admin/paths/{pid}/archive").json()["status"] == "archived"
    return pid


def test_archive_hides_from_newcomers_and_closes_enrollment(client):
    pid = archived_path(client, "Archive hub")
    assert pid not in hub_ids(client, NEWCOMER)
    assert pid in hub_ids(client, ENROLLED)
    r = client.put(f"/{pid}/api/enroll", headers=NEWCOMER, json={})
    assert r.status_code == 409 and "closed" in r.json()["detail"]
    status = client.get(f"/{pid}/api/status", headers=ENROLLED).json()
    assert status["archived"] is True and status["enrolled"] is True


def test_archived_path_is_read_only(client):
    pid = archived_path(client, "Archive read only")
    r = client.put(f"/{pid}/api/progress", headers=ENROLLED, json={"state": {"done": {"x": 1}}})
    assert r.status_code == 409
    assert client.put(f"/{pid}/api/enroll", headers=ENROLLED, json={"leave": True}).status_code == 200


def test_archived_path_leaves_dashboard_but_stays_in_team_progress(client):
    pid = archived_path(client, "Archive dashboard")
    assert pid not in client.get("/api/dashboard").json()["paths"]
    paths = {p["id"]: p for p in client.get("/api/team-summary").json()["paths"]}
    assert paths[pid]["archived"] is True


def test_archived_path_cannot_be_edited_or_deleted_until_restored(client):
    pid = archived_path(client, "Archive restore")
    assert client.put(f"/api/admin/paths/{pid}/draft", json={"content": {"title": "x"}}).status_code == 409
    assert client.delete(f"/api/admin/paths/{pid}").status_code == 400
    assert client.post(f"/api/admin/paths/{pid}/restore").json()["status"] == "published"
    assert pid in hub_ids(client, NEWCOMER)
    assert client.put(f"/{pid}/api/enroll", headers=NEWCOMER, json={}).status_code == 200


def test_only_published_paths_archive_and_built_ins_refuse(client):
    draft = make_path(client, "Archive draft", publish=False)
    assert client.post(f"/api/admin/paths/{draft}/archive").status_code == 400
    assert client.post("/api/admin/paths/ai-engineer/archive").status_code == 404
    assert client.post(f"/api/admin/paths/{draft}/restore").status_code == 400


def test_published_path_still_cannot_be_deleted(client):
    pid = make_path(client, "Archive no delete")
    assert client.delete(f"/api/admin/paths/{pid}").status_code == 400
