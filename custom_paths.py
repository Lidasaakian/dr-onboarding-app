"""Learning paths created in the app (built by hand, or from links and files with the LLM).

Each path is one document, docs/path-<id>.json:

    {
      "id": "agent-workforce-monitoring",
      "status": "draft" | "published",
      "owners": ["maria.pm@datarobot.com", ...],     # the creator first; owners see this path's admin views
      "createdBy", "createdAt", "updatedAt", "publishedAt", "publishedBy",
      "draft":   <content>,                          # what owners edit
      "live":    <content> | null                    # what learners see (set on publish)
    }

Content:

    {
      "title", "blurb", "length",
      "pace": "weeks" | "days",                      # calendar weeks or working days
      "level": "Week" | "Module" | "Phase" | <custom>,
      "useDays": true | false,                       # days inside each group
      "skill": {"enabled": bool, "name": str},       # skill growth ("Decide later" = enabled false)
      "groups": [{"id", "title", "days": [{"id", "title", "steps": [<step>]}]}]
    }

Step: {"id", "title", "details", "link": {"url", "label"} | null, "type": "Required" | "Stretch" | "Optional",
       "gate": bool, "source": str}

Learners' ticks are keyed by step id, so ids never change once created.
"""

from __future__ import annotations

import copy
import io
import re
import secrets

from paths import Item, PathModel

TYPES = ("Required", "Stretch", "Optional")
LEVELS = ("Week", "Module", "Phase")
RESERVED = {"admin", "api", "assets", "static", "new", "path", "agentic", "ai-engineer", "p", "verify"}
MAX_STEPS = 600


def new_id(prefix: str) -> str:
    return f"{prefix}{secrets.token_hex(4)}"


def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")[:48].strip("-")
    return s or "path"


def unique_slug(title: str, taken: set[str]) -> str:
    base = slugify(title)
    if base in RESERVED:
        base = f"{base}-path"
    s, n = base, 2
    while s in taken or s in RESERVED:
        s = f"{base}-{n}"
        n += 1
    return s


def blank_content(title: str = "", level: str = "Week", use_days: bool = True, pace: str = "weeks") -> dict:
    return {
        "title": title or "Untitled learning path",
        "blurb": "",
        "length": "",
        "pace": pace if pace in ("weeks", "days") else "weeks",
        "level": level or "Week",
        "useDays": bool(use_days),
        "skill": {"enabled": False, "name": ""},
        "groups": [{"id": new_id("g"), "title": "", "days": [{"id": new_id("d"), "title": "", "steps": []}]}],
    }


def _txt(v, limit: int) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", str(v or "")).strip()[:limit]


def _link(v):
    if isinstance(v, str):
        v = {"url": v, "label": ""}
    if not isinstance(v, dict):
        return None
    url = _txt(v.get("url"), 2000)
    if not re.match(r"^https?://", url, re.I):
        return None
    return {"url": url, "label": _txt(v.get("label"), 200) or url}


def normalize(content: dict, keep_ids: set[str] | None = None) -> dict:
    """Clean and complete content from the editor, an import or the LLM. Every group, day and step gets an
    id (new ones when missing or duplicated). Raises ValueError when there is nothing usable."""
    if not isinstance(content, dict):
        raise ValueError("The path content must be an object.")
    seen: set[str] = set()

    def ident(v, prefix):
        v = re.sub(r"[^A-Za-z0-9_.-]", "", str(v or ""))[:40]
        if not v or v in seen or v.lower() in ("new", "none", "null"):
            v = new_id(prefix)
            while v in seen:
                v = new_id(prefix)
        seen.add(v)
        return v

    out = {
        "title": _txt(content.get("title"), 140) or "Untitled learning path",
        "blurb": _txt(content.get("blurb"), 600),
        "length": _txt(content.get("length"), 40),
        "pace": content.get("pace") if content.get("pace") in ("weeks", "days") else "weeks",
        "level": _txt(content.get("level"), 24) or "Week",
        "useDays": bool(content.get("useDays", True)),
        "skill": {"enabled": bool((content.get("skill") or {}).get("enabled")),
                  "name": _txt((content.get("skill") or {}).get("name"), 60)},
        "groups": [],
    }
    n = 0
    for g in content.get("groups") or []:
        if not isinstance(g, dict):
            continue
        days = g.get("days")
        if days is None and isinstance(g.get("steps"), list):  # a flat group from the LLM or an import
            days = [{"title": "", "steps": g["steps"]}]
        gd = {"id": ident(g.get("id"), "g"), "title": _txt(g.get("title"), 160), "days": []}
        for d in days or []:
            if not isinstance(d, dict):
                continue
            dd = {"id": ident(d.get("id"), "d"), "title": _txt(d.get("title"), 160), "steps": []}
            for st in d.get("steps") or []:
                if not isinstance(st, dict):
                    continue
                title = _txt(st.get("title"), 400)
                if not title:
                    continue
                n += 1
                if n > MAX_STEPS:
                    raise ValueError(f"A path can have at most {MAX_STEPS} steps.")
                typ = st.get("type") if st.get("type") in TYPES else "Required"
                dd["steps"].append({
                    "id": ident(st.get("id"), "s"),
                    "title": title,
                    "details": str(st.get("details") or "").strip()[:4000],
                    "link": _link(st.get("link")),
                    "type": typ,
                    "gate": bool(st.get("gate")),
                    "source": _txt(st.get("source"), 300),
                })
            gd["days"].append(dd)
        if not gd["days"]:
            gd["days"].append({"id": ident(None, "d"), "title": "", "steps": []})
        if not out["useDays"] and len(gd["days"]) > 1:  # no days: merge them
            merged = [s for d in gd["days"] for s in d["steps"]]
            gd["days"] = [{**gd["days"][0], "title": "", "steps": merged}]
        out["groups"].append(gd)
    if not out["groups"]:
        out["groups"].append({"id": ident(None, "g"), "title": "", "days": [{"id": ident(None, "d"), "title": "", "steps": []}]})
    return out


def steps(content: dict):
    """(group index, group, day index, day, step) for every step, in order."""
    for gi, g in enumerate(content.get("groups") or []):
        for di, d in enumerate(g.get("days") or []):
            for st in d.get("steps") or []:
                yield gi, g, di, d, st


def step_count(content: dict) -> int:
    return sum(1 for _ in steps(content))


def where_label(content: dict, gi: int, di: int) -> str:
    lvl = content.get("level") or "Week"
    s = f"{lvl} {gi + 1}"
    if content.get("useDays") and len((content["groups"][gi].get("days") or [])) > 0:
        s += f" · Day {di + 1}"
    return s


def model(path_doc: dict, content: dict, page_html: str) -> PathModel:
    """The PathModel the rest of the app uses (progress, pace, badge, team views) for a custom path."""
    items: list[Item] = []
    day_no = 0
    for gi, g in enumerate(content["groups"]):
        for di, d in enumerate(g["days"]):
            day_no += 1
            unit = gi + 1 if content["pace"] == "weeks" else day_no
            for st in d["steps"]:
                items.append(Item(id=st["id"], unit=unit, label=f"{where_label(content, gi, di)}: {st['title']}",
                                  anchor="s-" + st["id"], path=st["type"], gate=st["gate"]))
    units = len(content["groups"]) if content["pace"] == "weeks" else max(day_no, 1)
    skill = content["skill"]["name"] if content["skill"]["enabled"] else ""
    length = content.get("length") or (f"{units} week{'s' if units != 1 else ''}" if content["pace"] == "weeks" else f"{units} day{'s' if units != 1 else ''}")
    m = PathModel(id=path_doc["id"], title=content["title"], blurb=content.get("blurb") or "", length=length,
                  unit_name="Week" if content["pace"] == "weeks" else "Day", skill=skill, units=max(units, 1),
                  items=items, html=page_html, source={"kind": "custom"})
    m.custom = True
    m.skill_enabled = bool(content["skill"]["enabled"])
    m.owners = list(path_doc.get("owners") or [])
    return m


# --------------------------------------------------------------------------- diff (for LLM edits and publishing)

def diff(old: dict, new: dict) -> list[dict]:
    """What changed between two versions of the content, as short lines for the "Suggested changes" list."""
    def index(c):
        idx = {}
        for gi, g, di, d, st in steps(c):
            idx[st["id"]] = (gi, di, st, where_label(c, gi, di))
        return idx
    a, b = index(old), index(new)
    out = []
    old_groups = {g["id"]: (i, g) for i, g in enumerate(old.get("groups") or [])}
    new_groups = {g["id"]: (i, g) for i, g in enumerate(new.get("groups") or [])}
    lvl = new.get("level") or "Week"
    for gid, (i, g) in new_groups.items():
        if gid not in old_groups:
            n = sum(len(d["steps"]) for d in g["days"])
            out.append({"kind": "add", "text": f"New {lvl.lower()}: {lvl} {i + 1}" + (f" — {g['title']}" if g["title"] else "") + f" ({n} step{'s' if n != 1 else ''})"})
        elif old_groups[gid][1]["title"] != g["title"]:
            out.append({"kind": "upd", "text": f"{lvl} {i + 1} renamed: {g['title'] or '(no title)'}"})
    for gid, (i, g) in old_groups.items():
        if gid not in new_groups:
            out.append({"kind": "del", "text": f"Removed {lvl.lower()}: {lvl} {i + 1}" + (f" — {g['title']}" if g["title"] else "")})
    old_days = {d["id"] for g in old.get("groups") or [] for d in g["days"]}
    for gi, g in enumerate(new.get("groups") or []):
        if g["id"] not in old_groups:
            continue
        for di, d in enumerate(g["days"]):
            if new.get("useDays") and d["id"] not in old_days:
                out.append({"kind": "add", "text": f"New day: {lvl} {gi + 1} · Day {di + 1}" + (f" — {d['title']}" if d["title"] else "")})
    moved = 0
    for sid, (gi, di, st, where) in b.items():
        if sid not in a:
            out.append({"kind": "add", "text": f"{where}: {st['title']}", "source": st.get("source") or ""})
            continue
        ogi, odi, ost, owhere = a[sid]
        if old["groups"][ogi]["days"][odi]["id"] != new["groups"][gi]["days"][di]["id"]:
            moved += 1
        elif any(ost.get(k) != st.get(k) for k in ("title", "details", "link", "type", "gate")):
            out.append({"kind": "upd", "text": f"Changed {where}: {st['title']}"})
    if moved:
        out.append({"kind": "mov", "text": f"Moved {moved} step{'s' if moved != 1 else ''} to another day or {lvl.lower()}"})
    removed = [x for x in a if x not in b]
    for sid in removed[:20]:
        out.append({"kind": "del", "text": f"Removed {a[sid][3]}: {a[sid][2]['title']}"})
    if len(removed) > 20:
        out.append({"kind": "del", "text": f"…and {len(removed) - 20} more steps removed"})
    return out


# --------------------------------------------------------------------------- .xlsx template

TEMPLATE_HEADERS = ["Group", "Group title", "Day", "Day title", "Step", "Details", "Link", "Type", "Gate"]
TEMPLATE_NOTE = ("One row per step. Group = the week, module or phase number (1, 2, 3…). Day = the day inside the group "
                 "(leave empty if the path has no days). Type = Required, Stretch or Optional. Gate = yes for a checkpoint "
                 "that has to be passed. Group title and Day title only need to be on the first row of each group or day.")


def export_xlsx(content: dict) -> bytes:
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Steps"
    ws.append(TEMPLATE_HEADERS)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="81FBA5")
    for gi, g, di, d, st in steps(content):
        first_g = di == 0 and d["steps"] and d["steps"][0] is st
        first_d = d["steps"] and d["steps"][0] is st
        ws.append([gi + 1, g["title"] if first_g else "", (di + 1) if content.get("useDays") else "",
                   d["title"] if first_d else "", st["title"], st["details"], (st["link"] or {}).get("url", ""),
                   st["type"], "yes" if st["gate"] else "", ])
    for col, w in zip("ABCDEFGHI", (8, 30, 6, 30, 60, 70, 50, 11, 7)):
        ws.column_dimensions[col].width = w
    info = wb.create_sheet("Path")
    for row in (["Title", content.get("title", "")], ["Who it's for", content.get("blurb", "")], ["Length", content.get("length", "")],
                ["Pace", "Working days" if content.get("pace") == "days" else "Calendar weeks"], ["Top level is called", content.get("level", "Week")],
                ["Days inside each group", "yes" if content.get("useDays") else "no"], [], ["How to fill in the Steps sheet", TEMPLATE_NOTE]):
        info.append(row)
    info.column_dimensions["A"].width = 28
    info.column_dimensions["B"].width = 100
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def template_xlsx() -> bytes:
    sample = blank_content("My learning path")
    sample["groups"] = [{"id": "g1", "title": "Getting started", "days": [
        {"id": "d1", "title": "Access and tools", "steps": [
            {"id": "s1", "title": "Request access to the tools you need", "details": "", "link": None, "type": "Required", "gate": False, "source": ""},
            {"id": "s2", "title": "Read the product overview", "details": "Note three things it does.", "link": {"url": "https://docs.datarobot.com/", "label": ""}, "type": "Required", "gate": False, "source": ""}]},
        {"id": "d2", "title": "First hands-on lab", "steps": [
            {"id": "s3", "title": "Lab 1: build your first project", "details": "Done when the project shows results.", "link": None, "type": "Required", "gate": False, "source": ""},
            {"id": "s4", "title": "Week 1 check-in with your manager", "details": "", "link": None, "type": "Required", "gate": True, "source": ""}]}]}]
    return export_xlsx(sample)


def is_template(data: bytes) -> bool:
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        if "Steps" not in wb.sheetnames:
            return False
        head = [str(c.value or "").strip() for c in next(wb["Steps"].iter_rows(max_row=1))]
        return head[:len(TEMPLATE_HEADERS)] == TEMPLATE_HEADERS
    except Exception:
        return False


def import_xlsx(data: bytes, base: dict | None = None) -> dict:
    """Read the app's .xlsx template (the "Steps" sheet, and the "Path" sheet when present)."""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    if "Steps" not in wb.sheetnames:
        raise ValueError('This spreadsheet has no "Steps" sheet. Download the template and fill that in.')
    rows = list(wb["Steps"].iter_rows(values_only=True))
    head = [str(c or "").strip() for c in rows[0]] if rows else []
    if head[:len(TEMPLATE_HEADERS)] != TEMPLATE_HEADERS:
        raise ValueError("The Steps sheet's columns don't match the template: " + ", ".join(TEMPLATE_HEADERS) + ".")
    content = copy.deepcopy(base) if base else blank_content()
    if "Path" in wb.sheetnames:
        meta = {str(r[0] or "").strip(): r[1] for r in wb["Path"].iter_rows(values_only=True) if r and r[0]}
        content["title"] = str(meta.get("Title") or content["title"])
        content["blurb"] = str(meta.get("Who it's for") or content.get("blurb") or "")
        content["length"] = str(meta.get("Length") or content.get("length") or "")
        content["pace"] = "days" if str(meta.get("Pace") or "").lower().startswith("working") else "weeks"
        content["level"] = str(meta.get("Top level is called") or content.get("level") or "Week")
        content["useDays"] = str(meta.get("Days inside each group") or "yes").strip().lower() not in ("no", "false", "0")
    groups: dict[int, dict] = {}
    any_day = False
    for r in rows[1:]:
        r = list(r) + [None] * 9
        g_no, g_title, d_no, d_title, title, details, link, typ, gate = r[:9]
        title = str(title or "").strip()
        if not title:
            continue
        try:
            g_no = int(float(g_no)) if g_no not in (None, "") else (max(groups) if groups else 1)
        except (TypeError, ValueError):
            raise ValueError(f'"{g_no}" in the Group column isn\'t a number (step "{title[:60]}").')
        g = groups.setdefault(g_no, {"title": "", "days": {}})
        if g_title:
            g["title"] = str(g_title).strip()
        try:
            d_key = int(float(d_no)) if d_no not in (None, "") else 0
        except (TypeError, ValueError):
            d_key = 0
        any_day = any_day or bool(d_key)
        d = g["days"].setdefault(d_key, {"title": "", "steps": []})
        if d_title:
            d["title"] = str(d_title).strip()
        t = str(typ or "Required").strip().capitalize()
        d["steps"].append({"title": title, "details": str(details or "").strip(), "link": str(link or "").strip() or None,
                           "type": t if t in TYPES else "Required", "gate": str(gate or "").strip().lower() in ("yes", "y", "true", "1", "x")})
    if not groups:
        raise ValueError("The Steps sheet has no steps.")
    if "Path" not in wb.sheetnames:
        content["useDays"] = any_day
    content["groups"] = [{"title": groups[k]["title"], "days": [groups[k]["days"][dk] for dk in sorted(groups[k]["days"])]} for k in sorted(groups)]
    return normalize(content)
