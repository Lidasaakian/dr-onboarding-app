"""Generation follows the author's structure (spec path-creation: Generation follows the chosen structure)."""

import types

import custom_paths as cp
import generate as gen


class StubLLM:
    """Answers chat_json with a fixed path and records the requests."""

    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def chat(self, purpose, system, user, **kw):
        return "notes"

    def chat_json(self, purpose, system, user, **kw):
        self.asked.append(user)
        return self.answer


def collector():
    src = {"item": "i1", "kind": "jira", "title": "PBMP-1", "url": "https://x.atlassian.net/browse/PBMP-1", "text": "Feature facts."}
    return types.SimpleNamespace(sources={"a": src}, groups=[])


def job():
    return {"progress": []}


WEEKS_ANSWER = {"title": "LLM title", "pace": "weeks", "level": "Week", "useDays": True, "groups": [
    {"title": "One", "days": [{"title": "D1", "steps": [{"title": "Do A", "source": "S1"}]},
                              {"title": "D2", "steps": [{"title": "Do B", "source": "S1"}]}]},
    {"title": "Two", "days": [{"title": "D1", "steps": [{"title": "Do C", "source": "S1"}]}]}]}


def test_llm_answer_in_weeks_becomes_working_days():
    llm = StubLLM(WEEKS_ANSWER)
    res = gen.generate_path(job(), llm, collector(), set(), {"title": "Mine", "cadence": "days", "sub": ""})
    c = res["content"]
    assert c["cadence"] == "days"
    assert c["levels"] == {"top": "Day", "sub": ""}
    assert [cp.section_label(c, i) for i in range(2)] == ["Day 1", "Day 2"]
    assert all(len(g["days"]) == 1 for g in c["groups"])
    assert c["title"] == "Mine"
    assert "Cadence: Working days" in llm.asked[0][0]["text"]


def test_before_you_start_is_added_when_asked():
    res = gen.generate_path(job(), StubLLM(WEEKS_ANSWER), collector(), set(), {"cadence": "weeks", "beforeStart": True})
    c = res["content"]
    assert [cp.section_label(c, i) for i in range(3)] == ["Before you start", "Week 1", "Week 2"]


def test_llm_before_you_start_kept_and_others_numbered():
    answer = {"groups": [{"title": "Before you start", "numbered": False, "steps": [{"title": "Get access"}]},
                         {"title": "x", "numbered": False, "steps": [{"title": "A"}]}]}
    c = gen.generate_path(job(), StubLLM(answer), collector(), set(), {"cadence": "self", "beforeStart": True})["content"]
    assert [g["numbered"] for g in c["groups"]] == [False, True]
    assert [cp.section_label(c, i) for i in range(2)] == ["Before you start", "Module 1"]


def test_unasked_unnumbered_sections_are_numbered():
    answer = {"groups": [{"title": "x", "numbered": False, "steps": [{"title": "A"}]}]}
    c = gen.generate_path(job(), StubLLM(answer), collector(), set(), {"cadence": "weeks"})["content"]
    assert c["groups"][0]["numbered"] is True


def test_edit_scope_label_for_unnumbered_section():
    c = cp.normalize({"title": "T", "cadence": "weeks", "levels": {"top": "Week", "sub": ""}, "groups": [
        {"id": "g0", "title": "Before you start", "numbered": False, "days": [{"title": "", "steps": [{"title": "A"}]}]},
        {"id": "g1", "title": "", "days": [{"title": "", "steps": [{"title": "B"}]}]}]})
    llm = StubLLM({"id": "g0", "title": "Before you start", "days": [{"title": "", "steps": [{"title": "A2"}]}]})
    res = gen.edit_draft(job(), llm, c, "Rename the step", {"type": "group", "id": "g0"})
    assert "Change only this part (Before you start)" in llm.asked[0]
    assert res["content"]["groups"][0]["numbered"] is False
