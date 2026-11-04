"""Shared test setup: the app folder on sys.path, and stored path documents as fixtures."""

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT))


def load_doc(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture
def stored():
    """Load a stored path document (docs/path-<id>.json as the app saves it) by fixture name."""
    return load_doc


ALL_STORED = ["weeks-with-days", "days-no-days", "custom-level"]


@pytest.fixture(scope="session")
def app_module(tmp_path_factory):
    """The app running locally (no DataRobot endpoint): data in a temp folder, the dev user is a system admin."""
    import os
    for k in ("DATAROBOT_ENDPOINT", "DATAROBOT_API_TOKEN", "SLACK_BOT_TOKEN", "SLACK_WEBHOOK_URL"):
        os.environ.pop(k, None)
    os.environ["DATA_DIR"] = str(tmp_path_factory.mktemp("data"))
    import app
    return app


@pytest.fixture(scope="session")
def client(app_module):
    from fastapi.testclient import TestClient
    return TestClient(app_module.app)


def make_path(client, title, cadence="weeks", sub=None, steps=2, publish=True):
    """Create a path through the API with `steps` steps in its first section, optionally published. Returns its id."""
    body = {"title": title, "cadence": cadence}
    if sub is not None:
        body["sub"] = sub
    pid = client.post("/api/admin/paths", json=body).json()["id"]
    draft = client.get(f"/api/admin/paths/{pid}").json()["path"]["draft"]
    draft["groups"][-1]["days"][0]["steps"] = [{"title": f"Step {i}"} for i in range(1, steps + 1)]
    r = client.put(f"/api/admin/paths/{pid}/draft", json={"content": draft})
    assert r.status_code == 200, r.text
    if publish:
        assert client.post(f"/api/admin/paths/{pid}/publish").status_code == 200
    return pid
