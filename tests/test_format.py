"""The step-details formatter (static/assets/format.js), checked with Node (spec step-formatting)."""

import pathlib
import shutil
import subprocess

import pytest

HERE = pathlib.Path(__file__).parent


@pytest.mark.skipif(not shutil.which("node"), reason="Node isn't installed")
def test_formatter():
    r = subprocess.run(["node", str(HERE / "format_test.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


DETAILS = "Set up:\n- [ ] Install the CLI\n- [x] Sign in\n**Done** when [the docs](https://docs.datarobot.com/) load.\n1. one\n2. two"


def test_formatting_survives_normalize_and_xlsx():
    import custom_paths as cp
    c = cp.normalize({"title": "T", "groups": [{"title": "", "days": [{"title": "", "steps": [{"title": "S", "details": DETAILS}]}]}]})
    assert next(cp.steps(c))[-1]["details"] == DETAILS
    back = cp.import_xlsx(cp.export_xlsx(c))
    assert next(cp.steps(back))[-1]["details"] == DETAILS


def test_prompts_describe_the_syntax():
    import generate as gen
    for prompt in (gen.SYSTEM_GENERATE, gen.SYSTEM_EDIT):
        assert "- [ ]" in prompt and "**bold**" in prompt and "no html" in prompt.lower()


def test_checklist_ticks_saved_and_validated(client):
    from conftest import make_path
    pid = make_path(client, "Checks", steps=1)
    client.put(f"/{pid}/api/enroll", json={})
    assert client.put(f"/{pid}/api/progress", json={"state": {"done": {}, "checks": ["bad"]}}).status_code == 400
    assert client.put(f"/{pid}/api/progress", json={"state": {"done": {}, "checks": {"s1": "bad"}}}).status_code == 400
    ok = {"done": {}, "checks": {"s1": {"1": 1793700000000}}}
    assert client.put(f"/{pid}/api/progress", json={"state": ok}).status_code == 200
    state = client.get(f"/{pid}/api/progress").json()["state"]
    assert state["checks"] == ok["checks"] and state["done"] == {}
