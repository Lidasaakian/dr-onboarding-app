"""Self-paced progress instead of a schedule (spec path-structure: Self-paced progress)."""

import datetime as dt

import custom_paths as cp
from conftest import make_path


def self_paced_model():
    c = cp.normalize({"title": "T", "cadence": "self", "levels": {"top": "Module", "sub": ""}, "groups": [
        {"title": "", "days": [{"title": "", "steps": [{"id": f"s{i}", "title": f"S{i}"} for i in range(1, 5)]}]}]})
    return cp.model({"id": "p"}, c, "")


def test_self_paced_learner_sees_progress():
    m = self_paced_model()
    p = m.pace({"done": {"s1": 1, "s2": 1}}, "2026-01-01", dt.date(2026, 6, 1))
    assert p == {"status": "self_paced", "label": "2 of 4 steps"}


def test_self_paced_finished():
    m = self_paced_model()
    done = {f"s{i}": 1 for i in range(1, 5)}
    assert m.pace({"done": done}, "2026-01-01", dt.date(2026, 6, 1))["status"] == "finished"


def test_scheduled_paths_unchanged():
    c = cp.normalize({"title": "T", "cadence": "weeks", "levels": {"top": "Week", "sub": ""}, "groups": [
        {"title": "", "days": [{"title": "", "steps": [{"id": "a", "title": "A"}]}]},
        {"title": "", "days": [{"title": "", "steps": [{"id": "b", "title": "B"}]}]}]})
    m = cp.model({"id": "p"}, c, "")
    assert m.pace({}, "2026-01-01", dt.date(2026, 1, 9))["status"] == "behind"
    assert m.pace({"done": {"a": 1}}, "2026-01-01", dt.date(2026, 1, 9))["status"] == "on_track"


def test_dashboard_leaves_self_paced_out_of_counts(client):
    pid = make_path(client, "Self paced dash", cadence="self")
    assert client.put(f"/{pid}/api/enroll", json={"date": "2025-01-01"}).status_code == 200
    tiles = client.get("/api/dashboard").json()["paths"][pid]["tiles"]
    assert tiles["enrolled"] == 1
    assert (tiles["onTrack"], tiles["behind"], tiles["ahead"]) == (0, 0, 0)


def test_team_views_show_self_paced_label(client):
    pid = make_path(client, "Self paced team", cadence="self", steps=3)
    client.put(f"/{pid}/api/enroll", json={"date": "2025-01-01"})
    rows = client.get("/api/team-summary").json()["learners"]
    me = next(r for r in rows if pid in r["paths"])
    assert me["paths"][pid]["pace"] == {"status": "self_paced", "label": "0 of 3 steps"}
    csv = client.get("/api/export.csv").text
    assert "0 of 3 steps" in csv
