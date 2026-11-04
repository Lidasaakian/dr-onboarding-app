"""Sharing stats with others on the same path (spec stats-sharing)."""

from conftest import make_path

A = {"x-user-email": "ana.share@example.com"}
B = {"x-user-email": "ben.private@example.com"}
C = {"x-user-email": "cara.viewer@example.com"}
OUT = {"x-user-email": "olga.outsider@example.com"}


def setup(client, title):
    pid = make_path(client, title, steps=2)
    for who in (A, B, C):
        client.put(f"/{pid}/api/enroll", headers=who, json={})
    return pid


def test_off_by_default_and_only_sharers_listed(client):
    pid = setup(client, "Share one")
    assert client.get(f"/{pid}/api/status", headers=A).json()["sharing"] is False
    assert client.get(f"/{pid}/api/peers", headers=C).json()["peers"] == []
    r = client.put(f"/{pid}/api/sharing", headers=A, json={"share": True})
    assert r.json()["status"]["sharing"] is True
    peers = client.get(f"/{pid}/api/peers", headers=C).json()["peers"]
    assert [p["name"] for p in peers] == ["Ana Share"]
    assert set(peers[0]) == {"name", "done", "total", "streak", "finished", "section"}


def test_switching_off_and_leaving_remove_from_list(client):
    pid = setup(client, "Share two")
    client.put(f"/{pid}/api/sharing", headers=A, json={"share": True})
    client.put(f"/{pid}/api/sharing", headers=B, json={"share": True})
    client.put(f"/{pid}/api/sharing", headers=A, json={"share": False})
    client.put(f"/{pid}/api/enroll", headers=B, json={"leave": True})
    assert client.get(f"/{pid}/api/peers", headers=C).json()["peers"] == []


def test_only_enrolled_learners(client):
    pid = setup(client, "Share three")
    assert client.get(f"/{pid}/api/peers", headers=OUT).status_code == 403
    assert client.put(f"/{pid}/api/sharing", headers=OUT, json={"share": True}).status_code == 400


def test_section_not_step_title(client):
    pid = setup(client, "Share four")
    client.put(f"/{pid}/api/sharing", headers=A, json={"share": True})
    peer = client.get(f"/{pid}/api/peers", headers=C).json()["peers"][0]
    assert peer["section"] == "Week 1 · Day 1"  # the section, not the step title after the colon
