"""Learning paths created in the app (built by hand, or from links and files with the LLM).

Each path is one document, docs/path-<id>.json:

    {
      "id": "agent-workforce-monitoring",
      "status": "generating" | "failed" | "draft" | "published",
      "owners": ["maria.pm@datarobot.com", ...],     # the creator first; owners see this path's admin views
      "createdBy", "createdAt", "updatedAt", "publishedAt", "publishedBy",
      "draft":   <content>,                          # what owners edit
      "live":    <content> | null                    # what learners see (set on publish)
    }

Content:

    {
      "title", "blurb", "length",
      "cadence": "weeks" | "days" | "self",          # calendar weeks, working days or self-paced
      "levels": {"top": "Week", "sub": "Day"},       # level names; sub "" = no second level
      "pace", "level", "useDays",                    # the same structure in the old fields, kept for rollback
      "skill": {"enabled": bool, "name": str},       # skill growth ("Decide later" = enabled false)
      "groups": [{"id", "title", "numbered": bool, "days": [{"id", "title", "steps": [<step>]}]}]
    }

"groups" are the top-level sections; "days" hold the second-level sections whatever they're called (a section
without a second level has one untitled entry). An unnumbered section ("Before you start") shows its title instead
of a number and doesn't count in the numbering of the others.

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
CADENCES = ("weeks", "days", "self")
DEFAULT_LEVELS = {"weeks": ("Week", "Day"), "days": ("Day", ""), "self": ("Module", "")}  # (top, sub) per cadence
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


def blank_content(title: str = "", cadence: str = "weeks", top: str | None = None, sub: str | None = None,
                  before_start: bool = False) -> dict:
    """An empty path with this structure; level names default to the cadence's. before_start adds an unnumbered
    "Before you start" section first."""
    cadence = cadence if cadence in CADENCES else "weeks"
    d_top, d_sub = DEFAULT_LEVELS[cadence]
    groups = [{"id": new_id("g"), "title": "", "numbered": True, "days": [{"id": new_id("d"), "title": "", "steps": []}]}]
    if before_start:
        groups.insert(0, {"id": new_id("g"), "title": "Before you start", "numbered": False,
                          "days": [{"id": new_id("d"), "title": "", "steps": []}]})
    return normalize({
        "title": title or "Untitled learning path",
        "cadence": cadence,
        "levels": {"top": d_top if top is None else top, "sub": d_sub if sub is None else sub},
        "groups": groups,
    })


def structure_from(d: dict) -> dict:
    """The structure the author chose (cadence, top, sub, beforeStart) as blank_content() arguments; None for a level
    name means the cadence's default. Also reads the old form's pace, level and useDays."""
    d = d or {}
    cadence = d.get("cadence") if d.get("cadence") in CADENCES else ("days" if d.get("pace") == "days" else "weeks")
    top = _txt(d.get("top") or d.get("level"), 24) or None
    if "sub" in d:
        sub = _txt(d.get("sub"), 24)
    elif "useDays" in d:
        sub = "Day" if d.get("useDays") else ""
    else:
        sub = None
    return {"cadence": cadence, "top": top, "sub": sub, "before_start": bool(d.get("beforeStart"))}


def levels_of(content: dict) -> tuple[str, str]:
    """(top, sub) level names, from the new fields or, for content saved before them, the old ones."""
    lv = content.get("levels")
    if isinstance(lv, dict):
        return (_txt(lv.get("top"), 24) or "Week", _txt(lv.get("sub"), 24))
    return (_txt(content.get("level"), 24) or "Week", "Day" if content.get("useDays", True) else "")


def cadence_of(content: dict) -> str:
    c = content.get("cadence")
    if c in CADENCES:
        return c
    return "days" if content.get("pace") == "days" else "weeks"


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

    cadence = cadence_of(content)
    top, sub = levels_of(content)
    out = {
        "title": _txt(content.get("title"), 140) or "Untitled learning path",
        "blurb": _txt(content.get("blurb"), 600),
        "length": _txt(content.get("length"), 40),
        "cadence": cadence,
        "levels": {"top": top, "sub": sub},
        "pace": "days" if cadence == "days" else "weeks",
        "level": top,
        "useDays": bool(sub),
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
        gd = {"id": ident(g.get("id"), "g"), "title": _txt(g.get("title"), 160), "numbered": g.get("numbered", True) is not False,
              "days": []}
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
        if not sub and len(gd["days"]) > 1:  # no second level: merge them, keeping the order and the step ids
            merged = [s for d in gd["days"] for s in d["steps"]]
            gd["days"] = [{**gd["days"][0], "title": "", "steps": merged}]
        out["groups"].append(gd)
    if not out["groups"]:
        out["groups"].append({"id": ident(None, "g"), "title": "", "numbered": True, "days": [{"id": ident(None, "d"), "title": "", "steps": []}]})
    return out


def steps(content: dict):
    """(group index, group, day index, day, step) for every step, in order."""
    for gi, g in enumerate(content.get("groups") or []):
        for di, d in enumerate(g.get("days") or []):
            for st in d.get("steps") or []:
                yield gi, g, di, d, st


def step_count(content: dict) -> int:
    return sum(1 for _ in steps(content))


def section_label(content: dict, gi: int) -> str:
    """ "Week 2" for a numbered section (counting only numbered ones), the title for an unnumbered one."""
    groups = content["groups"]
    g = groups[gi]
    if g.get("numbered", True) is False:
        return g.get("title") or "Section"
    n = sum(1 for x in groups[:gi + 1] if x.get("numbered", True) is not False)
    return f"{levels_of(content)[0]} {n}"


def sub_label(content: dict, gi: int, di: int) -> str:
    """ "Day 3" inside its section, or "" when the path has no second level."""
    sub = levels_of(content)[1]
    return f"{sub} {di + 1}" if sub else ""


def where_label(content: dict, gi: int, di: int) -> str:
    s = section_label(content, gi)
    sl = sub_label(content, gi, di)
    if sl and len((content["groups"][gi].get("days") or [])) > 0:
        s += f" · {sl}"
    return s


def schedule_units(content: dict) -> tuple[list[list[int]], int]:
    """The schedule unit (week or working day, from 1) of every second-level section, per section, and the number
    of units. Weeks: each numbered section is a week. Days: each second-level section is a working day, or each
    numbered section when there's no second level. An unnumbered section is scheduled with the next numbered
    section, or the last one when none follows. Self-paced paths have one unit."""
    cadence = cadence_of(content)
    has_sub = bool(levels_of(content)[1])
    groups = content["groups"]
    units: list[list[int] | None] = []
    n = 0
    for g in groups:
        if g.get("numbered", True) is False or cadence == "self":
            units.append(None)
            continue
        if cadence == "weeks":
            n += 1
            units.append([n] * len(g["days"]))
        elif has_sub:
            units.append(list(range(n + 1, n + len(g["days"]) + 1)))
            n += len(g["days"])
        else:
            n += 1
            units.append([n] * len(g["days"]))
    total = max(n, 1)
    for gi in range(len(groups) - 1, -1, -1):
        if units[gi] is None:
            nxt = next((u[0] for u in units[gi + 1:] if u), total)
            units[gi] = [nxt] * len(groups[gi]["days"])
    return units, total


def model(path_doc: dict, content: dict, page_html: str) -> PathModel:
    """The PathModel the rest of the app uses (progress, pace, badge, team views) for a custom path."""
    items: list[Item] = []
    per_day, units = schedule_units(content)
    for gi, g in enumerate(content["groups"]):
        for di, d in enumerate(g["days"]):
            for st in d["steps"]:
                items.append(Item(id=st["id"], unit=per_day[gi][di], label=f"{where_label(content, gi, di)}: {st['title']}",
                                  anchor="s-" + st["id"], path=st["type"], gate=st["gate"]))
    skill = content["skill"]["name"] if content["skill"]["enabled"] else ""
    cadence = cadence_of(content)
    if cadence == "self":
        top = levels_of(content)[0]
        n = sum(1 for g in content["groups"] if g.get("numbered", True) is not False)
        length, unit_name = f"{n} {top.lower()}{'s' if n != 1 else ''}", ""
    elif cadence == "weeks":
        length, unit_name = f"{units} week{'s' if units != 1 else ''}", "Week"
    else:
        length, unit_name = f"{units} day{'s' if units != 1 else ''}", "Day"
    m = PathModel(id=path_doc["id"], title=content["title"], blurb=content.get("blurb") or "", length=content.get("length") or length,
                  unit_name=unit_name, skill=skill, units=units,
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
    lvl, sub = levels_of(new)
    for gid, (i, g) in new_groups.items():
        if gid not in old_groups:
            n = sum(len(d["steps"]) for d in g["days"])
            out.append({"kind": "add", "text": f"New section: {section_label(new, i)}" + (f" — {g['title']}" if g["title"] and g.get("numbered", True) is not False else "") + f" ({n} step{'s' if n != 1 else ''})"})
        elif old_groups[gid][1]["title"] != g["title"]:
            out.append({"kind": "upd", "text": f"{section_label(old, old_groups[gid][0])} renamed: {g['title'] or '(no title)'}"})
    for gid, (i, g) in old_groups.items():
        if gid not in new_groups:
            out.append({"kind": "del", "text": f"Removed section: {section_label(old, i)}" + (f" — {g['title']}" if g["title"] and g.get("numbered", True) is not False else "")})
    old_days = {d["id"] for g in old.get("groups") or [] for d in g["days"]}
    for gi, g in enumerate(new.get("groups") or []):
        if g["id"] not in old_groups:
            continue
        for di, d in enumerate(g["days"]):
            if sub and d["id"] not in old_days:
                out.append({"kind": "add", "text": f"New {sub.lower()}: {where_label(new, gi, di)}" + (f" — {d['title']}" if d["title"] else "")})
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
        out.append({"kind": "mov", "text": f"Moved {moved} step{'s' if moved != 1 else ''} to another {(sub or 'section').lower()} or {lvl.lower()}"})
    removed = [x for x in a if x not in b]
    for sid in removed[:20]:
        out.append({"kind": "del", "text": f"Removed {a[sid][3]}: {a[sid][2]['title']}"})
    if len(removed) > 20:
        out.append({"kind": "del", "text": f"…and {len(removed) - 20} more steps removed"})
    return out


# --------------------------------------------------------------------------- .xlsx template

TEMPLATE_HEADERS = ["Group", "Group title", "Day", "Day title", "Step", "Details", "Link", "Type", "Gate"]
TEMPLATE_NOTE = ("One row per step. Group = the section's position (1, 2, 3…), counting every section. Day = the "
                 "second-level section inside it, such as the day or module (leave empty if the path has no second level). "
                 "Type = Required, Stretch or Optional. Gate = yes for a checkpoint that has to be passed. Group title and Day "
                 "title only need to be on the first row of each section. On the Path sheet, Cadence is Calendar weeks, Working "
                 "days or Self-paced; leave \"Second level is called\" empty for no second level; \"Unnumbered sections\" lists the "
                 "Group numbers of sections shown by their title instead of a number, such as a Before you start section.")
CADENCE_NAMES = {"weeks": "Calendar weeks", "days": "Working days", "self": "Self-paced"}


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
        ws.append([gi + 1, g["title"] if first_g else "", (di + 1) if levels_of(content)[1] else "",
                   d["title"] if first_d else "", st["title"], st["details"], (st["link"] or {}).get("url", ""),
                   st["type"], "yes" if st["gate"] else "", ])
    for col, w in zip("ABCDEFGHI", (8, 30, 6, 30, 60, 70, 50, 11, 7)):
        ws.column_dimensions[col].width = w
    info = wb.create_sheet("Path")
    top, sub = levels_of(content)
    unnumbered = ", ".join(str(gi + 1) for gi, g in enumerate(content["groups"]) if g.get("numbered", True) is False)
    for row in (["Title", content.get("title", "")], ["Who it's for", content.get("blurb", "")], ["Length", content.get("length", "")],
                ["Cadence", CADENCE_NAMES[cadence_of(content)]], ["Top level is called", top], ["Second level is called", sub],
                ["Unnumbered sections", unnumbered], [], ["How to fill in the Steps sheet", TEMPLATE_NOTE]):
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
        cad = str(meta.get("Cadence") or meta.get("Pace") or "").strip().lower()  # "Pace" in files made before "Cadence"
        content["cadence"] = "self" if cad.startswith("self") else "days" if cad.startswith("working") else "weeks"
        top = str(meta.get("Top level is called") or "").strip() or levels_of(content)[0]
        if "Second level is called" in meta:
            sub = str(meta.get("Second level is called") or "").strip()
        else:
            sub = "Day" if str(meta.get("Days inside each group") or "yes").strip().lower() not in ("no", "false", "0") else ""
        content["levels"] = {"top": top, "sub": sub}
        unnumbered = {int(x) for x in re.findall(r"\d+", str(meta.get("Unnumbered sections") or ""))}
    else:
        unnumbered = set()
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
        content["levels"] = {"top": levels_of(content)[0], "sub": "Day" if any_day else ""}
    content["groups"] = [{"title": groups[k]["title"], "numbered": k not in unnumbered,
                          "days": [groups[k]["days"][dk] for dk in sorted(groups[k]["days"])]} for k in sorted(groups)]
    return normalize(content)
