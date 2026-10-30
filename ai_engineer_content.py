"""Parse the "AI Engineer Learning Plan" Google Sheet (exported as .xlsx) into the app's content.json.

Used by the app (admins upload the .xlsx on the hub) and by tools/refresh_ai_engineer.py.
Every checkable row keeps the id it had in the previous content (matched by week + title, then by
week + link + day + type), so learners' saved ticks survive edits to the sheet.
"""

from __future__ import annotations

import hashlib
import json
import re
import time

import io

import openpyxl

SHEET_URL = "https://docs.google.com/spreadsheets/d/13Uas6xLXTMv8DOUk7n_Qj0kojgvikr5bYPz9d8Ahy5U/edit"

HL = re.compile(r'^=HYPERLINK\("([^"]+)"\s*,\s*"([^"]*)"\)$', re.S)


def cell(v):
    """Plain text of a cell value; numbers like 3.0 become '3'."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def link(v):
    """(url, label) for a =HYPERLINK(...) cell, or (url, url) for a bare URL, else (None, text)."""
    s = cell(v)
    m = HL.match(s)
    if m:
        return m.group(1), m.group(2)
    if s.startswith("http"):
        return s, s
    return None, s


def lk(v):
    url, label = link(v)
    return {"url": url, "label": label} if url else None


def tidy(s: str) -> str:
    """Light tidy-up only: whitespace, and a trailing full stop for sentence-like 'done when' text."""
    s = re.sub(r"[ \t]+", " ", s or "").strip()
    return s


def rows(ws, start):
    for r in ws.iter_rows(min_row=start):
        vals = [c.value for c in r]
        if any(v not in (None, "") for v in vals):
            yield vals


def short_id(*parts) -> str:
    return hashlib.md5("|".join(parts).encode()).hexdigest()[:6]


# --------------------------------------------------------------------------- tabs

def read_overview(ws):
    lines = [cell(r[0]) for r in rows(ws, 1)]
    title = lines[0]
    get = {i: [c.value for c in row] for i, row in enumerate(ws.iter_rows(min_row=1), start=1)}
    rules = [cell(get[i][0]).lstrip("- ").strip() for i in range(3, 8) if cell(get[i][0])]
    routing = {
        "title": cell(get[9][0]),
        "fast": cell(get[10][0]),
        "full": cell(get[11][0]),
        "links": [x for x in (lk(get[12][0]), lk(get[13][0])) if x],
    }
    courses, notes, worth = [], [], []
    section = None
    for i in range(15, ws.max_row + 1):
        r = get.get(i)
        if not r:
            continue
        a = cell(r[0])
        if a.startswith("Anthropic / Claude courses"):
            section = "courses"; continue
        if a == "#":
            continue
        if a == "Things worth knowing":
            section = "worth"; continue
        if section == "courses":
            if re.fullmatch(r"\d+", a):
                courses.append({"n": int(a), "name": cell(r[1]), "week": cell(r[2]), "path": cell(r[3]), "url": link(r[4])[0]})
            elif a:
                notes.append({"text": tidy(a.rstrip(":")), "link": lk(r[1])})
        elif section == "worth" and a:
            worth.append({"text": tidy(a), "link": lk(r[4])})
    return {"title": title, "rules": rules, "routing": routing, "courses": courses, "courseNotes": notes, "worth": worth}


def read_plan(ws, prev_ids):
    intro = [cell(ws["A2"].value)]
    weeks: dict[str, dict] = {}
    seen = set()
    for r in rows(ws, 4):
        week, day, theme, typ, path, title, lnk, done, notes = (list(r) + [None] * 9)[:9]
        week, day = cell(week), cell(day)
        if not cell(title):
            continue
        url, _ = link(lnk)
        gate = cell(typ) == "Gate"
        title = tidy(cell(title))
        if gate:
            title = re.sub(r"^GATE:\s*", "", title)
            title = title[:1].upper() + title[1:]
        wk = weeks.setdefault(week, {"week": week, "theme": cell(theme), "items": []})
        key_title = (week, title)
        key_link = (week, url or "", day, cell(typ))
        iid = prev_ids.get(("t",) + key_title) or prev_ids.get(("l",) + key_link)
        if not iid or iid in seen:
            iid = f"w{week.lower()}.{short_id(day, url or '', cell(typ))}"
            if iid in seen:
                iid = f"w{week.lower()}.{short_id(day, url or '', cell(typ), title)}"
        seen.add(iid)
        wk["items"].append({
            "id": iid,
            "day": day,
            "type": cell(typ),
            "path": cell(path),
            "title": title,
            "url": url,
            "doneWhen": tidy(cell(done)),
            "notes": tidy(cell(notes)),
            "gate": gate,
        })
    ordered = sorted((w for k, w in weeks.items() if k.isdigit()), key=lambda w: int(w["week"]))
    anyweek = [w for k, w in weeks.items() if not k.isdigit()]
    return intro, ordered, anyweek


def read_options(ws):
    get = {i: [c.value for c in row] for i, row in enumerate(ws.iter_rows(min_row=1), start=1)}
    hdr = [cell(x) for x in get[4]]
    opts, refs = [], []
    for i in range(5, ws.max_row + 1):
        r = get.get(i)
        if not r:
            continue
        if re.fullmatch(r"\d+", cell(r[0])):
            name = cell(r[1])
            m = re.match(r"^([A-Z])\.\s*(.*)$", name)
            key, nm = (m.group(1), m.group(2)) if m else (cell(r[0]), name)
            rec = "(recommended default)" in nm
            nm = nm.replace("(recommended default)", "").strip()
            gates = {}
            for j, h in enumerate(hdr):
                g = re.match(r"Week (\d+) gate", h)
                if g:
                    gates[g.group(1)] = tidy(cell(r[j]))
            opts.append({
                "key": key, "name": nm, "recommended": rec,
                "description": tidy(cell(r[2])), "data": tidy(cell(r[3])), "dataLink": lk(r[4]),
                "template": lk(r[5]), "video": lk(r[6]),
                "accuracy": tidy(cell(r[7])), "escalation": tidy(cell(r[8])), "gates": gates,
            })
        elif cell(r[1]) and cell(r[1]) != "Extra references for the options":
            refs.append({"text": tidy(cell(r[1])), "link": lk(r[4])})
    return {"title": cell(get[1][0]), "intro": cell(get[2][0]), "options": opts, "refs": refs}


def read_roadmap(ws):
    out = {"title": cell(ws["A1"].value), "intro": cell(ws["A2"].value), "weeks": {}}
    for r in rows(ws, 5):
        w = cell(r[0])
        if not w.isdigit():
            continue
        out["weeks"][w] = {"phase": cell(r[1]), "learn": tidy(cell(r[2])), "apply": tidy(cell(r[3])),
                           "state": tidy(cell(r[4])), "doneWhen": tidy(cell(r[5])), "ref": lk(r[6])}
    return out


def read_planning(ws):
    get = {i: [c.value for c in row] for i, row in enumerate(ws.iter_rows(min_row=1), start=1)}
    out = {"title": cell(get[1][0]), "intro": [cell(get[2][0]), cell(get[3][0])], "steps": [], "tip": ""}
    step = None
    for i in range(4, ws.max_row + 1):
        r = get.get(i) or []
        a = cell(r[0]) if r else ""
        if a.startswith("Step "):
            step = {"title": a, "header": [], "rows": [], "refs": []}
            out["steps"].append(step); continue
        if a.startswith("Tip:"):
            out["tip"] = tidy(a); continue
        if step is None or not any(cell(x) for x in r):
            continue
        if not step["header"]:
            step["header"] = [cell(x) for x in r if cell(x)]; continue
        if a == "Reference":
            step["refs"] = [lk(x) for x in r[1:] if lk(x)]; continue
        cells = []
        for x in r[:len(step["header"])]:
            u = lk(x)
            cells.append({"link": u} if u else {"text": tidy(cell(x))})
        step["rows"].append(cells)
    return out


def read_example(ws):
    get = {i: [c.value for c in row] for i, row in enumerate(ws.iter_rows(min_row=1), start=1)}
    out = {"title": cell(get[1][0]), "intro": [cell(get[i][0]) for i in (2, 3, 4)], "rows": [], "starter": None}
    for i in range(7, ws.max_row + 1):
        r = get.get(i)
        if not r:
            continue
        if cell(r[0]).isdigit():
            out["rows"].append({"week": cell(r[0]), "phase": cell(r[1]), "learn": tidy(cell(r[2])), "build": tidy(cell(r[3])),
                                "deliverable": tidy(cell(r[4])), "doneWhen": tidy(cell(r[5])), "planning": tidy(cell(r[6])), "ref": lk(r[7])})
        elif cell(r[0]).startswith("Template starter"):
            out["starter"] = lk(r[1])
    return out


def read_certs(ws, prev_ids):
    out = {"title": cell(ws["A1"].value), "intro": cell(ws["A2"].value), "rows": [], "notes": []}
    for r in rows(ws, 5):
        a = cell(r[0])
        if a.isdigit():
            name = tidy(cell(r[1]))
            iid = prev_ids.get(("c", name)) or f"cert.{short_id(name)}"
            out["rows"].append({"id": iid, "name": name, "provider": tidy(cell(r[2])), "link": lk(r[3]), "timing": tidy(cell(r[4])),
                                "cost": tidy(cell(r[5])), "format": tidy(cell(r[6])), "extra": lk(r[7])})
        elif cell(r[1]) and not cell(r[1]).startswith("Certifications done"):
            out["notes"].append(tidy(cell(r[1])))
    return out


# --------------------------------------------------------------------------- main

def previous_ids(old: dict | None):
    ids, all_ids = {}, set()
    if not old:
        return ids, all_ids
    for w in old.get("weeks", []) + old.get("anyWeek", []):
        for it in w["items"]:
            ids[("t", w["week"], it["title"])] = it["id"]
            ids[("l", w["week"], it.get("url") or "", it["day"], it["type"])] = it["id"]
            all_ids.add(it["id"])
    for c in old.get("certs", {}).get("rows", []):
        ids[("c", c["name"])] = c["id"]
        all_ids.add(c["id"])
    return ids, all_ids


def item_index(content: dict) -> dict[str, str]:
    """id -> 'Week N: title' for every checkable row (plan rows and certifications)."""
    out = {}
    for w in content.get("weeks", []) + content.get("anyWeek", []):
        for it in w["items"]:
            out[it["id"]] = f"Week {w['week']}: {it['title']}"
    for c in content.get("certs", {}).get("rows", []):
        out[c["id"]] = f"Certification: {c['name']}"
    return out


REQUIRED_TABS = ["Overview", "Plan", "Project Options", "Project Roadmap", "Project Planning",
                 "Example - Data Analyst Agent", "Optional Certifications"]


def build(xlsx, previous: dict | None = None) -> tuple[dict, dict]:
    """xlsx: a path or the file's bytes. Returns (content, diff) where diff lists added/removed row ids."""
    wb = openpyxl.load_workbook(io.BytesIO(xlsx) if isinstance(xlsx, (bytes, bytearray)) else xlsx)
    missing = [t for t in REQUIRED_TABS if t not in wb.sheetnames]
    if missing:
        raise ValueError("This doesn't look like the AI Engineer Learning Plan sheet. Missing tabs: " + ", ".join(missing))
    prev, old_ids = previous_ids(previous)
    intro, weeks, anyweek = read_plan(wb["Plan"], prev)
    if not weeks:
        raise ValueError("The Plan tab has no rows.")
    content = {
        "meta": {"title": "AI Engineer Learning Plan", "source": SHEET_URL, "generatedAt": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())},
        "overview": read_overview(wb["Overview"]),
        "planIntro": intro,
        "weeks": weeks,
        "anyWeek": anyweek,
        "options": read_options(wb["Project Options"]),
        "roadmap": read_roadmap(wb["Project Roadmap"]),
        "planning": read_planning(wb["Project Planning"]),
        "example": read_example(wb["Example - Data Analyst Agent"]),
        "certs": read_certs(wb["Optional Certifications"], prev),
    }
    new_index = item_index(content)
    old_index = item_index(previous) if previous else {}
    added = sorted(set(new_index) - set(old_index)) if previous else []
    removed = sorted(set(old_index) - set(new_index)) if previous else []
    diff = {
        "weeks": len(weeks),
        "rows": sum(len(w["items"]) for w in weeks + anyweek),
        "options": len(content["options"]["options"]),
        "certs": len(content["certs"]["rows"]),
        "added": [{"id": i, "label": new_index[i]} for i in added],
        "removed": [{"id": i, "label": old_index[i]} for i in removed],
    }
    return content, diff


# ---------------------------------------------------------------------- export (app -> sheet)

def _hl(link: dict | None, label: str | None = None) -> str | None:
    if not link or not link.get("url"):
        return None
    text = (label if label is not None else link.get("label") or link["url"]).replace('"', "'")
    return f'=HYPERLINK("{link["url"]}","{text}")'


def export_xlsx(content: dict) -> bytes:
    """Write the content back into the sheet's layout (same tabs, rows and columns), so the file can be
    shared, edited in Google Sheets and uploaded again. read_* above parse exactly this layout."""
    from openpyxl.styles import Font

    wb = openpyxl.Workbook()
    bold = Font(bold=True)

    # Overview
    ws = wb.active
    ws.title = "Overview"
    o = content["overview"]
    ws["A1"] = o["title"]
    ws["A1"].font = Font(bold=True, size=14)
    for i, r in enumerate(o["rules"][:5]):
        ws.cell(row=3 + i, column=1, value="- " + r)
    ws["A9"] = o["routing"]["title"]
    ws["A9"].font = bold
    ws["A10"], ws["A11"] = o["routing"]["fast"], o["routing"]["full"]
    for i, l in enumerate(o["routing"]["links"][:2]):
        ws.cell(row=12 + i, column=1, value=_hl(l))
    ws["A15"] = "Anthropic / Claude courses, in the order to take them"
    ws["A15"].font = bold
    for j, h in enumerate(["#", "Course", "Week", "Path", "Link"], start=1):
        ws.cell(row=16, column=j, value=h).font = bold
    r = 17
    for c in o["courses"]:
        for j, v in enumerate([c["n"], c["name"], c["week"], c["path"], _hl({"url": c["url"]}, "open")], start=1):
            ws.cell(row=r, column=j, value=v)
        r += 1
    for n in o["courseNotes"]:
        ws.cell(row=r, column=1, value=n["text"] + (":" if n.get("link") else ""))
        ws.cell(row=r, column=2, value=_hl(n.get("link")))
        r += 1
    ws.cell(row=r, column=1, value="Things worth knowing").font = bold
    r += 1
    for w in o["worth"]:
        ws.cell(row=r, column=1, value=w["text"])
        ws.cell(row=r, column=5, value=_hl(w.get("link"), "source"))
        r += 1

    # Plan
    ws = wb.create_sheet("Plan")
    ws["A1"] = "Plan, week by week"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = (content.get("planIntro") or [""])[0]
    for j, h in enumerate(["Week", "Day", "Theme", "Type", "Path", "Title", "Link", "Done when...", "Notes"], start=1):
        ws.cell(row=3, column=j, value=h).font = bold
    r = 4
    for w in content["weeks"] + content.get("anyWeek", []):
        for it in w["items"]:
            title = ("GATE: " + it["title"]) if it.get("gate") else it["title"]
            vals = [int(w["week"]) if w["week"].isdigit() else w["week"],
                    int(it["day"]) if it["day"].isdigit() else it["day"], w["theme"],
                    it["type"], it["path"], title, _hl({"url": it["url"]}, it["url"]) if it.get("url") else None,
                    it.get("doneWhen") or None, it.get("notes") or None]
            for j, v in enumerate(vals, start=1):
                ws.cell(row=r, column=j, value=v)
            r += 1

    # Project Options
    ws = wb.create_sheet("Project Options")
    P = content["options"]
    ws["A1"], ws["A2"] = P["title"], P["intro"]
    gate_weeks = sorted({int(k) for o in P["options"] for k in o["gates"]})
    hdr = ["#", "Option", "One-line description", "Data source (public only)", "Data link", "Starter template", "Video",
           "Accuracy means", "Escalation means"] + [f"Week {g} gate" for g in gate_weeks]
    for j, h in enumerate(hdr, start=1):
        ws.cell(row=4, column=j, value=h).font = bold
    r = 5
    for i, o in enumerate(P["options"], start=1):
        vals = [i, f"{o['key']}. {o['name']}" + (" (recommended default)" if o.get("recommended") else ""),
                o["description"], o["data"], _hl(o.get("dataLink")), _hl(o.get("template")), _hl(o.get("video")),
                o["accuracy"], o["escalation"]] + [o["gates"].get(str(g), "") for g in gate_weeks]
        for j, v in enumerate(vals, start=1):
            ws.cell(row=r, column=j, value=v)
        r += 1
    ws.cell(row=r, column=2, value="Extra references for the options").font = bold
    r += 1
    for ref in P["refs"]:
        ws.cell(row=r, column=2, value=ref["text"])
        ws.cell(row=r, column=5, value=_hl(ref.get("link"), "open"))
        r += 1

    # Project Roadmap
    ws = wb.create_sheet("Project Roadmap")
    R = content["roadmap"]
    ws["A1"], ws["A2"] = R["title"], R["intro"]
    for j, h in enumerate(["Week", "Phase", "What you learn", "Apply it to your project", "Project state at the end of the week",
                           "Done when (project check)", "Reference"], start=1):
        ws.cell(row=4, column=j, value=h).font = bold
    r = 5
    for wk in sorted(R["weeks"], key=int):
        x = R["weeks"][wk]
        for j, v in enumerate([int(wk), x["phase"], x["learn"], x["apply"], x["state"], x["doneWhen"], _hl(x.get("ref"))], start=1):
            ws.cell(row=r, column=j, value=v)
        r += 1

    # Project Planning
    ws = wb.create_sheet("Project Planning")
    PL = content["planning"]
    ws["A1"] = PL["title"]
    ws["A2"], ws["A3"] = (PL["intro"] + ["", ""])[:2]
    r = 6
    for st in PL["steps"]:
        ws.cell(row=r, column=1, value=st["title"]).font = bold
        r += 1
        for j, h in enumerate(st["header"], start=1):
            ws.cell(row=r, column=j, value=h).font = bold
        r += 1
        for row in st["rows"]:
            for j, c in enumerate(row, start=1):
                ws.cell(row=r, column=j, value=_hl(c["link"]) if c.get("link") else (c.get("text") or None))
            r += 1
        if st.get("refs"):
            ws.cell(row=r, column=1, value="Reference")
            for j, l in enumerate(st["refs"], start=2):
                ws.cell(row=r, column=j, value=_hl(l))
            r += 1
        r += 1
    if PL.get("tip"):
        ws.cell(row=r, column=1, value=PL["tip"])

    # Example
    ws = wb.create_sheet("Example - Data Analyst Agent")
    E = content["example"]
    ws["A1"] = E["title"]
    for i, t in enumerate(E["intro"][:3]):
        ws.cell(row=2 + i, column=1, value=t)
    for j, h in enumerate(["Week", "Phase", "Learning you use", "What to build this week", "Deliverable at the end of the week",
                           "Done when", "Planning this week (spec and plan grow here)", "Reference"], start=1):
        ws.cell(row=6, column=j, value=h).font = bold
    r = 7
    for x in E["rows"]:
        for j, v in enumerate([int(x["week"]), x["phase"], x["learn"], x["build"], x["deliverable"], x["doneWhen"],
                               x["planning"], _hl(x.get("ref"))], start=1):
            ws.cell(row=r, column=j, value=v)
        r += 1
    if E.get("starter"):
        ws.cell(row=r + 1, column=1, value="Template starter:")
        ws.cell(row=r + 1, column=2, value=_hl(E["starter"]))

    # Optional Certifications
    ws = wb.create_sheet("Optional Certifications")
    X = content["certs"]
    ws["A1"], ws["A2"] = X["title"], X["intro"]
    for j, h in enumerate(["#", "Certification (all Optional)", "Provider", "Official page", "Suggested timing", "Cost",
                           "Exam format", "Extra link"], start=1):
        ws.cell(row=4, column=j, value=h).font = bold
    r = 5
    for i, c in enumerate(X["rows"], start=1):
        for j, v in enumerate([i, c["name"], c["provider"], _hl(c.get("link")), c["timing"], c["cost"], c["format"],
                               _hl(c.get("extra"))], start=1):
            ws.cell(row=r, column=j, value=v)
        r += 1
    for n in X.get("notes", []):
        ws.cell(row=r, column=2, value=n)
        r += 1

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def validate_content(content: dict) -> None:
    """Basic shape checks for content edited in the app."""
    if not isinstance(content, dict) or not content.get("weeks"):
        raise ValueError("The plan has no weeks.")
    seen = set()
    for w in content["weeks"] + content.get("anyWeek", []):
        for it in w.get("items", []):
            if not it.get("id") or not str(it.get("title", "")).strip():
                raise ValueError(f"Week {w.get('week')}: every row needs a title.")
            if it["id"] in seen:
                raise ValueError(f"Duplicate step id {it['id']}.")
            seen.add(it["id"])
            if it.get("path") not in ("Required", "Stretch", "Optional"):
                raise ValueError(f"Week {w.get('week')}: path must be Required, Stretch or Optional.")
    for key in ("overview", "options", "roadmap", "planning", "example", "certs"):
        if key not in content:
            raise ValueError(f"Missing section: {key}.")
