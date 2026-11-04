"""Structure in the .xlsx template, export and import (spec path-structure: Structure in the spreadsheet template)."""

import io

import openpyxl

import custom_paths as cp


def structure(c):
    return (c["cadence"], c["levels"], [(g["title"], g["numbered"], len(g["days"])) for g in c["groups"]],
            [(st["title"], st["type"], st["gate"]) for *_, st in cp.steps(c)])


def test_round_trip_keeps_structure():
    c = cp.normalize({"title": "T", "cadence": "days", "levels": {"top": "Week", "sub": "Module"}, "groups": [
        {"title": "Prerequisites", "numbered": False, "days": [{"title": "", "steps": [{"title": "Get access"}]}]},
        {"title": "Basics", "days": [{"title": "M1", "steps": [{"title": "A"}]}, {"title": "M2", "steps": [{"title": "B", "gate": True}]}]},
    ]})
    back = cp.import_xlsx(cp.export_xlsx(c))
    assert structure(back) == structure(c)
    assert [cp.section_label(back, i) for i in range(2)] == ["Prerequisites", "Week 1"]


def test_round_trip_self_paced():
    c = cp.normalize({"title": "T", "cadence": "self", "levels": {"top": "Module", "sub": ""},
                      "groups": [{"title": "", "days": [{"title": "", "steps": [{"title": "A"}]}]}]})
    assert structure(cp.import_xlsx(cp.export_xlsx(c))) == structure(c)


def old_format_file(days_inside: str, pace: str) -> bytes:
    """A file made by the template before this change: Pace and "Days inside each group" on the Path sheet."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Steps"
    ws.append(cp.TEMPLATE_HEADERS)
    ws.append([1, "Intro", 1, "", "Step A", "", "", "Required", ""])
    ws.append([1, "", 2, "", "Step B", "", "", "Required", ""])
    ws.append([2, "Next", 1, "", "Step C", "", "", "Required", "yes"])
    info = wb.create_sheet("Path")
    for row in (["Title", "Old"], ["Pace", pace], ["Top level is called", "Phase"], ["Days inside each group", days_inside]):
        info.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_old_format_template_still_imports():
    c = cp.import_xlsx(old_format_file("yes", "Working days"))
    assert c["cadence"] == "days"
    assert c["levels"] == {"top": "Phase", "sub": "Day"}
    assert [len(g["days"]) for g in c["groups"]] == [2, 1]
    assert all(g["numbered"] for g in c["groups"])


def test_old_format_without_days():
    c = cp.import_xlsx(old_format_file("no", "Calendar weeks"))
    assert (c["cadence"], c["levels"]["sub"]) == ("weeks", "")
    assert [len(g["days"]) for g in c["groups"]] == [1, 1]


def test_template_downloads_and_imports():
    c = cp.import_xlsx(cp.template_xlsx())
    assert cp.step_count(c) == 4
    assert c["levels"] == {"top": "Week", "sub": "Day"}
