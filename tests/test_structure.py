"""Path structure: cadence, level names, numbered and unnumbered sections, schedule mapping (spec path-structure)."""

import json

import pytest

import custom_paths as cp
from conftest import ALL_STORED, FIXTURES


def step(i, **kw):
    return {"id": f"s{i}", "title": f"Step {i}", **kw}


def content(cadence="weeks", top="Week", sub="Day", groups=()):
    return cp.normalize({"title": "T", "cadence": cadence, "levels": {"top": top, "sub": sub}, "groups": list(groups)})


def section(gid, *days, title="", numbered=True):
    return {"id": gid, "title": title, "numbered": numbered,
            "days": [{"id": f"{gid}d{i}", "title": "", "steps": d} for i, d in enumerate(days)]}


# ---------------------------------------------------------------- existing paths keep working

@pytest.mark.parametrize("name,cadence,levels", [
    ("weeks-with-days", "weeks", {"top": "Week", "sub": "Day"}),
    ("days-no-days", "days", {"top": "Day", "sub": ""}),
    ("custom-level", "weeks", {"top": "Sprint", "sub": ""}),
])
def test_old_paths_get_equivalent_structure(stored, name, cadence, levels):
    old = stored(name)["draft"]
    new = cp.normalize(old)
    assert new["cadence"] == cadence
    assert new["levels"] == levels
    assert all(g["numbered"] for g in new["groups"])
    assert [st["id"] for *_, st in cp.steps(new)] == [st["id"] for *_, st in cp.steps(old)]


@pytest.mark.parametrize("name", ALL_STORED)
def test_old_fields_still_written(stored, name):
    old = stored(name)["draft"]
    new = cp.normalize(old)
    assert (new["pace"], new["level"], new["useDays"]) == (old["pace"], old["level"], old["useDays"])


@pytest.mark.parametrize("name", ALL_STORED)
def test_schedule_unchanged_for_stored_paths(stored, name):
    base = json.loads((FIXTURES / "model-baseline.json").read_text())[name]
    doc = stored(name)
    m = cp.model(doc, cp.normalize(doc["draft"]), "")
    assert (m.unit_name, m.units, m.length) == (base["unit_name"], base["units"], base["length"])
    assert [[i.id, i.unit, i.label, i.gate, i.path] for i in m.items] == base["items"]


def test_normalize_is_stable():
    c = content(groups=[section("g1", [step(1)], title="Before you start", numbered=False), section("g2", [step(2)])])
    assert cp.normalize(c) == c


def test_self_paced_old_fields_for_rollback():
    c = content("self", "Module", "")
    assert (c["pace"], c["level"], c["useDays"]) == ("weeks", "Module", False)


# ---------------------------------------------------------------- labels

def test_modules_inside_weeks():
    c = content("weeks", "Week", "Module", [section("g1", [step(1)], [step(2)]), section("g2", [step(3)])])
    assert cp.where_label(c, 0, 1) == "Week 1 · Module 2"
    assert cp.where_label(c, 1, 0) == "Week 2 · Module 1"


def test_no_second_level():
    c = content("weeks", "Week", "", [section("g1", [step(1)])])
    assert cp.where_label(c, 0, 0) == "Week 1"
    assert cp.sub_label(c, 0, 0) == ""


def test_custom_level_name():
    c = content("weeks", "Sprint", "", [section("g1", [step(1)]), section("g2", [step(2)])])
    assert [cp.section_label(c, i) for i in range(2)] == ["Sprint 1", "Sprint 2"]


def test_path_starts_with_before_you_start():
    c = content("weeks", "Week", "", [section("g0", [step(1)], title="Before you start", numbered=False),
                                      section("g1", [step(2)]), section("g2", [step(3)])])
    assert [cp.section_label(c, i) for i in range(3)] == ["Before you start", "Week 1", "Week 2"]


def test_unnumbered_section_in_the_middle():
    c = content("weeks", "Week", "", [section("g1", [step(1)]), section("g2", [step(2)]),
                                      section("gm", [step(3)], title="Midpoint review", numbered=False), section("g3", [step(4)])])
    assert [cp.section_label(c, i) for i in range(4)] == ["Week 1", "Week 2", "Midpoint review", "Week 3"]


def test_untitled_unnumbered_section():
    c = content("weeks", "Week", "", [section("g1", [step(1)], numbered=False)])
    assert cp.section_label(c, 0) == "Section"


# ---------------------------------------------------------------- schedule mapping

def test_before_you_start_belongs_to_week_1():
    c = content("weeks", "Week", "", [section("g0", [step(1)], title="Before you start", numbered=False),
                                      section("g1", [step(2)]), section("g2", [step(3)])])
    m = cp.model({"id": "p"}, c, "")
    assert {i.id: i.unit for i in m.items} == {"s1": 1, "s2": 1, "s3": 2}
    assert (m.unit_name, m.units, m.length) == ("Week", 2, "2 weeks")


def test_unnumbered_section_at_the_end_takes_the_last_unit():
    c = content("weeks", "Week", "", [section("g1", [step(1)]), section("g2", [step(2)]),
                                      section("gz", [step(3)], title="Wrap-up", numbered=False)])
    assert {i.id: i.unit for i in cp.model({"id": "p"}, c, "").items}["s3"] == 2


def test_days_inside_weeks_with_working_days():
    weeks = [section(f"g{w}", *[[step(w * 10 + d)] for d in range(5)]) for w in (1, 2)]
    c = content("days", "Week", "Day", weeks)
    m = cp.model({"id": "p"}, c, "")
    units = {i.id: i.unit for i in m.items}
    assert units["s20"] == 6  # Week 2, Day 1
    assert (m.unit_name, m.units) == ("Day", 10)


def test_working_days_without_second_level():
    c = content("days", "Day", "", [section(f"g{i}", [step(i)]) for i in range(1, 4)])
    m = cp.model({"id": "p"}, c, "")
    assert [i.unit for i in m.items] == [1, 2, 3]


def test_unnumbered_section_with_days_shares_next_unit():
    c = content("days", "Week", "Day", [section("g0", [step(1)], [step(2)], title="Before you start", numbered=False),
                                        section("g1", [step(3)], [step(4)])])
    assert [i.unit for i in cp.model({"id": "p"}, c, "").items] == [1, 1, 1, 2]


def test_self_paced_has_no_schedule():
    c = content("self", "Module", "", [section("g1", [step(1)]), section("g2", [step(2)])])
    m = cp.model({"id": "p"}, c, "")
    assert (m.unit_name, m.units, m.length) == ("", 1, "2 modules")


# ---------------------------------------------------------------- removing the second level

def test_remove_days_from_a_week():
    c = content("weeks", "Week", "Day", [section("g1", [step(1), step(2)], [step(3)], [step(4)])])
    c["levels"]["sub"] = ""
    out = cp.normalize(c)
    assert len(out["groups"][0]["days"]) == 1
    assert [st["id"] for st in out["groups"][0]["days"][0]["steps"]] == ["s1", "s2", "s3", "s4"]


# ---------------------------------------------------------------- blank paths

def test_blank_content_defaults_follow_cadence():
    assert cp.blank_content("x", "weeks")["levels"] == {"top": "Week", "sub": "Day"}
    assert cp.blank_content("x", "days")["levels"] == {"top": "Day", "sub": ""}
    assert cp.blank_content("x", "self")["levels"] == {"top": "Module", "sub": ""}


def test_blank_content_before_you_start():
    c = cp.blank_content("x", "weeks", before_start=True)
    assert [cp.section_label(c, i) for i in range(2)] == ["Before you start", "Week 1"]
