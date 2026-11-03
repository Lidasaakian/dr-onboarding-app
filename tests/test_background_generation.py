"""Generation in the background (spec path-creation: Generation runs in the background, Failed or interrupted
generation, Sources are optional)."""

import time
import types

import pytest

import custom_paths as cp
import generate as gen

LEARNER = {"x-user-email": "learner@example.com"}


class StubLLM:
    enabled = True

    def __init__(self, answer=None, error=None, wait=0.0):
        self.answer, self.error, self.wait = answer, error, wait

    def chat(self, *a, **kw):
        return "notes"

    def chat_json(self, *a, **kw):
        time.sleep(self.wait)
        if self.error:
            raise self.error
        return self.answer


class StubBot:
    enabled = True

    def __init__(self):
        self.sent = []

    def dm(self, email, text, background=True):
        self.sent.append((email, text))
        return True

    def url(self, path=""):
        return "https://app/" + path

    def photo(self, email):
        return ""


ANSWER = {"groups": [{"title": "A", "steps": [{"title": "Do A"}]}, {"title": "B", "steps": [{"title": "Do B"}]}]}


@pytest.fixture
def stubs(app_module, client, monkeypatch):
    bot = StubBot()
    monkeypatch.setattr(app_module, "slackbot", bot)
    monkeypatch.setattr(gen, "check_links", lambda urls: [])
    me = client.get("/agentic/api/me").json()

    def found_job():
        src = {"item": "i1", "kind": "web", "title": "Docs", "url": "https://docs.example.com", "text": "Facts."}
        job = gen.start("find", me["id"], lambda j: {"groups": []})
        job["data"]["collector"] = types.SimpleNamespace(sources={"a": src}, groups=[])
        wait(client, job["id"])
        return job["id"]

    def use_llm(llm):
        monkeypatch.setattr(app_module, "llm", llm)

    return types.SimpleNamespace(bot=bot, found_job=found_job, use_llm=use_llm, me=me)


def wait(client, jid, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/admin/jobs/{jid}").json()
        if j["status"] != "running":
            return j
        time.sleep(0.05)
    raise AssertionError("job didn't finish")


def generate(client, stubs, **settings):
    body = {"job": stubs.found_job(), "unchecked": [], "settings": {"title": "Gen path", **settings},
            "wizard": {"step": "review", "links": ["https://docs.example.com"], "gh": "secret-token"}}
    r = client.post("/api/admin/paths/generate", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def status_of(client, pid):
    return client.get(f"/api/admin/paths/{pid}").json()["path"]["status"]


def test_generating_then_draft_with_dm(client, stubs):
    stubs.use_llm(StubLLM(ANSWER, wait=0.3))
    r = generate(client, stubs, cadence="days")
    assert status_of(client, r["id"]) == "generating"
    row = next(p for p in client.get("/api/admin/paths").json()["paths"] if p["id"] == r["id"])
    assert row["status"] == "generating"
    wait(client, r["job"])
    doc = client.get(f"/api/admin/paths/{r['id']}").json()["path"]
    assert doc["status"] == "draft"
    assert doc["draft"]["cadence"] == "days"
    assert doc["generation"]["coverage"]["total"] == 1
    assert len(stubs.bot.sent) == 1 and "ready" in stubs.bot.sent[0][1]


def test_failure_is_recorded_without_dm(client, stubs):
    stubs.use_llm(StubLLM(error=ValueError("The LLM didn't return a learning path.")))
    r = generate(client, stubs)
    wait(client, r["job"])
    row = next(p for p in client.get("/api/admin/paths").json()["paths"] if p["id"] == r["id"])
    assert row["status"] == "failed"
    assert "didn't return" in row["error"]
    assert row["wizard"]["links"] == ["https://docs.example.com"]
    assert row["wizard"]["settings"]["title"] == "Gen path"
    assert "gh" not in row["wizard"]
    assert stubs.bot.sent == []


def test_try_again_replaces_the_failed_path(client, stubs):
    stubs.use_llm(StubLLM(error=ValueError("nope")))
    failed = generate(client, stubs)
    wait(client, failed["job"])
    stubs.use_llm(StubLLM(ANSWER))
    body = {"job": stubs.found_job(), "settings": {"title": "Gen path"}, "retryOf": failed["id"]}
    again = client.post("/api/admin/paths/generate", json=body).json()
    wait(client, again["job"])
    rows = client.get("/api/admin/paths").json()["paths"]
    assert len(rows) == len({p["id"] for p in rows})
    assert next(p for p in rows if p["id"] == again["id"])["status"] == "draft"
    assert not any(p["status"] == "failed" and p["id"] == failed["id"] for p in rows)


def test_generating_path_cannot_be_edited(client, stubs):
    stubs.use_llm(StubLLM(ANSWER, wait=0.5))
    r = generate(client, stubs)
    assert client.put(f"/api/admin/paths/{r['id']}/draft", json={"content": {"title": "x"}}).status_code == 409
    assert client.post(f"/api/admin/paths/{r['id']}/publish").status_code == 409
    wait(client, r["job"])


def test_generating_path_is_invisible_to_learners(client, stubs):
    stubs.use_llm(StubLLM(ANSWER, wait=0.5))
    r = generate(client, stubs)
    pid = r["id"]
    assert pid not in [p["id"] for p in client.get("/api/summary", headers=LEARNER).json()["paths"]]
    assert client.get(f"/{pid}/api/content", headers=LEARNER).status_code == 404
    assert client.get(f"/{pid}/api/progress", headers=LEARNER).status_code == 404
    assert client.put(f"/{pid}/api/enroll", headers=LEARNER, json={}).status_code == 404
    assert pid not in client.get("/api/dashboard").json()["paths"]
    wait(client, r["job"])


def test_ready_notice_listing(client, stubs):
    stubs.use_llm(StubLLM(ANSWER, wait=0.3))
    r = generate(client, stubs)
    mine = client.get("/api/admin/paths?generating=1").json()["paths"]
    assert {"id": r["id"], "status": "generating"}.items() <= next(p for p in mine if p["id"] == r["id"]).items()
    wait(client, r["job"])
    mine = client.get("/api/admin/paths?generating=1").json()["paths"]
    assert next(p for p in mine if p["id"] == r["id"])["status"] == "draft"


def test_restart_marks_generating_as_interrupted(app_module):
    doc = {"id": "cut-off", "status": "generating", "owners": ["dev@example.com"], "createdByEmail": "dev@example.com",
           "draft": cp.blank_content("Cut off"), "live": None, "wizard": {"settings": {"title": "Cut off"}}}
    app_module.docs.put("path-cut-off", doc)
    app_module.load_custom()
    got = app_module.CUSTOM["cut-off"]
    assert got["status"] == "failed"
    assert "interrupted" in got["error"]
    assert app_module.docs.get("path-cut-off")["status"] == "failed"


def test_skip_and_start_empty(client):
    r = client.post("/api/admin/paths", json={"title": "Empty one", "cadence": "weeks", "top": "Week", "sub": "Module",
                                              "beforeStart": True})
    c = client.get(f"/api/admin/paths/{r.json()['id']}").json()["path"]["draft"]
    assert (c["cadence"], c["levels"]) == ("weeks", {"top": "Week", "sub": "Module"})
    assert [cp.section_label(c, i) for i in range(2)] == ["Before you start", "Week 1"]


def test_old_build_form_still_accepted(client):
    r = client.post("/api/admin/paths", json={"title": "Old form", "pace": "days", "level": "Phase", "useDays": False})
    c = client.get(f"/api/admin/paths/{r.json()['id']}").json()["path"]["draft"]
    assert (c["cadence"], c["levels"]) == ("days", {"top": "Phase", "sub": ""})


def upload(client, name, text):
    r = client.post("/api/uploads", content=text.encode(), headers={"content-type": "text/markdown", "x-file-name": name})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_read_them_too_reads_only_new_sources(client):
    """Spec path-creation: Review sources before generating. Earlier items keep their ids, so unticks still apply."""
    first = client.post("/api/admin/paths/find", json={"uploads": [upload(client, "a.md", "# A\nAlpha facts.")]}).json()
    found1 = wait(client, first["job"])["result"]
    ids1 = [it["id"] for g in found1["groups"] for it in g["items"]]
    more = client.post("/api/admin/paths/find", json={"addTo": first["job"], "uploads": [upload(client, "b.md", "# B\nBeta facts.")]}).json()
    found2 = wait(client, more["job"])["result"]
    ids2 = [it["id"] for g in found2["groups"] for it in g["items"]]
    assert ids2[:len(ids1)] == ids1
    assert len(ids2) == len(ids1) + 1
    labels = [it["label"] for g in found2["groups"] for it in g["items"]]
    assert sum("a.md" in x for x in labels) == 1


def test_generate_refused_without_llm(client, stubs):
    stubs.use_llm(types.SimpleNamespace(enabled=False))
    body = {"job": stubs.found_job(), "settings": {"title": "No LLM"}}
    before = len(client.get("/api/admin/paths").json()["paths"])
    r = client.post("/api/admin/paths/generate", json=body)
    assert r.status_code == 503
    assert len(client.get("/api/admin/paths").json()["paths"]) == before


def test_xlsx_template_imported_without_llm(client):
    """Spec path-creation: Importing the .xlsx template."""
    c = cp.normalize({"title": "From sheet", "cadence": "self", "levels": {"top": "Module", "sub": ""}, "groups": [
        {"title": "Prerequisites", "numbered": False, "days": [{"title": "", "steps": [{"title": "Get access"}]}]},
        {"title": "", "days": [{"title": "", "steps": [{"title": "Learn"}]}]}]})
    r = client.post("/api/uploads", content=cp.export_xlsx(c), headers={"x-file-name": "plan.xlsx",
                    "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"})
    found = client.post("/api/admin/paths/find", json={"uploads": [r.json()["id"]], "settings": {"title": "Sheet path"}}).json()
    draft = client.get(f"/api/admin/paths/{found['imported']}").json()["path"]["draft"]
    assert draft["title"] == "Sheet path"
    assert (draft["cadence"], draft["levels"]["top"]) == ("self", "Module")
    assert [cp.section_label(draft, i) for i in range(2)] == ["Prerequisites", "Module 1"]
