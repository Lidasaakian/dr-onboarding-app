"""Background jobs that use the LLM: collecting sources, generating a path, editing a draft, writing a Jira bug.

Jobs run in threads; the page polls GET api/admin/jobs/<id> for progress. Results stay in memory for an hour.
"""

from __future__ import annotations

import concurrent.futures as cf
import copy
import json
import logging
import re
import secrets
import threading
import time

import requests

import custom_paths as cp
from llm import Gateway, LLMError
from sources import Collector, public_url, selected_sources

log = logging.getLogger("onboarding.generate")

JOBS: dict[str, dict] = {}
_lock = threading.Lock()
CHUNK = 14_000
SINGLE_PASS_CHARS = 110_000
NOTES_LIMIT = 160_000


def start(kind: str, owner: str, fn, *args) -> dict:
    jid = secrets.token_urlsafe(9)
    job = {"id": jid, "kind": kind, "owner": owner, "status": "running", "progress": [], "result": None, "error": "",
           "created": time.time(), "data": {}}
    with _lock:
        for k in [k for k, j in JOBS.items() if j["created"] < time.time() - 3600]:
            JOBS.pop(k, None)
        JOBS[jid] = job

    def run():
        try:
            job["result"] = fn(job, *args)
            job["status"] = "done"
        except Exception as e:  # report every failure to the page
            log.exception("Job %s (%s) failed", jid, kind)
            job["status"] = "error"
            job["error"] = str(e) if isinstance(e, (LLMError, ValueError)) else f"{type(e).__name__}: {e}"
    threading.Thread(target=run, daemon=True).start()
    return job


def public(job: dict) -> dict:
    return {k: job[k] for k in ("id", "kind", "status", "progress", "result", "error")}


def step(job: dict, text: str, done: bool = False) -> None:
    """Progress lines: the last one is the step in progress until the next one arrives."""
    if job["progress"] and not job["progress"][-1]["done"]:
        job["progress"][-1]["done"] = True
    job["progress"].append({"text": text, "done": done})


def finish(job: dict, text: str) -> None:
    """Mark the step in progress as done, with its final wording."""
    if job["progress"] and not job["progress"][-1]["done"]:
        job["progress"][-1].update(text=text, done=True)
    else:
        job["progress"].append({"text": text, "done": True})


def note(job: dict, text: str) -> None:
    """Replace the text of the step in progress (for 'reading issue 3 of 19…')."""
    if job["progress"] and not job["progress"][-1]["done"]:
        job["progress"][-1]["text"] = text
    else:
        job["progress"].append({"text": text, "done": False})


# --------------------------------------------------------------------------- 1. find sources

def find_sources(job: dict, atl, links: list[str], files: list[dict], gh_token: str) -> dict:
    step(job, "Reading your links and files…")
    col = Collector(atl, gh_token, progress=lambda m: note(job, m))
    found = col.collect(links, files)
    job["data"]["collector"] = col
    finish(job, f"Found about {found['pages']} page{'s' if found['pages'] != 1 else ''} of material")
    return found


def add_sources(job: dict, col: Collector, links: list[str], files: list[dict]) -> dict:
    """Read more links and files into sources already found. What was read before isn't read again, and its items
    keep their ids, so the author's ticks still apply."""
    step(job, "Reading the new links and files…")
    col.progress = lambda m: note(job, m)
    found = col.collect(links, files)
    job["data"]["collector"] = col
    finish(job, f"Found about {found['pages']} page{'s' if found['pages'] != 1 else ''} of material in all")
    return found


# --------------------------------------------------------------------------- 2. generate

SYSTEM_GENERATE = """You design hands-on onboarding learning paths for DataRobot employees: support engineers, solution architects,
engineers and product managers who need to learn a product feature quickly and use it with customers.

Rules:
- Use only facts from the source material provided. Never invent product names, menu paths, button labels, API names,
  parameters, limits or URLs. If the sources don't say how to do something, leave it out.
- Every step is one concrete thing the learner does (read, watch, try, build, check), 15-45 minutes.
  "title": a short imperative sentence (max 140 characters). "details": how to do it and how they know it's done,
  with the exact names from the sources (2-5 sentences, plain text; "- " bullets allowed).
- Prefer hands-on labs in the product over reading. Add a few "Check yourself:" questions.
- "type": "Required" for the core, "Stretch" for deeper material, "Optional" for nice-to-have extras.
- "gate": true only for checkpoints the learner must pass (for example the end of a week); at most one per group.
- "link": only a URL that appears in the sources (the best page for that step), or null.
- "source": the ids of the sources the step is based on, for example "S3, S7".
- Issues marked as not shipped describe work in progress: don't teach them as available features.
- Write in plain American English, second person ("you"). No marketing language.

Structure: the author has chosen it and it's given in the request. Follow it exactly.
- "groups" are the top-level sections. Each group's "days" are its second-level sections. When the path has no second
  level, give every group exactly one entry in "days" with an empty title.
- Calendar weeks: each numbered group is one week (5 working days of work). Working days: each second-level section
  is one working day, or each group when there's no second level (4-8 steps a day). Self-paced: no schedule; size the
  sections by topic.
- Use the approximate length to decide how many sections and steps to make.
- "numbered": false only for a "Before you start" section, when the request asks for one. It comes first, is titled
  "Before you start", holds what has to be in place before the path starts (access, setup, background) and has no gate.
  Every other group is numbered.
"""

SCHEMA = """{"title": str, "blurb": "one sentence: who it's for and what they'll be able to do", "length": "for example 1 week",
 "groups": [{"title": str, "numbered": bool, "days": [{"title": str, "steps": [{"title": str, "details": str, "link": {"url": str, "label": str} | null,
   "type": "Required"|"Stretch"|"Optional", "gate": bool, "source": str}]}]}],
 "unused": [{"source": "S5", "reason": "why it wasn't used"}]}"""

SYSTEM_NOTES = """You turn product material into study notes for someone building a hands-on learning path.
Keep everything a learner needs: what the feature does and why it matters, prerequisites and access, step-by-step UI or API usage
with exact menu names, buttons, commands, parameters and limits, examples, common problems, and the URLs that go with them
(copy URLs exactly). Leave out internal implementation detail unless it's needed to use the feature. Note if the material says
something is not shipped yet. Write compact notes with headings and bullets, at most about 900 words."""


def _chunks(text: str) -> list[str]:
    if len(text) <= CHUNK:
        return [text]
    out, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        if len(cur) + len(para) > CHUNK and cur:
            out.append(cur)
            cur = ""
        cur += para[:CHUNK] + "\n\n"
    if cur.strip():
        out.append(cur)
    return out


def _catalog(srcs: list[dict]) -> tuple[dict[str, dict], str]:
    ids = {}
    lines = []
    for i, s in enumerate(srcs, 1):
        sid = f"S{i}"
        ids[sid] = s
        lines.append(f"{sid}: {s['title']}" + (f" — {s['url']}" if s.get("url") and s["url"].startswith("http") else "") + (" [image]" if s.get("image") else ""))
    return ids, "\n".join(lines)


def generate_path(job: dict, llm: Gateway, col: Collector, unchecked: set[str], settings: dict) -> dict:
    srcs = selected_sources(col, unchecked)
    if not srcs:
        raise ValueError("Nothing is selected to read. Tick at least one source.")
    ids, catalog = _catalog(srcs)
    total = sum(len(s["text"]) for s in srcs)
    images = [(sid, s) for sid, s in ids.items() if s.get("image")]

    kinds = {}
    for s in srcs:
        kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
    names = {"jira": "Jira issue", "confluence": "Confluence page", "github": "GitHub file", "web": "web page", "file": "file", "image": "image"}
    step(job, "Read " + ", ".join(f"{n} {names.get(k, k)}{'s' if n != 1 else ''}" for k, n in kinds.items()), done=True)

    # map: notes per source chunk (skipped when everything fits in one request)
    if total <= SINGLE_PASS_CHARS:
        material = "\n\n".join(f"=== {sid}: {s['title']} ===\n{s['text']}" for sid, s in ids.items() if s["text"])
    else:
        jobs = [(sid, s, c) for sid, s in ids.items() if s["text"] for c in _chunks(s["text"])]
        step(job, f"Summarizing {len(jobs)} parts of the material…")
        notes: dict[str, list[str]] = {}
        done = [0]

        def one(t):
            sid, s, c = t
            r = llm.chat("generate", SYSTEM_NOTES, f"Source {sid}: {s['title']}\n\n{c}", max_tokens=2500)
            done[0] += 1
            note(job, f"Summarizing the material: {done[0]} of {len(jobs)} parts…")
            return sid, r
        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            for sid, r in ex.map(one, jobs):
                notes.setdefault(sid, []).append(r)
        material = "\n\n".join(f"=== {sid}: {ids[sid]['title']} ===\n" + "\n".join(v) for sid, v in notes.items())
        finish(job, f"Summarized {len(jobs)} parts of the material")
        if len(material) > NOTES_LIMIT:
            step(job, "Condensing the notes…")
            parts = _chunks(material)
            with cf.ThreadPoolExecutor(max_workers=4) as ex:
                material = "\n\n".join(ex.map(lambda c: llm.chat("generate", SYSTEM_NOTES + " Keep the source ids (S1, S2…) next to each fact.", c, max_tokens=3000), parts))
            finish(job, "Condensed the notes")

    length = settings.get("length") or "Whatever fits the material"
    shape_of = cp.structure_from(settings)
    top, sub = cp.blank_content("", **shape_of)["levels"].values()
    cadence = {"weeks": "Calendar weeks", "days": "Working days", "self": "Self-paced"}[shape_of["cadence"]]
    shape = (f"Cadence: {cadence}\nTop-level sections are called: {top}\n"
             f"Second level inside each section: {sub + ' (in days)' if sub else 'none (one untitled entry in days)'}\n"
             f"Start with a \"Before you start\" section: {'yes' if shape_of['before_start'] else 'no'}\n")
    request = (f"{shape}Approximate length: {length}\nWho it's for: {settings.get('audience') or 'DataRobot employees new to this feature'}\n"
               f"Path name: {settings.get('title') or '(suggest one)'}\n"
               f"Notes from the author: {settings.get('notes') or '(none)'}\n\n"
               f"Sources:\n{catalog}\n\nReturn JSON in this shape:\n{SCHEMA}\n\nSource material:\n\n{material}")
    content = [{"type": "text", "text": request}]
    for sid, s in images[:8]:
        content.append({"type": "text", "text": f"Image {sid}: {s['title']}"})
        content.append({"type": "image_url", "image_url": {"url": f"data:{s['image']['mime']};base64,{s['image']['b64']}"}})
    step(job, "Planning the path and writing the steps…")
    raw = llm.chat_json("generate", SYSTEM_GENERATE, content, max_tokens=16000)
    if not isinstance(raw, dict) or not raw.get("groups"):
        raise ValueError("The LLM didn't return a learning path. Try again, or add notes for the LLM.")

    # sources: S-ids -> titles; coverage
    used: set[str] = set()
    for g in raw.get("groups") or []:
        for d in (g.get("days") or [{"steps": g.get("steps") or []}]):
            for st in d.get("steps") or []:
                refs = re.findall(r"S\d+", str(st.get("source") or ""))
                used |= set(refs)
                st["source"] = ", ".join(ids[r]["title"] for r in refs if r in ids)[:300]
    raw["skill"] = {"enabled": bool(settings.get("skillEnabled")), "name": settings.get("skillName") or ""}
    raw["cadence"], raw["levels"] = shape_of["cadence"], {"top": top, "sub": sub}  # the author's choice wins over the LLM's
    raw.pop("pace", None), raw.pop("level", None), raw.pop("useDays", None)
    groups = [g for g in raw.get("groups") or [] if isinstance(g, dict)]
    if shape_of["before_start"] and not (groups and groups[0].get("numbered") is False):
        groups.insert(0, {"title": "Before you start", "days": [{"title": "", "steps": []}]})
    for gi, g in enumerate(groups):
        g["numbered"] = not (shape_of["before_start"] and gi == 0)
    raw["groups"] = groups
    if settings.get("title"):
        raw["title"] = settings["title"]
    if not raw.get("blurb") and settings.get("audience"):
        raw["blurb"] = settings["audience"]
    content_out = cp.normalize(raw)
    n = cp.step_count(content_out)
    gates = sum(1 for *_, st in cp.steps(content_out) if st["gate"])
    labs = sum(1 for *_, st in cp.steps(content_out) if re.match(r"(lab\b|lab \d|try|build|create|deploy|set up)", st["title"], re.I))
    lvl = cp.levels_of(content_out)[0].lower()
    finish(job, f"Planned {len(content_out['groups'])} {lvl}{'s' if len(content_out['groups']) != 1 else ''}, {n} steps"
           + (f", {labs} hands-on" if labs else "") + (f", {gates} gate{'s' if gates != 1 else ''}" if gates else ""))

    step(job, "Checking every link…")
    broken = check_links([st["link"]["url"] for *_, st in cp.steps(content_out) if st.get("link")])
    finish(job, "Checked every link" + (f": {len(broken)} didn't open" if broken else ""))

    unused_reason = {u.get("source"): u.get("reason", "") for u in raw.get("unused") or [] if isinstance(u, dict)}
    unused = [{"title": ids[sid]["title"], "reason": unused_reason.get(sid, "")} for sid in ids if sid not in used]
    warnings = []
    for g in col.groups:
        for w in g["warnings"]:
            warnings.append(w["title"] + ". " + w["text"])
    return {"content": content_out, "coverage": {"used": len([s for s in ids if s in used]), "total": len(ids), "unused": unused},
            "broken": broken, "warnings": warnings}


def check_links(urls: list[str]) -> list[str]:
    """Public links that don't open (Atlassian, GitHub and other signed-in links are skipped)."""
    todo = [u for u in dict.fromkeys(urls) if not re.search(r"atlassian\.net|github\.com|google\.com", u)][:40]

    def ok(u):
        if not public_url(u):
            return True
        try:
            r = requests.head(u, timeout=8, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code in (403, 405, 501):
                r = requests.get(u, timeout=10, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}, stream=True)
            return r.status_code < 400
        except requests.RequestException:
            return False
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(ok, todo))
    return [u for u, good in zip(todo, res) if not good]


# --------------------------------------------------------------------------- 3. edit a draft with the LLM

SYSTEM_EDIT = """You edit an onboarding learning path for DataRobot employees, following the author's instruction exactly.
Keep everything the instruction doesn't ask you to change exactly as it is, including ids. Give new items the id "new".
Keep the step style: "title" a short imperative sentence, "details" how to do it and how they know it's done, "type"
Required/Stretch/Optional, "gate" true only for must-pass checkpoints, "link" {"url", "label"} or null. Don't invent product
facts or URLs that aren't already in the path or in the instruction. Plain American English."""


def _scope(content: dict, scope: dict):
    t, sid = (scope or {}).get("type") or "path", (scope or {}).get("id")
    for gi, g in enumerate(content["groups"]):
        if t == "group" and g["id"] == sid:
            return "group", (gi,), g
        for di, d in enumerate(g["days"]):
            if t == "day" and d["id"] == sid:
                return "day", (gi, di), d
            for si, st in enumerate(d["steps"]):
                if t == "step" and st["id"] == sid:
                    return "step", (gi, di, si), st
    return "path", (), content


def edit_draft(job: dict, llm: Gateway, content: dict, instruction: str, scope: dict) -> dict:
    content = cp.normalize(content)
    kind, where, part = _scope(content, scope)
    lvl, sub = cp.levels_of(content)
    step(job, "Reading the draft…", done=True)
    step(job, "Writing the changes…")
    if kind == "path":
        outline = json.dumps({k: content[k] for k in ("title", "blurb", "cadence", "levels")} | {"groups": content["groups"]}, ensure_ascii=False)
        ask = (f"Instruction: {instruction}\n\nThe whole path (top-level groups are called {lvl!r}"
               + (f", their days hold the second level, called {sub!r}" if sub else ", no second level: one untitled entry in days")
               + '; "numbered": false marks a section shown by its title, such as Before you start'
               + f"):\n{outline}\n\n"
               'Return JSON: {"title": str (only if it should change), "blurb": str (only if it should change), '
               '"groups": [only the groups you add or change, each complete with its days and steps], '
               '"order": [every group id in the new order, "new-1", "new-2"… for added groups in the same order as in "groups"]}. '
               'Added groups use the id "new-1", "new-2"… Groups left out of "order" are deleted.')
        raw = llm.chat_json("generate", SYSTEM_EDIT, ask, max_tokens=16000)
        new = copy.deepcopy(content)
        changed = {g.get("id"): g for g in raw.get("groups") or [] if isinstance(g, dict)}
        order = [str(x) for x in raw.get("order") or []] or [g["id"] for g in content["groups"]]
        existing = {g["id"]: g for g in content["groups"]}
        groups = []
        for gid in order:
            if gid in changed:
                g = changed[gid]
                if gid.startswith("new"):
                    g["id"] = "new"
                elif gid in existing and "numbered" not in g:
                    g["numbered"] = existing[gid].get("numbered", True)
                groups.append(g)
            elif gid in existing:
                groups.append(existing[gid])
        for gid, g in changed.items():  # changed groups missing from order: keep them where they were
            if gid in existing and gid not in order:
                groups.append(g)
        new["groups"] = groups
        for k in ("title", "blurb"):
            if raw.get(k):
                new[k] = raw[k]
    else:
        label = {"group": lambda: cp.section_label(content, where[0]), "day": lambda: cp.where_label(content, where[0], where[1]),
                 "step": lambda: f"one step of {cp.section_label(content, where[0])}"}[kind]()
        shape = {"group": '{"id", "title", "days": [{"id", "title", "steps": [...]}]}',
                 "day": '{"id", "title", "steps": [...]}',
                 "step": '{"steps": [the step, rewritten; or several steps if the instruction asks to split it]}'}[kind]
        ask = (f"Instruction: {instruction}\n\nChange only this part ({label}):\n{json.dumps(part, ensure_ascii=False)}\n\n"
               f"For context, the path is {content['title']!r}; top-level groups are called {lvl!r}.\n\nReturn JSON in this shape: {shape}")
        raw = llm.chat_json("generate", SYSTEM_EDIT, ask, max_tokens=12000)
        new = copy.deepcopy(content)
        if kind == "group":
            if isinstance(raw, dict) and raw.get("days") is not None:
                raw["id"] = content["groups"][where[0]]["id"]
                raw["numbered"] = content["groups"][where[0]].get("numbered", True)
                new["groups"][where[0]] = raw
        elif kind == "day":
            if isinstance(raw, dict) and raw.get("steps") is not None:
                raw["id"] = content["groups"][where[0]]["days"][where[1]]["id"]
                new["groups"][where[0]]["days"][where[1]] = raw
        else:
            sts = raw.get("steps") if isinstance(raw, dict) else raw
            if isinstance(sts, list) and sts:
                if isinstance(sts[0], dict):
                    sts[0]["id"] = part["id"]
                d = new["groups"][where[0]]["days"][where[1]]["steps"]
                d[where[2]:where[2] + 1] = sts
    new = cp.normalize(new)
    changes = cp.diff(content, new)
    finish(job, f"{len(changes)} change{'s' if len(changes) != 1 else ''} suggested")
    if not changes:
        raise ValueError("The LLM didn't change anything. Try saying more precisely what should change.")
    return {"content": new, "changes": changes}


# --------------------------------------------------------------------------- 4. a learner's bug -> Jira issue text

SYSTEM_BUG = """You turn a learner's bug report about the DataRobot product into a clear Jira Bug for engineering, and pick the
Jira project of the team that owns the broken feature.

You get DataRobot's engineering org page from Confluence: pillars, pods, what each owns (charters and functional areas) and
their Jira projects. It changes often and may contain an older structure further down. Decide which pod owns the feature
using the newest structure on the page, then use that pod's Jira project key. If the newest structure doesn't list a Jira
project for that pod, use the Jira project an older table on the page gives for the same functional area. Use only project
keys that appear on the page or in the extra project list. If you can't tell, use the fallback project.

Write only what the report and the context support; don't guess causes.
Return JSON: {"project": "KEY", "pod": "the owning pod or team, as named on the page",
"summary": "one line, max 120 characters, what's broken and where",
"description": "plain text with these sections: ## What happened / ## Expected / ## Steps to reproduce (numbered, from the report and the learning-path step) / ## Environment / ## Links",
"why": "one sentence on why this pod and project"}."""


def bug_issue(llm: Gateway, report: dict, extra: list[dict], fallback: str, images: list[dict], org_page: str = "") -> dict:
    proj = "\n".join(f"- {r['key']}: {r['description']}" for r in extra)
    text = ((f"Engineering org page (pillars, pods and Jira projects):\n{org_page[:60000]}\n\n" if org_page else "")
            + (f"Extra projects:\n{proj}\n\n" if proj else "")
            + f"Fallback project: {fallback or '(none)'}\n\n"
            f"Learner: {report['name']} ({report['email']})\nLearning path: {report['pathTitle']}\nStep: {report.get('itemLabel') or '(general)'}\n"
            f"Step text: {report.get('stepText') or ''}\nBrowser: {report.get('browser') or ''}\nTime: {report.get('when') or ''}\n"
            f"Links: {', '.join(report.get('links') or []) or '(none)'}\nAttached files: {', '.join(a['name'] for a in report.get('files') or []) or '(none)'}\n\n"
            f"Report:\n{report['message']}")
    content = [{"type": "text", "text": text}]
    for im in images[:4]:
        content.append({"type": "image_url", "image_url": {"url": f"data:{im['mime']};base64,{im['b64']}"}})
    j = llm.chat_json("reports", SYSTEM_BUG, content, max_tokens=2000)
    return {"project": str(j.get("project") or "").upper().strip(), "pod": str(j.get("pod") or "")[:120],
            "summary": str(j.get("summary") or report["message"][:100]).strip()[:250],
            "description": str(j.get("description") or report["message"]), "why": str(j.get("why") or "")}
