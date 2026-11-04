"""DataRobot onboarding hub, served as a DataRobot custom application.

Pages
    /                    hub: your paths (progress, pace, badges); admins also get team progress,
                         CSV export, the problem-reports inbox and content updates
    /ai-engineer/        AI Engineer learning plan
    /agentic/            Agentic AI learning path

Learner API (every path page uses <path>/api/...)
    GET  api/me                        who is viewing
    GET  api/summary                   your progress, pace and badge on every path
    GET  <path>/api/progress           your saved state for the path      PUT saves it
    GET  <path>/api/status             your start date, cohort, pace and badge
    PUT  <path>/api/start              set your start date ({"date": "YYYY-MM-DD"}); admins may add "learner"
    POST <path>/api/reports            report a problem ({"message", "itemId", "itemLabel", "anchor"})

Admin API (MANAGER_EMAILS only)
    GET  <path>/api/team               everyone's state for the path, with pace, cohort and badge
    GET  api/team-summary              everyone, every path
    GET  api/export.csv[?cohort=...]   the same as CSV
    GET  api/reports                   the problem-reports inbox      POST api/reports/<id> {"status"}
    GET  api/admin/content             where each path's content comes from
    POST api/admin/content/<path>/preview   upload a new .xlsx (AI Engineer) or page (Agentic): returns what changes
    POST api/admin/content/<path>/publish   {"token"} make the previewed upload live
    POST api/admin/content/<path>/revert    go back to the deployed content
    GET  api/admin/content/agentic/page     download the live Agentic page (to edit and upload)
    GET  api/health                    storage, Slack and configuration problems

Learner records live in the DataRobot Files item PROGRESS_FILES_ID (see storage.py). The Agentic path keeps its
original place in each record (record["state"]) so progress saved by the first version of the app carries over;
other paths live under record["paths"][<path id>]; start dates under record["start"][<path id>].
"""

from __future__ import annotations

import base64
import csv
import datetime as dt
import io
import json
import logging
import os
import re
import secrets
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import quote, unquote, urlencode
from zoneinfo import ZoneInfo

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

import ai_engineer_content
import custom_paths as cp
import generate as gen
from atlassian import Atlassian, AtlassianError
from llm import Gateway, LLMError
from notify import Slack, SlackBot, link as slack_link, welcome_text
from paths import INACTIVE_DAYS, agentic_model, ai_engineer_model, cohort_of, inactive_days, validate_agentic_page
from roles import Users
from storage import DocStore, ProgressStore, make_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("onboarding")

APP_DIR = Path(__file__).resolve().parent
STATIC = APP_DIR / "static"
TZ = ZoneInfo("Europe/Dublin")
MAX_STATE_BYTES = 300_000
MAX_UPLOAD_BYTES = 5_000_000


def runtime_param(name: str, default: str = "") -> str:
    """DataRobot injects runtime parameters as MLOPS_RUNTIME_PARAM_<NAME>, sometimes JSON-encoded as
    {"type": ..., "payload": ...}; plain env vars work for local runs."""
    raw = (os.getenv(f"MLOPS_RUNTIME_PARAM_{name}") or os.getenv(name) or "").strip()
    if raw.startswith("{"):
        try:
            payload = json.loads(raw).get("payload")
            if isinstance(payload, dict):  # credential-type parameters
                payload = payload.get("apiToken") or payload.get("token") or payload.get("password") or ""
            return default if payload in (None, "") else str(payload).strip()
        except (ValueError, AttributeError):
            pass
    return raw or default


def runtime_credential(name: str) -> dict:
    """A credential-type runtime parameter: DataRobot passes {"type": "credential", "payload": {"credentialType": ...,
    "apiToken": ...}} (API token) or {... "username": ..., "password": ...} (basic). A plain string works as a token."""
    raw = (os.getenv(f"MLOPS_RUNTIME_PARAM_{name}") or os.getenv(name) or "").strip()
    if raw.startswith("{"):
        try:
            payload = json.loads(raw).get("payload")
            if isinstance(payload, dict):
                return payload
        except (ValueError, AttributeError):
            pass
    return {"apiToken": raw} if raw else {}


ENDPOINT = (os.getenv("DATAROBOT_ENDPOINT") or "").rstrip("/")
APP_TOKEN = os.getenv("DATAROBOT_API_TOKEN") or ""
MANAGER_EMAILS = {e.strip().lower() for e in runtime_param("MANAGER_EMAILS").split(",") if e.strip()}
LOCAL = not ENDPOINT

backend, STORAGE_PROBLEMS = make_storage(ENDPOINT, APP_TOKEN, runtime_param("PROGRESS_FILES_ID"), Path(os.getenv("DATA_DIR", APP_DIR / "data")))
store = ProgressStore(backend)
docs = DocStore(backend)
slack = Slack(runtime_param("SLACK_WEBHOOK_URL"), runtime_param("APP_URL"))
_bot_cred = runtime_credential("SLACK_BOT_TOKEN")
slackbot = SlackBot(str(_bot_cred.get("apiToken") or _bot_cred.get("token") or _bot_cred.get("password") or ""), runtime_param("APP_URL"))
users = Users(docs, MANAGER_EMAILS)
_jira_cred = runtime_credential("JIRA_API_TOKEN")
atl = Atlassian(runtime_param("JIRA_URL", "https://datarobot.atlassian.net"),
                runtime_param("JIRA_EMAIL") or str(_jira_cred.get("username") or ""),  # a basic credential can carry the email too
                str(_jira_cred.get("apiToken") or _jira_cred.get("token") or _jira_cred.get("password") or ""))
llm = Gateway(ENDPOINT, APP_TOKEN or os.getenv("LLM_GATEWAY_TOKEN", ""), runtime_param("LLM_MODEL_GENERATE"), runtime_param("LLM_MODEL_REPORTS"), os.getenv("LLM_GATEWAY_URL", ""))
LINKEDIN_ORG_ID = runtime_param("LINKEDIN_ORGANIZATION_ID")
# Who made the built-in paths (shown with a photo next to the length; paths made in the app show their creator)
BUILTIN_AUTHORS = {"ai-engineer": "raghavendran.nehru@datarobot.com", "agentic": "lidiia.saakian@datarobot.com"}
JIRA_ISSUE_TYPE = "Bug"  # learners' reports are always filed as Bugs
JIRA_FALLBACK = runtime_param("JIRA_FALLBACK_PROJECT").upper()
JIRA_ROUTING_PAGE = runtime_param("JIRA_ROUTING_PAGE", "https://datarobot.atlassian.net/wiki/spaces/ENG/overview")
_routing: dict = {"text": "", "title": "", "at": 0.0, "error": "", "keys": set()}
_routing_lock = threading.Lock()


def routing_page(force: bool = False) -> dict:
    """The Confluence page with the engineering org (pillars, pods, Jira projects), read with the service account and
    kept for 3 hours, so the LLM always routes bugs by the current structure."""
    from sources import confluence_page_id, html_to_text
    with _routing_lock:
        if not JIRA_ROUTING_PAGE or not atl.enabled:
            return _routing
        if not force and _routing["text"] and time.time() - _routing["at"] < 3 * 3600:
            return _routing
        if not force and _routing["error"] and time.time() - _routing["at"] < 600:
            return _routing
        try:
            pid = confluence_page_id(JIRA_ROUTING_PAGE, atl)
            if not pid:
                raise AtlassianError("JIRA_ROUTING_PAGE isn't a Confluence page link.")
            page = atl.page(pid)
            text = html_to_text(((page.get("body") or {}).get("storage") or {}).get("value", ""))
            _routing.update(text=text, title=page.get("title") or "", at=time.time(), error="",
                            keys=set(re.findall(r"\b[A-Z][A-Z0-9_]{1,9}\b", text)))
        except AtlassianError as e:
            log.warning("Couldn't read the Jira routing page: %s", e)
            _routing.update(at=time.time(), error=str(e)[:300])
        return _routing


def jira_routing() -> list[dict]:
    """Optional JIRA_PROJECTS: extra projects on top of the routing page, one per line (or separated by ;) as
    "KEY: what it owns". JSON lists work too."""
    raw = runtime_param("JIRA_PROJECTS")
    out = []
    try:
        data = json.loads(raw) if raw.startswith("[") else None
    except ValueError:
        data = None
    if isinstance(data, list):
        for r in data:
            if isinstance(r, dict) and r.get("key"):
                out.append({"key": str(r["key"]).upper().strip(), "description": str(r.get("description") or "")})
        return out
    for part in re.split(r"[\n;]+", raw):
        m = re.match(r"\s*([A-Za-z][A-Za-z0-9_]+)\s*[:=-]\s*(.*)", part)
        if m:
            out.append({"key": m.group(1).upper(), "description": m.group(2).strip()})
    return out


def today() -> dt.date:
    return dt.datetime.now(TZ).date()


def now_ms() -> float:
    return time.time() * 1000


# --------------------------------------------------------------------------- learning paths (live content)

DEPLOYED_AI = json.loads((STATIC / "ai-engineer" / "content.json").read_text(encoding="utf-8"))
AI_TEMPLATE = (STATIC / "ai-engineer" / "index.html").read_text(encoding="utf-8")
DEPLOYED_AGENTIC = (STATIC / "agentic" / "index.html").read_text(encoding="utf-8")
HUB_HTML = (STATIC / "index.html").read_text(encoding="utf-8")
PATH_TEMPLATE = (STATIC / "path" / "index.html").read_text(encoding="utf-8")
PATHS: dict = {}
CUSTOM: dict[str, dict] = {}   # every path created in the app (drafts too), by id
_paths_lock = threading.Lock()


def custom_page(doc: dict, content: dict | None) -> str:
    """The generic learning-path page, with the live content built in (drafts load theirs after sign-in)."""
    data = {"id": doc["id"], "status": doc.get("status"), "content": content}
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return PATH_TEMPLATE.replace("<!--PATH_JSON-->", f'<script id="path-data" type="application/json">{blob}</script>')


def load_custom() -> None:
    """Load the paths made in the app (at startup). Jobs live in memory, so a path still "generating" was cut off by
    a restart: it becomes "failed" and its owners can try again."""
    global CUSTOM
    found = {}
    for name in docs.names("path-"):
        d = docs.get(name)
        if isinstance(d, dict) and d.get("id"):
            if d.get("status") == "generating":
                d["status"], d["error"] = "failed", "Generation was interrupted by an app restart."
                docs.put(name, d)
            found[d["id"]] = d
    CUSTOM = found


def _live_ai() -> tuple[dict, dict]:
    ov = docs.get("content-ai-engineer")
    if ov and not ov.get("reverted") and ov["content"]["meta"]["generatedAt"] >= DEPLOYED_AI["meta"]["generatedAt"]:
        return ov["content"], {"kind": "uploaded", "at": ov["publishedAt"], "by": ov["publishedBy"], "file": ov.get("file", "")}
    note = "A newer upload exists but the deployed sheet is newer, so the deployed one is live." if ov and not ov.get("reverted") else ""
    return DEPLOYED_AI, {"kind": "deployed", "at": DEPLOYED_AI["meta"]["generatedAt"], "note": note}


_MAIN = re.compile(r'(<main id="main">)(.*?)(</main>)', re.S)


def splice_main(page: str, main: str) -> str:
    if not _MAIN.search(page):
        raise ValueError("The live page has no <main> section to update.")
    main = re.sub(r"<script\b.*?</script>", "", main, flags=re.S | re.I)  # never accept scripts from the editor
    return _MAIN.sub(lambda m: m.group(1) + "\n" + main + "\n  " + m.group(3), page, count=1)


def _live_agentic() -> tuple[str, dict]:
    """The Agentic page learners see. Saved edits keep only their <main> content: it goes into the page deployed with
    the app, so fixes to the page's scripts and styles reach learners even while edits are live."""
    ov = docs.get("content-agentic")
    if ov and not ov.get("reverted"):
        src = {"kind": "uploaded", "at": ov["publishedAt"], "by": ov["publishedBy"], "file": ov.get("file", "")}
        m = _MAIN.search(ov["html"])
        if m:
            try:
                return splice_main(DEPLOYED_AGENTIC, m.group(2)), src
            except ValueError:
                log.warning("The deployed Agentic page has no <main>; serving the saved page as it is")
        return ov["html"], src
    return DEPLOYED_AGENTIC, {"kind": "deployed"}


def activate_content() -> None:
    global PATHS
    ai_content, ai_src = _live_ai()
    agentic_html, ag_src = _live_agentic()
    new = {
        "ai-engineer": ai_engineer_model(ai_content, AI_TEMPLATE, ai_src),
        "agentic": agentic_model(agentic_html, ag_src),
    }
    new["ai-engineer"].content = ai_content
    for pid, doc in sorted(CUSTOM.items(), key=lambda kv: kv[1].get("publishedAt") or 0):
        if doc.get("status") in ("published", "archived") and doc.get("live"):
            try:
                new[pid] = cp.model(doc, doc["live"], custom_page(doc, doc["live"]))
                new[pid].archived = doc["status"] == "archived"  # enrolled learners keep it, read-only
            except Exception:
                log.exception("Couldn't load path %s", pid)
    with _paths_lock:
        PATHS = new
    log.info("Content live: %s", {k: (v.source.get("kind"), len(v.items)) for k, v in new.items()})


load_custom()
activate_content()


def is_custom(pid: str) -> bool:
    return pid in CUSTOM


def path_state(record: dict | None, path_id: str) -> dict | None:
    if not record:
        return None
    if path_id == "agentic":
        return record.get("state")
    return (record.get("paths") or {}).get(path_id)


def start_of(record: dict | None, path_id: str) -> str | None:
    """The learner's start date for a path. Records from before start dates existed fall back to the
    first-activity time the page saved (state.startedAt)."""
    if not record:
        return None
    s = (record.get("start") or {}).get(path_id)
    if s:
        return s
    st = path_state(record, path_id) or {}
    stamps = [st.get("startedAt")] + list((st.get("done") or {}).values())
    stamps = [t for t in stamps if isinstance(t, (int, float)) and t > 10**11]
    if not stamps and st.get("done") and isinstance(st.get("updatedAt"), (int, float)):
        stamps = [st["updatedAt"]]  # ticks without usable times: best guess is the last save
    if stamps:
        return dt.datetime.fromtimestamp(min(stamps) / 1000, TZ).date().isoformat()
    return None


def is_enrolled(record: dict | None, pid: str) -> bool:
    """Enrolled = clicked Enroll (or ticked a step, which asks to enroll). Learners who had ticks before
    enrollment existed count as enrolled. Admins can remove someone ({"removed": true})."""
    e = ((record or {}).get("enrolled") or {}).get(pid)
    if isinstance(e, dict):
        return not e.get("removed")
    return bool((path_state(record, pid) or {}).get("done"))


def enrolled_at(record: dict | None, pid: str) -> float | None:
    e = ((record or {}).get("enrolled") or {}).get(pid)
    if isinstance(e, dict) and not e.get("removed") and isinstance(e.get("at"), (int, float)):
        return e["at"]
    s = start_of(record, pid)
    return dt.datetime.combine(dt.date.fromisoformat(s), dt.time(9), TZ).timestamp() * 1000 if s and is_enrolled(record, pid) else None


def mascot_stage(summary: dict) -> int:
    """0-10: one anniversary mascot per tenth of the required steps."""
    d, t = summary["requiredDone"], summary["requiredTotal"]
    return 10 if t and d >= t else (10 * d // t if t else 0)


def item_href(pid: str, item_id: str) -> str:
    p = PATHS[pid]
    for i in p.items:
        if i.id == item_id:
            prefix = "s-" if getattr(p, "custom", False) else "i-" if pid == "ai-engineer" else "t-"
            return f"{pid}/#" + prefix + re.sub(r"[^A-Za-z0-9_-]", "-", i.id)
    return f"{pid}/"


def learner_path_view(record: dict | None, pid: str) -> dict:
    p = PATHS[pid]
    st = path_state(record, pid) or {}
    enrolled = is_enrolled(record, pid)
    start = start_of(record, pid) if enrolled else None
    badge = p.badge(st)
    kept = ((record or {}).get("badges") or {}).get(pid)
    if not badge["earned"] and kept:  # once earned, a badge stays, even if new required rows are added later
        badge = {"earned": True, "at": kept.get("at")}
    nxt = p.first_open(st)
    summary = p.summarize(st)
    stage = max(mascot_stage(summary), int(((record or {}).get("mascots") or {}).get(pid) or 0))  # mascots never shrink
    stars = st.get("stars") or {}
    return {
        **summary,
        "skill": p.skill,
        "skillEnabled": getattr(p, "skill_enabled", True),
        "custom": getattr(p, "custom", False),
        "archived": getattr(p, "archived", False),
        "enrolled": enrolled,
        "start": start,
        "cohort": cohort_of(start),
        "pace": p.pace(st, start, today()) if enrolled else {"status": "not_enrolled", "label": "Not enrolled"},
        "badge": badge,
        "mascot": stage,
        "inactiveDays": inactive_days(st, badge["earned"], now_ms()) if enrolled else 0,
        "nowOn": nxt.label if nxt else ("Finished" if badge["earned"] else ""),
        "track": st.get("track") or "",
        "option": st.get("option") or "",
        "length": p.length,
        "author": {k: v for k, v in path_author(pid).items() if k != "email"},
        "starred": [{"id": i, "label": p.label_of(i), "href": item_href(pid, i)}
                    for i in sorted(stars, key=lambda k: stars[k], reverse=True) if i in p.ids or i.startswith("cert.")][:50],
    }


# --------------------------------------------------------------------------- identity

_profiles: dict[str, dict] = {}


def safe_key(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.@-]", "_", (s or "").strip().lower())[:120]


def _profile(request: Request) -> dict:
    """Who is visiting (cached). DataRobot's app proxy adds X-DataRobot-User-Id and a visitor-scoped API key
    (X-DATAROBOT-API-KEY) for DataRobot users; people opening an externally shared link arrive with X-USER-EMAIL."""
    uid = (request.headers.get("x-datarobot-user-id") or "").strip()
    email = (request.headers.get("x-user-email") or "").strip()
    visitor_key = (request.headers.get("x-datarobot-api-key") or "").strip()
    cache_key = uid or email or visitor_key[-12:]
    if cache_key and cache_key in _profiles:
        return _profiles[cache_key]

    name = ""
    if visitor_key and ENDPOINT:
        try:
            r = requests.get(f"{ENDPOINT}/account/info/", headers={"Authorization": f"Bearer {visitor_key}"}, timeout=8)
            if r.ok:
                info = r.json()
                uid = uid or str(info.get("uid") or info.get("id") or "")
                email = email or str(info.get("email") or "")
                name = " ".join(x for x in [info.get("firstName"), info.get("lastName")] if x) or str(info.get("username") or "")
            else:
                log.warning("account/info returned %s", r.status_code)
        except requests.RequestException:
            log.exception("Could not look up the visitor's profile")

    if not uid and not email:
        if not LOCAL:  # deployed but no identity headers: refuse rather than mixing everyone into one record
            raise HTTPException(status_code=401, detail="Could not identify you. Open the app from its DataRobot link.")
        uid = os.getenv("DEV_USER_ID", "local-dev")
        email = os.getenv("DEV_USER_EMAIL", "dev@example.com")
        name = os.getenv("DEV_USER_NAME", "Local developer")

    if not name and email:
        name = email.split("@")[0].replace(".", " ").title()
    prof = {"id": store.resolve_key(safe_key(uid), safe_key(email), email), "name": name or "Learner", "email": email}
    if cache_key:
        _profiles[cache_key] = prof
    return prof


def identify(request: Request) -> dict:
    """The visitor plus their roles. Roles are read on every request, so changes apply on the next click."""
    prof = _profile(request)
    email = prof["email"].lower()
    roles = users.roles_of(email)
    system = users.is_system(email)
    if LOCAL and email == os.getenv("DEV_USER_EMAIL", "dev@example.com").lower() and os.getenv("DEV_MANAGER", "1") == "1":
        roles.add("admin")  # running locally without identity headers: you're a system admin
        system = True
    owns = sorted(pid for pid, doc in CUSTOM.items() if email and email in [o.lower() for o in doc.get("owners") or []])
    users.seen(email, prof["name"])
    return {"app": "dr-onboarding", **prof,
            "roles": sorted(roles), "isManager": "admin" in roles, "isAuthor": "author" in roles or "admin" in roles,
            "isSystemAdmin": bool(system), "owns": owns,
            "canAdmin": "admin" in roles or "author" in roles or bool(owns),
            "welcome": welcome_banner(email)}


def welcome_banner(email: str) -> dict | None:
    """The banner on the hub for roles given and not acknowledged yet (it stays until "Got it")."""
    w = users.welcome_of(email)
    if not w:
        return None
    return {"roles": w["roles"], "label": "New roles" if len(w["roles"]) > 1 else "New role", **welcome_text(w["roles"], w.get("by", ""))}


def require_path(path_id: str):
    if path_id not in PATHS:
        raise HTTPException(status_code=404, detail="Unknown learning path.")
    return PATHS[path_id]


def require_manager(me: dict) -> None:
    if not me["isManager"]:
        raise HTTPException(status_code=403, detail="Admins only.")


def can_manage(me: dict, pid: str) -> bool:
    """Admins manage every path; owners manage theirs (built-in paths have no owners)."""
    return bool(me["isManager"] or pid in me["owns"])


def require_manage(me: dict, pid: str) -> None:
    if not can_manage(me, pid):
        raise HTTPException(status_code=403, detail="Only this path's owners and the admins can do this.")


def require_admin_page(me: dict) -> None:
    if not me["canAdmin"]:
        raise HTTPException(status_code=403, detail="Admins and authors only.")


def managed_paths(me: dict) -> list[str]:
    return [pid for pid in PATHS if can_manage(me, pid)]


async def json_body(request: Request, limit: int = MAX_STATE_BYTES) -> dict:
    body = await request.body()
    if len(body) > limit:
        raise HTTPException(status_code=413, detail="Request too large.")
    try:
        data = json.loads(body or b"{}")
    except ValueError:
        raise HTTPException(status_code=400, detail="Body must be JSON.")
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object.")
    return data


# --------------------------------------------------------------------------- app

app = FastAPI(title="DataRobot onboarding", docs_url=None, redoc_url=None)
NO_CACHE = {"Cache-Control": "no-cache"}


@app.get("/", response_class=HTMLResponse)
def hub() -> HTMLResponse:
    return HTMLResponse(HUB_HTML, headers=NO_CACHE)


@app.get("/assets/{name:path}")
def asset(name: str) -> FileResponse:
    root = (STATIC / "assets").resolve()
    p = (root / name).resolve()
    if root not in p.parents or not p.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(p, headers=NO_CACHE)


@app.get("/api/me")
def api_me(request: Request) -> dict:
    return identify(request)


@app.get("/api/summary")
def api_summary(request: Request) -> dict:
    me = identify(request)
    rec = store.get(me["id"])
    out = {
        "me": me,
        "paths": [{"id": pid, "title": p.title, "skill": p.skill, "blurb": p.blurb, "length": p.length, **learner_path_view(rec, pid)}
                  for pid, p in PATHS.items() if not getattr(p, "archived", False) or is_enrolled(rec, pid)],
    }
    if me["canAdmin"]:
        out["openReports"] = sum(1 for r in visible_reports(me) if r.get("status") == "open")
    return out


def visible_reports(me: dict) -> list[dict]:
    """System admins see everything; admins see learners' reports on every path; owners see their paths' reports.
    Reports to the system admins (from the Users tab) are for system admins only."""
    out = []
    for r in docs.get("reports", []):
        kind = r.get("kind") or "path"
        if kind == "system":
            if me["isSystemAdmin"]:
                out.append(r)
        elif me["isManager"] or r.get("path") in me["owns"]:
            out.append(r)
    return out


# ------------------------------------------------------------------ team (admins)

def team_rows(pids: list[str] | None = None) -> list[dict]:
    rows = []
    pids = list(PATHS) if pids is None else pids
    for key, rec in store.all().items():
        paths = {pid: learner_path_view(rec, pid) for pid in pids}
        if not any(v["enrolled"] for v in paths.values()):
            continue
        starts = sorted(v["start"] for v in paths.values() if v["start"])
        last = max([(v["updatedAt"] or 0) for v in paths.values()] or [0])
        rows.append({
            "id": key, "name": rec.get("name") or rec.get("email") or "", "email": rec.get("email") or "",
            "cohort": cohort_of(starts[0]) if starts else "",
            "lastActive": last or None,
            "inactiveDays": max([v["inactiveDays"] for v in paths.values()] or [0]),
            "paths": paths,
        })
    rows.sort(key=lambda r: r["lastActive"] or 0, reverse=True)
    return rows


def cohort_sort_key(c: str):
    try:
        return dt.datetime.strptime(c, "%b %Y")
    except ValueError:
        return dt.datetime.min


@app.get("/api/team-summary")
def api_team_summary(request: Request) -> dict:
    me = identify(request)
    require_admin_page(me)
    pids = managed_paths(me)
    rows = team_rows(pids)
    cohorts = sorted({r["cohort"] for r in rows if r["cohort"]}, key=cohort_sort_key, reverse=True)
    left = [{"name": rec.get("name") or rec.get("email") or "", "email": rec.get("email") or "", "path": pid,
             "pathTitle": PATHS[pid].title, "at": e.get("at")}
            for rec in store.all().values() for pid in pids
            for e in [((rec.get("enrolled") or {}).get(pid))] if isinstance(e, dict) and e.get("left")]
    left.sort(key=lambda x: x["at"] or 0, reverse=True)
    return {"paths": [{"id": pid, "title": PATHS[pid].title, "unit": PATHS[pid].unit_name,
                       "archived": getattr(PATHS[pid], "archived", False)} for pid in pids],
            "learners": rows, "cohorts": cohorts, "inactiveAfterDays": INACTIVE_DAYS, "left": left}


@app.get("/api/export.csv")
def api_export(request: Request, cohort: str = "") -> Response:
    me = identify(request)
    require_admin_page(me)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Learner", "Email", "Cohort (first start month)", "Path", "Start date", "Path cohort", "Progress %", "Rows done",
                "Rows total", "Required done", "Required total", "Gates passed", "Gates total", "Pace", "Completed",
                "Completed on", "Now on", "Track", "Capstone option", "Last active (UTC)", "Days inactive"])
    for r in team_rows(managed_paths(me)):
        if cohort and r["cohort"] != cohort:
            continue
        for pid, v in r["paths"].items():
            if not v["enrolled"]:
                continue
            last = dt.datetime.fromtimestamp(v["updatedAt"] / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M") if v["updatedAt"] else ""
            w.writerow([r["name"], r["email"], r["cohort"], PATHS[pid].title, v["start"] or "", v["cohort"],
                        round(100 * v["done"] / v["total"]) if v["total"] else 0, v["done"], v["total"],
                        v["requiredDone"], v["requiredTotal"], v["gatesDone"] if v["gatesTotal"] else "", v["gatesTotal"] or "",
                        v["pace"]["label"], "yes" if v["badge"]["earned"] else "no", v["badge"].get("at") or "",
                        v["nowOn"], v["track"], v["option"], last, v["inactiveDays"] or ""])
    name = "onboarding-progress" + (f"-{cohort.replace(' ', '-').lower()}" if cohort else "") + f"-{today().isoformat()}.csv"
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ------------------------------------------------------------------ problem reports

@app.get("/api/reports")
def api_reports(request: Request) -> dict:
    me = identify(request)
    require_admin_page(me)
    reports = visible_reports(me)
    reports.sort(key=lambda r: r["createdAt"], reverse=True)
    for r in reports:
        r["kind"] = r.get("kind") or "path"
        for f in r.get("files") or []:
            f.pop("blob", None)
    meta = docs.get("meta", {}) or {}
    return {"reports": reports, "lastSync": meta.get("jiraSync"), "jira": atl.enabled}


@app.post("/api/reports/{report_id}")
async def api_report_status(report_id: str, request: Request) -> dict:
    me = identify(request)
    require_admin_page(me)
    status = (await json_body(request)).get("status")
    if status not in ("open", "resolved"):
        raise HTTPException(status_code=400, detail='status must be "open" or "resolved".')
    if not any(r["id"] == report_id for r in visible_reports(me)):
        raise HTTPException(status_code=404, detail="No such report.")

    def change(reports):
        for r in reports:
            if r["id"] == report_id:
                r["status"] = status
                r["resolvedBy"] = me["name"] if status == "resolved" else ""
                r["resolvedAt"] = now_ms() if status == "resolved" else None
                r["manualStatus"], r["autoResolved"] = True, False  # from now on the Jira sync leaves the status alone
                return r
        return None

    r = docs.mutate("reports", [], change)
    if not r:
        raise HTTPException(status_code=404, detail="No such report.")
    return {"ok": True, "report": r}


# ------------------------------------------------------------------ content updates (admins)

_pending: dict[str, dict] = {}


def ticks_on(item_ids: set[str], pid: str) -> int:
    """How many learners have ticked at least one of these steps (so admins see who an upload affects)."""
    n = 0
    for rec in store.all().values():
        done = (path_state(rec, pid) or {}).get("done") or {}
        if item_ids & set(done):
            n += 1
    return n


@app.get("/api/admin/content")
def api_content_status(request: Request) -> dict:
    require_manager(identify(request))
    return {"paths": [{"id": pid, "title": p.title, "steps": len(p.items), "source": p.source} for pid, p in PATHS.items() if not is_custom(pid)]}


def dedupe_steps(page: str) -> str:
    """Editing can copy a step (pressing Enter in a list item duplicates its data-t). Give copies new ids."""
    seen: dict[str, int] = {}

    def fix(m):
        tid = m.group(1)
        seen[tid] = seen.get(tid, 0) + 1
        return m.group(0) if seen[tid] == 1 else f'data-t="{tid}-n{seen[tid]}"'
    return re.sub(r'data-t="([^"]+)"', fix, page)


@app.get("/api/admin/content/ai-engineer/export.xlsx")
def api_ai_export(request: Request) -> Response:
    require_manager(identify(request))
    data = ai_engineer_content.export_xlsx(PATHS["ai-engineer"].content)
    name = f"AI Engineer Learning Plan ({today().isoformat()}).xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/admin/content/ai-engineer/content.json")
def api_ai_content(request: Request) -> dict:
    require_manager(identify(request))
    return PATHS["ai-engineer"].content


@app.get("/api/admin/content/agentic/page")
def api_agentic_download(request: Request) -> Response:
    require_manager(identify(request))
    return Response(PATHS["agentic"].html, media_type="text/html",
                    headers={"Content-Disposition": 'attachment; filename="agentic-index.html"'})


@app.post("/api/admin/content/{path_id}/preview")
async def api_content_preview(path_id: str, request: Request) -> dict:
    me = identify(request)
    require_manager(me)
    p = require_path(path_id)
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="The file is empty.")
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than 5 MB.")
    file_name = request.headers.get("x-file-name", "")[:200]
    in_app = (request.headers.get("content-type") or "").startswith("application/json")
    try:
        if path_id == "ai-engineer":
            prev = getattr(p, "content", None)
            if in_app:  # edited in the app
                content = json.loads(body).get("content")
                ai_engineer_content.validate_content(content)
                content["meta"] = {**(prev or {}).get("meta", {}), **content.get("meta", {})}
                old_i, new_i = ai_engineer_content.item_index(prev or {}), ai_engineer_content.item_index(content)
                diff = {"weeks": len(content["weeks"]), "rows": sum(len(w["items"]) for w in content["weeks"] + content.get("anyWeek", [])),
                        "options": len(content["options"]["options"]), "certs": len(content["certs"]["rows"]),
                        "added": [{"id": i, "label": new_i[i]} for i in sorted(set(new_i) - set(old_i))],
                        "removed": [{"id": i, "label": old_i[i]} for i in sorted(set(old_i) - set(new_i))]}
                file_name = "edited in the app"
            else:
                content, diff = ai_engineer_content.build(body, prev)
            new_model = ai_engineer_model(content, AI_TEMPLATE, {})
            payload = {"content": content}
            summary = {
                "counts": f"{diff['weeks']} weeks, {diff['rows']} plan steps, {diff['options']} capstone options, {diff['certs']} certifications",
                "added": diff["added"], "removed": diff["removed"],
            }
        else:
            if in_app:  # the page's <main> edited in the app: put it back into the live page
                main = json.loads(body).get("main") or ""
                html = splice_main(p.html, main)
                file_name = "edited in the app"
            else:
                html = body.decode("utf-8")
            html = dedupe_steps(html)
            validate_agentic_page(html)
            new_model = agentic_model(html, {})
            old_ids, new_ids = p.ids, new_model.ids
            payload = {"html": html}
            summary = {
                "counts": f"{len(new_ids)} steps",
                "added": [{"id": i, "label": new_model.label_of(i)} for i in sorted(new_ids - old_ids)],
                "removed": [{"id": i, "label": p.label_of(i)} for i in sorted(old_ids - new_ids)],
            }
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="That file isn't a UTF-8 HTML page.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # openpyxl raises many types for a wrong file
        log.exception("Upload preview failed")
        raise HTTPException(status_code=400, detail=f"Couldn't read the file ({type(e).__name__}). Is it the right file type?")
    summary["learnersAffected"] = ticks_on({r["id"] for r in summary["removed"]}, path_id)
    summary["stepsBefore"], summary["stepsAfter"] = len(p.items), len(new_model.items)
    token = secrets.token_urlsafe(12)
    for k in [k for k, v in _pending.items() if v["expires"] < time.time()]:
        _pending.pop(k, None)
    _pending[token] = {"path": path_id, "payload": payload, "file": file_name, "expires": time.time() + 3600}
    return {"token": token, "summary": summary}


@app.post("/api/admin/content/{path_id}/publish")
async def api_content_publish(path_id: str, request: Request) -> dict:
    me = identify(request)
    require_manager(me)
    require_path(path_id)
    token = (await json_body(request)).get("token", "")
    pend = _pending.pop(token, None)
    if not pend or pend["path"] != path_id or pend["expires"] < time.time():
        raise HTTPException(status_code=400, detail="This preview has expired. Upload the file again.")
    doc = {**pend["payload"], "publishedAt": now_ms(), "publishedBy": me["name"], "file": pend["file"]}
    if path_id == "ai-engineer":
        # make sure the upload wins over the deployed file (it was generated just now)
        doc["content"]["meta"]["generatedAt"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    docs.put(f"content-{path_id}", doc)
    activate_content()
    return {"ok": True, "source": PATHS[path_id].source, "steps": len(PATHS[path_id].items)}


@app.post("/api/admin/content/{path_id}/revert")
def api_content_revert(path_id: str, request: Request) -> dict:
    me = identify(request)
    require_manager(me)
    require_path(path_id)
    docs.put(f"content-{path_id}", {"reverted": True, "publishedAt": now_ms(), "publishedBy": me["name"]})
    activate_content()
    return {"ok": True, "source": PATHS[path_id].source}


# ------------------------------------------------------------------ dashboard (admins)

def week_start(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


@app.get("/api/dashboard")
def api_dashboard(request: Request, weeks: int = 12) -> dict:
    me = identify(request)
    require_admin_page(me)
    pids = [pid for pid in managed_paths(me) if not getattr(PATHS[pid], "archived", False)]
    weeks = max(4, min(weeks, 52))
    now = now_ms()
    this_week = week_start(today())
    starts = [this_week - dt.timedelta(weeks=weeks - 1 - i) for i in range(weeks)]
    idx = {d: i for i, d in enumerate(starts)}
    paths_out = {}
    learners_any, active_any = set(), set()
    for pid in pids:
        p = PATHS[pid]
        tiles = {"enrolled": 0, "newThisMonth": 0, "active7": 0, "notStarted": 0, "completed": 0, "completed30": 0,
                 "onTrack": 0, "behind": 0, "ahead": 0, "reqPctSum": 0.0}
        active = [set() for _ in starts]
        ticks = [0] * weeks
        enrolls = [0] * weeks
        month_ago = now - 30 * 86_400_000
        for key, rec in store.all().items():
            if not is_enrolled(rec, pid):
                continue
            v = learner_path_view(rec, pid)
            st = path_state(rec, pid) or {}
            tiles["enrolled"] += 1
            learners_any.add(key)
            ea = enrolled_at(rec, pid)
            if ea and ea >= month_ago:
                tiles["newThisMonth"] += 1
            if ea:
                wi = idx.get(week_start(dt.datetime.fromtimestamp(ea / 1000, TZ).date()))
                if wi is not None:
                    enrolls[wi] += 1
            if not v["started"]:
                tiles["notStarted"] += 1
            if v["badge"]["earned"]:
                tiles["completed"] += 1
                at = v["badge"].get("at")
                if at and dt.date.fromisoformat(at) >= today() - dt.timedelta(days=30):
                    tiles["completed30"] += 1
            s = v["pace"]["status"]
            if s in ("on_track", "finished"):
                tiles["onTrack"] += 1
            elif s == "behind":
                tiles["behind"] += 1
            elif s == "ahead":
                tiles["ahead"] += 1
            tiles["reqPctSum"] += (v["requiredDone"] / v["requiredTotal"]) if v["requiredTotal"] else 0
            for item_id, ts in (st.get("done") or {}).items():
                if item_id not in p.ids or not isinstance(ts, (int, float)) or ts < 10**11:
                    continue
                wi = idx.get(week_start(dt.datetime.fromtimestamp(ts / 1000, TZ).date()))
                if wi is not None:
                    ticks[wi] += 1
                    active[wi].add(key)
            last = st.get("updatedAt")
            if isinstance(last, (int, float)) and last >= now - 7 * 86_400_000 and st.get("done"):
                tiles["active7"] += 1
                active_any.add(key)
        n = tiles.pop("reqPctSum")
        tiles["avgRequiredPct"] = round(100 * n / tiles["enrolled"]) if tiles["enrolled"] else 0
        paths_out[pid] = {"title": p.title, "tiles": tiles, "activeLearners": [len(a) for a in active], "ticks": ticks, "enrollments": enrolls}
    return {
        "weeks": [d.isoformat() for d in starts],
        "paths": paths_out,
        "order": pids,
        "overall": {"learners": len(learners_any), "active7": len(active_any),
                    "openReports": sum(1 for r in visible_reports(me) if r.get("status") == "open")},
    }


ADMIN_HTML = (STATIC / "admin.html").read_text(encoding="utf-8")


@app.get("/admin/", response_class=HTMLResponse)
def admin_page() -> HTMLResponse:
    return HTMLResponse(ADMIN_HTML, headers=NO_CACHE)


@app.get("/admin", response_class=HTMLResponse)
def admin_page_no_slash() -> HTMLResponse:
    return RedirectResponse("admin/", status_code=307)


# ------------------------------------------------------------------ health

@app.get("/api/health")
def api_health() -> dict:
    files_id = getattr(backend, "files_id", None)
    problems = list(STORAGE_PROBLEMS)
    if getattr(backend, "created_new", False):
        problems.append(f"Set the PROGRESS_FILES_ID runtime parameter to {files_id} so progress survives restarts.")
    if not MANAGER_EMAILS and not LOCAL:
        problems.append("MANAGER_EMAILS is empty: nobody can see Team progress.")
    if not slack.enabled:
        problems.append("SLACK_WEBHOOK_URL is not set: problem reports and the weekly summary stay in the app only.")
    elif slack.last_error:
        problems.append(slack.last_error)
    if (slack.enabled or slackbot.enabled) and not slack.app_url:
        problems.append("APP_URL is not set: Slack messages won't link back to the app.")
    if not slackbot.enabled:
        problems.append("SLACK_BOT_TOKEN is not set: people given a role see the welcome banner in the app, but get no Slack DM.")
    elif slackbot.last_error:
        problems.append(slackbot.last_error)
    routing = jira_routing()
    page = routing_page() if atl.enabled else _routing
    if not atl.enabled:
        problems.append("JIRA_EMAIL / JIRA_API_TOKEN are not set: bug reports go to the admins instead of Jira, and paths can't read Jira or Confluence.")
    else:
        if page["error"]:
            problems.append(f"Couldn't read the Jira routing page ({JIRA_ROUTING_PAGE}): {page['error']}")
        if not JIRA_FALLBACK:
            problems.append("JIRA_FALLBACK_PROJECT is not set: a bug whose project the LLM can't work out can't be filed in Jira.")
        elif not atl.takes_bugs(JIRA_FALLBACK, JIRA_ISSUE_TYPE):
            problems.append(f"JIRA_FALLBACK_PROJECT {JIRA_FALLBACK} doesn't exist, or the service account can't create Bugs in it.")
    if atl.last_error:
        problems.append(atl.last_error)
    catalog = llm.catalog() if llm.enabled else []
    if not llm.enabled:
        problems.append("The LLM Gateway isn't available (no DataRobot endpoint or token): creating paths from sources and LLM edits are off.")
    elif not catalog and not (llm.model_for("generate") and llm.model_for("reports")):
        problems.append(llm.last_error or "The LLM Gateway catalog is empty.")
    return {
        "storage": backend.mode,
        "progressFilesId": files_id,
        "managers": len(MANAGER_EMAILS),
        "slack": slack.enabled,
        "slackBot": slackbot.enabled,
        "jira": {"connected": atl.enabled, "site": atl.url, "issueType": JIRA_ISSUE_TYPE, "fallback": JIRA_FALLBACK,
                 "routingPage": {"url": JIRA_ROUTING_PAGE, "title": page["title"], "readAt": page["at"] or None, "error": page["error"]},
                 "extraProjects": [r["key"] for r in routing]},
        "llm": {"available": llm.enabled, "generate": llm.model_for("generate") if llm.enabled else "", "reports": llm.model_for("reports") if llm.enabled else "",
                "catalog": [m["model"] for m in catalog][:200]},
        "paths": {pid: {"steps": len(p.items), "content": p.source.get("kind")} for pid, p in PATHS.items()},
        "customPaths": {pid: d.get("status") for pid, d in CUSTOM.items()},
        "problems": problems,
    }


# ------------------------------------------------------------------ file uploads (bug reports, path sources)

UPLOAD_DIR = Path(tempfile.gettempdir()) / "onboarding-uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_FILE = 20_000_000
_uploads: dict[str, dict] = {}


def _clean_uploads() -> None:
    for k, u in list(_uploads.items()):
        if u["at"] < time.time() - 3 * 3600:
            _uploads.pop(k, None)
            try:
                (UPLOAD_DIR / k).unlink()
            except OSError:
                pass


@app.post("/api/uploads")
async def api_upload(request: Request) -> dict:
    """One file per request (raw body, name in X-File-Name). Returns an id to reference in a report or a path."""
    me = identify(request)
    _clean_uploads()
    mine = [u for u in _uploads.values() if u["owner"] == me["id"]]
    if len(mine) >= 60:
        raise HTTPException(status_code=429, detail="Too many files at once. Try again in a while.")
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="The file is empty.")
    if len(body) > MAX_FILE:
        raise HTTPException(status_code=413, detail="Each file can be at most 20 MB.")
    name = re.sub(r"[\\/\x00-\x1f]", "_", unquote(request.headers.get("x-file-name", "") or "file"))[:160] or "file"
    uid = secrets.token_urlsafe(10)
    (UPLOAD_DIR / uid).write_bytes(body)
    _uploads[uid] = {"id": uid, "name": name, "type": (request.headers.get("content-type") or "application/octet-stream")[:100],
                     "size": len(body), "owner": me["id"], "at": time.time()}
    return {"id": uid, "name": name, "size": len(body)}


def take_uploads(me: dict, ids: list, limit: int = 10) -> list[dict]:
    out = []
    for uid in (ids or [])[:limit]:
        u = _uploads.get(str(uid))
        if not u or u["owner"] != me["id"]:
            continue
        try:
            data = (UPLOAD_DIR / u["id"]).read_bytes()
        except OSError:
            continue
        out.append({**u, "data": data})
    return out


def keep_files(report_id: str, files: list[dict]) -> list[dict]:
    """Store report attachments with the app's data (when they can't go to Jira) and return their metadata."""
    meta = []
    for i, f in enumerate(files):
        blob = f"{report_id}-{i}-{re.sub(r'[^A-Za-z0-9._-]', '_', f['name'])[:80]}"
        try:
            backend.write_blob(blob, f["data"])
        except Exception:
            log.exception("Couldn't store %s", f["name"])
            blob = ""
        meta.append({"name": f["name"], "size": f["size"], "type": f["type"], "blob": blob})
    return meta


@app.get("/api/reports/{report_id}/files/{n}")
def api_report_file(report_id: str, n: int, request: Request) -> Response:
    me = identify(request)
    require_admin_page(me)
    r = next((x for x in visible_reports(me) if x["id"] == report_id), None)
    files = (r or {}).get("files") or []
    if not r or n < 0 or n >= len(files) or not files[n].get("blob"):
        raise HTTPException(status_code=404, detail="No such file.")
    data = backend.read_blob(files[n]["blob"])
    if data is None:
        raise HTTPException(status_code=404, detail="The file is no longer stored.")
    return Response(data, media_type=files[n].get("type") or "application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{quote(files[n]["name"])}"'})


# ------------------------------------------------------------------ Jira: learners' bug reports

def jira_ready() -> bool:
    return atl.enabled and bool(JIRA_ROUTING_PAGE or jira_routing() or JIRA_FALLBACK)


def send_bug_to_jira(report: dict, files: list[dict]) -> dict:
    """Write the issue with the LLM (project, summary, description), create it, attach the files."""
    images = []
    for f in files:
        if f["type"].startswith("image/") and f["size"] < 3_500_000:
            images.append({"mime": f["type"], "b64": base64.b64encode(f["data"]).decode()})
    extra = jira_routing()
    page = routing_page()
    try:
        issue = gen.bug_issue(llm, report, extra, JIRA_FALLBACK, images, page["text"])
    except Exception as e:  # no LLM: still file the bug, with the learner's own words
        log.warning("LLM couldn't write the Jira issue (%s); filing it as written", e)
        first = report["message"].strip().split("\n", 1)[0]
        issue = {"project": "", "pod": "", "summary": first[:120], "description": report["message"], "why": ""}
    # the LLM's pick must be a project named on the page (or in JIRA_PROJECTS) that takes Bugs; otherwise the fallback
    allowed = set(page["keys"]) | {r["key"] for r in extra}
    picked = issue["project"]
    if not (picked and picked in allowed and atl.takes_bugs(picked, JIRA_ISSUE_TYPE)):
        if picked:
            log.info("Project %r from the LLM can't take Bugs or isn't on the page; using the fallback", picked)
        issue["project"], issue["routedTo"] = JIRA_FALLBACK, "fallback"
    else:
        issue["routedTo"] = "page"
    if not issue["project"]:
        raise AtlassianError("The LLM couldn't pick a Jira project and JIRA_FALLBACK_PROJECT isn't set.")
    desc = (issue["description"].strip() + "\n\n## Reported from the onboarding app\n"
            f"- Learner: {report['name']} ({report['email']})\n- Learning path: {report['pathTitle']}\n"
            f"- Step: {report.get('itemLabel') or '(general)'}\n" + (f"- App link: {slack.url(report['path'] + '/#' + (report.get('anchor') or ''))}\n" if slack.app_url else ""))
    created = atl.create_bug(issue["project"], issue["summary"], desc, report["email"], JIRA_ISSUE_TYPE)
    attached = atl.attach(created["key"], [(f["name"], f["data"], f["type"]) for f in files]) if files else 0
    return {**created, "project": issue["project"], "pod": issue.get("pod", ""), "routedTo": issue.get("routedTo", ""),
            "summary": issue["summary"], "why": issue["why"], "attached": attached,
            "status": "Open", "category": "new", "syncedAt": now_ms(), "visible": True}


def sync_jira() -> dict:
    """Read the status of every report's Jira issue. Resolved in Jira -> Resolved here; reopened -> Open again."""
    reports = docs.get("reports", [])
    keys = sorted({r["jira"]["key"] for r in reports if (r.get("jira") or {}).get("key")})
    if not keys or not atl.enabled:
        return {"synced": 0}
    try:
        st = atl.statuses(keys)
    except AtlassianError as e:
        log.warning("Jira sync failed: %s", e)
        return {"synced": 0, "error": str(e)}

    def apply(reps):
        n = 0
        for r in reps:
            j = r.get("jira") or {}
            k = j.get("key")
            if not k:
                continue
            info = st.get(k)
            j["syncedAt"] = now_ms()
            if not info:
                j["visible"] = False
                continue
            n += 1
            j.update(info, visible=True)
            done = info["category"] == "done"
            if r.get("manualStatus"):
                pass  # resolved or reopened by hand: keep it that way
            elif done and r.get("status") != "resolved":
                r["status"], r["resolvedBy"], r["resolvedAt"], r["autoResolved"] = "resolved", "Jira", now_ms(), True
            elif not done and r.get("status") == "resolved" and r.get("autoResolved"):
                r["status"], r["resolvedBy"], r["resolvedAt"], r["autoResolved"] = "open", "", None, False
            r["jira"] = j
        return n
    n = docs.mutate("reports", [], apply)
    meta = docs.get("meta", {}) or {}
    meta["jiraSync"] = now_ms()
    docs.put("meta", meta)
    return {"synced": n}


def jira_loop() -> None:
    while True:
        time.sleep(15 * 60)
        try:
            sync_jira()
        except Exception:
            log.exception("Jira sync failed")


threading.Thread(target=jira_loop, daemon=True).start()


@app.post("/api/jira/sync")
def api_reports_sync(request: Request) -> dict:
    require_admin_page(identify(request))
    res = sync_jira()
    if res.get("error"):
        raise HTTPException(status_code=502, detail=f"Couldn't read Jira: {res['error']}")
    return {**res, "lastSync": (docs.get("meta", {}) or {}).get("jiraSync")}


# ------------------------------------------------------------------ users and roles (admins)

@app.get("/api/admin/users")
def api_users(request: Request) -> dict:
    me = identify(request)
    require_manager(me)
    owns: dict[str, list] = {}
    for pid, doc in CUSTOM.items():
        content = doc.get("live") or doc.get("draft") or {}
        for o in doc.get("owners") or []:
            owns.setdefault(o.lower(), []).append({"id": pid, "title": content.get("title") or pid, "status": doc.get("status")})
    rows = users.listing()
    for u in rows:
        u["owns"] = owns.get(u["email"], [])
        if not u["name"]:
            rec = next((r for r in store.all().values() if (r.get("email") or "").lower() == u["email"]), None)
            u["name"] = (rec or {}).get("name") or u["email"].split("@")[0].replace(".", " ").title()
    return {"users": rows, "me": me["email"].lower()}


@app.post("/api/admin/users")
async def api_user_invite(request: Request) -> dict:
    me = identify(request)
    require_manager(me)
    try:
        return {"user": users.invite((await json_body(request)).get("email", ""), me["name"])}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/admin/users/{email}")
async def api_user_roles(email: str, request: Request) -> dict:
    me = identify(request)
    require_manager(me)
    roles = (await json_body(request)).get("roles") or []
    try:
        user = users.set_roles(unquote(email), roles, me["name"])
        if user["added"] and slackbot.enabled:  # a DM only for roles that are new to this person
            name = user["name"] or next((r.get("name") for r in store.all().values() if (r.get("email") or "").lower() == user["email"]), "") or ""
            slackbot.welcome(user["email"], name, user["added"], me["name"])
        return {"user": user}
    except PermissionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail="Invite this person first.")


@app.delete("/api/admin/users/{email}")
def api_user_remove(email: str, request: Request) -> dict:
    me = identify(request)
    require_manager(me)
    try:
        users.remove(unquote(email), me["name"])
    except PermissionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail="No such user.")
    return {"ok": True}


@app.post("/api/welcome/dismiss")
def api_welcome_dismiss(request: Request) -> dict:
    """ "Got it" on the welcome banner."""
    users.dismiss_welcome(identify(request)["email"])
    return {"ok": True}


@app.post("/api/admin/system-report")
async def api_system_report(request: Request) -> dict:
    """Admins report a problem with the app itself to the system admins (the MANAGER_EMAILS admins)."""
    me = identify(request)
    require_manager(me)
    data = await json_body(request, 40_000)
    message = str(data.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Write a short description of the problem.")
    rid = secrets.token_hex(6)
    files = keep_files(rid, take_uploads(me, data.get("uploads") or []))
    report = {"id": rid, "kind": "system", "path": "admin", "pathTitle": "Admin", "itemId": "",
              "itemLabel": str(data.get("about") or "Admin → Users")[:200], "anchor": "", "message": message[:4000],
              "learnerId": me["id"], "name": me["name"], "email": me["email"], "createdAt": now_ms(), "status": "open", "files": files}
    docs.mutate("reports", [], lambda reports: reports.append(report))
    slack.report({**report, "path": "admin", "pathTitle": "Admin (to the system admins)"})
    return {"ok": True}


# ------------------------------------------------------------------ paths created in the app (admins and authors)

def path_doc(pid: str, editable: bool = False) -> dict:
    """The stored path. editable: refuse a path that is still generating or whose generation failed."""
    doc = CUSTOM.get(pid)
    if not doc:
        raise HTTPException(status_code=404, detail="No such path.")
    if editable and doc.get("status") == "generating":
        raise HTTPException(status_code=409, detail="This draft is still being generated. Try again when it's ready.")
    if editable and doc.get("status") == "archived":
        raise HTTPException(status_code=409, detail="This path is archived. Restore it before editing.")
    if editable and doc.get("status") == "failed":
        raise HTTPException(status_code=409, detail="Generating this draft failed. Try again from Admin → Content, or delete it.")
    return doc


def save_path(doc: dict) -> None:
    doc["updatedAt"] = now_ms()
    docs.put(f"path-{doc['id']}", doc)
    CUSTOM[doc["id"]] = doc


def parse_owners(raw, creator: str) -> list[str]:
    from roles import normalize_email
    items = raw if isinstance(raw, list) else re.split(r"[,;\s]+", str(raw or ""))
    out = [creator.lower()] if creator else []
    for x in items:
        x = str(x).strip()
        if not x or x.lower() in ("you", "me"):
            continue
        try:
            e = normalize_email(x)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Owners: {x}: {e}")
        if e not in out:
            out.append(e)
    return out


def new_path(me: dict, content: dict, owners_raw="", origin: str = "app", status: str = "draft") -> dict:
    taken = set(CUSTOM) | set(PATHS)
    pid = cp.unique_slug(content.get("title") or "path", taken)
    doc = {"id": pid, "status": status, "owners": parse_owners(owners_raw, me["email"]), "createdBy": me["name"],
           "createdByEmail": me["email"].lower(), "createdAt": now_ms(), "origin": origin, "draft": cp.normalize(content), "live": None}
    save_path(doc)
    return doc


def path_row(pid: str, enrolled_counts: dict) -> dict:
    if pid in CUSTOM:
        d = CUSTOM[pid]
        c = d.get("draft") or d.get("live") or {}
        return {"id": pid, "title": c.get("title") or pid, "status": d.get("status"), "custom": True,
                "steps": cp.step_count(c), "enrolled": enrolled_counts.get(pid, 0), "owners": d.get("owners") or [],
                "unpublished": d.get("status") == "published" and d.get("draft") != d.get("live"), "updatedAt": d.get("updatedAt"),
                "createdAt": d.get("createdAt"), "createdByEmail": d.get("createdByEmail"), "error": d.get("error") or "",
                "wizard": d.get("wizard") if d.get("status") == "failed" else None}
    p = PATHS[pid]
    return {"id": pid, "title": p.title, "status": "published", "custom": False, "steps": len(p.items),
            "enrolled": enrolled_counts.get(pid, 0), "owners": [], "source": p.source}


@app.get("/api/admin/paths")
def api_paths(request: Request, generating: int = 0) -> dict:
    """Paths you manage. generating=1: only the ones you started generating that are still running or just failed,
    for the "draft is ready" notice (cheap enough to poll)."""
    me = identify(request)
    require_admin_page(me)
    if generating:
        mine = [d for d in CUSTOM.values() if (d.get("createdByEmail") or "") == me["email"].lower()
                and d.get("status") in ("generating", "failed", "draft") and d.get("origin") == "sources"]
        return {"paths": [{"id": d["id"], "title": (d.get("draft") or {}).get("title") or d["id"], "status": d["status"],
                           "error": d.get("error") or ""} for d in mine]}
    counts: dict[str, int] = {}
    for rec in store.all().values():
        for pid in PATHS:
            if is_enrolled(rec, pid):
                counts[pid] = counts.get(pid, 0) + 1
    ids = [pid for pid in PATHS if not is_custom(pid) and me["isManager"]] + \
          [pid for pid, d in sorted(CUSTOM.items(), key=lambda kv: kv[1].get("createdAt") or 0) if can_manage(me, pid)]
    return {"paths": [path_row(pid, counts) for pid in ids], "canCreate": me["isAuthor"], "jira": atl.enabled, "llm": llm.enabled,
            "slackDm": slackbot.enabled}


@app.get("/api/admin/paths/template.xlsx")
def api_path_template(request: Request) -> Response:
    require_admin_page(identify(request))
    return Response(cp.template_xlsx(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="Learning path template.xlsx"'})


@app.post("/api/admin/paths")
async def api_path_create(request: Request) -> dict:
    """Build in the app: an empty draft with the chosen structure."""
    me = identify(request)
    if not me["isAuthor"]:
        raise HTTPException(status_code=403, detail="Only admins and authors can create learning paths.")
    d = await json_body(request)
    content = cp.blank_content(d.get("title") or "", **cp.structure_from(d))
    content["blurb"] = str(d.get("blurb") or "")[:600]
    content["skill"] = {"enabled": bool(d.get("skillEnabled")), "name": str(d.get("skillName") or "")[:60]}
    doc = new_path(me, content, d.get("owners") or "")
    return {"id": doc["id"]}


def _job(me: dict, jid: str) -> dict:
    j = gen.JOBS.get(jid)
    if not j or j["owner"] != me["id"]:
        raise HTTPException(status_code=404, detail="This job has expired. Start again.")
    return j


@app.get("/api/admin/jobs/{jid}")
def api_job(jid: str, request: Request) -> dict:
    return gen.public(_job(identify(request), jid))


@app.post("/api/admin/paths/find")
async def api_path_find(request: Request) -> dict:
    """Create from source, step 1: read the links and files. The .xlsx template is imported as it is."""
    me = identify(request)
    if not me["isAuthor"]:
        raise HTTPException(status_code=403, detail="Only admins and authors can create learning paths.")
    d = await json_body(request, 60_000)
    links = [str(x).strip() for x in d.get("links") or [] if str(x).strip()][:20]
    files = take_uploads(me, d.get("uploads") or [], limit=20)
    if not links and not files:
        raise HTTPException(status_code=400, detail="Add at least one link or file.")
    if d.get("addTo"):  # "Read them too" on the review step: only the new links and files
        base = _job(me, str(d["addTo"]))
        col = base["data"].get("collector")
        if base["status"] != "done" or not col:
            raise HTTPException(status_code=400, detail="Wait until the sources have been read.")
        job = gen.start("find", me["id"], gen.add_sources, col, links, [{"name": f["name"], "data": f["data"], "type": f["type"]} for f in files])
        return {"job": job["id"]}
    for f in files:
        if f["name"].lower().endswith(".xlsx") and cp.is_template(f["data"]):
            try:
                content = cp.import_xlsx(f["data"])
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            st = d.get("settings") or {}
            if st.get("title"):
                content["title"] = st["title"]
            content["skill"] = {"enabled": bool(st.get("skillEnabled")), "name": str(st.get("skillName") or "")}
            doc = new_path(me, content, st.get("owners") or "", origin="template")
            return {"imported": doc["id"], "note": "The .xlsx template was imported as it is." + (" Your other links and files weren't used." if links or len(files) > 1 else "")}
    job = gen.start("find", me["id"], gen.find_sources, atl, links, [{"name": f["name"], "data": f["data"], "type": f["type"]} for f in files], str(d.get("githubToken") or ""))
    return {"job": job["id"]}


@app.post("/api/admin/paths/generate")
async def api_path_generate(request: Request) -> dict:
    me = identify(request)
    if not me["isAuthor"]:
        raise HTTPException(status_code=403, detail="Only admins and authors can create learning paths.")
    d = await json_body(request, 60_000)
    found = _job(me, str(d.get("job") or ""))
    col = found["data"].get("collector")
    if found["status"] != "done" or not col:
        raise HTTPException(status_code=400, detail="Wait until the sources have been read.")
    if not llm.enabled:
        raise HTTPException(status_code=503, detail="The LLM Gateway isn't available to the app, so it can't write a draft. Start empty instead, or try again later.")
    settings = d.get("settings") or {}
    parse_owners(settings.get("owners") or "", me["email"])  # fail now, not after a long run
    retry = CUSTOM.get(str(d.get("retryOf") or ""))
    if retry and retry.get("status") == "failed" and can_manage(me, retry["id"]):
        docs.delete(f"path-{retry['id']}")
        CUSTOM.pop(retry["id"], None)
    # The path exists from the start (status "generating"), so Admin -> Content shows it while the job runs, and
    # its answers are kept for "Try again" if the job fails or the app restarts.
    placeholder = cp.blank_content(settings.get("title") or "", **cp.structure_from(settings))
    placeholder["blurb"] = str(settings.get("audience") or "")[:600]
    doc = new_path(me, placeholder, settings.get("owners") or "", origin="sources", status="generating")
    doc["wizard"] = wizard_answers(d.get("wizard"), settings)
    save_path(doc)
    pid = doc["id"]

    def run(job):
        try:
            res = gen.generate_path(job, llm, col, set(d.get("unchecked") or []), settings)
        except Exception as e:
            cur = CUSTOM.get(pid)
            if cur and cur.get("status") == "generating":
                cur["status"] = "failed"
                cur["error"] = str(e) if isinstance(e, (LLMError, ValueError)) else "Something went wrong while generating the draft."
                save_path(cur)
            raise
        cur = CUSTOM.get(pid)
        if not cur or cur.get("status") != "generating":  # deleted while it ran
            return {"id": None}
        cur["draft"] = res["content"]
        cur["status"] = "draft"
        cur.pop("error", None)
        cur["generation"] = {"coverage": res["coverage"], "broken": res["broken"], "warnings": res["warnings"], "at": now_ms()}
        save_path(cur)
        title = res["content"]["title"]
        slackbot.dm(me["email"], f"Your learning path draft is ready: {slack_link(slackbot.url(pid + '/'), title)}")
        return {"id": pid, "coverage": res["coverage"], "broken": res["broken"], "warnings": res["warnings"]}
    job = gen.start("generate", me["id"], run)
    doc["job"] = job["id"]
    save_path(doc)
    return {"job": job["id"], "id": pid}


def wizard_answers(wizard, settings: dict) -> dict:
    """What the author entered in the wizard, kept on a generating path for "Try again". Tokens are never kept."""
    w = wizard if isinstance(wizard, dict) else {}
    w = {k: v for k, v in w.items() if k.lower() not in ("gh", "githubtoken", "token")}
    if len(json.dumps(w, ensure_ascii=False)) > 20_000:
        w = {}
    return {**w, "settings": settings}


@app.get("/api/admin/paths/{pid}")
def api_path_get(pid: str, request: Request) -> dict:
    me = identify(request)
    require_manage(me, pid)
    return {"path": path_doc(pid), "canEdit": True}


@app.put("/api/admin/paths/{pid}/draft")
async def api_path_save(pid: str, request: Request) -> dict:
    me = identify(request)
    require_manage(me, pid)
    doc = path_doc(pid, editable=True)
    d = await json_body(request, 3_000_000)
    try:
        doc["draft"] = cp.normalize(d.get("content") or {})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if "owners" in d:
        doc["owners"] = parse_owners(d.get("owners"), (doc.get("owners") or [me["email"]])[0])
    doc["editedBy"] = me["name"]
    save_path(doc)
    return {"ok": True, "draft": doc["draft"], "owners": doc["owners"], "updatedAt": doc["updatedAt"]}


@app.post("/api/admin/paths/{pid}/publish")
def api_path_publish(pid: str, request: Request) -> dict:
    me = identify(request)
    require_manage(me, pid)
    doc = path_doc(pid, editable=True)
    content = cp.normalize(doc["draft"])
    if not cp.step_count(content):
        raise HTTPException(status_code=400, detail="Add at least one step before publishing.")
    removed = []
    if doc.get("live"):
        old_ids = {st["id"] for *_, st in cp.steps(doc["live"])}
        removed = sorted(old_ids - {st["id"] for *_, st in cp.steps(content)})
    doc["live"], doc["draft"], doc["status"] = content, content, "published"
    doc["publishedAt"], doc["publishedBy"] = doc.get("publishedAt") or now_ms(), me["name"]
    doc["lastPublishedAt"] = now_ms()
    save_path(doc)
    activate_content()
    return {"ok": True, "url": f"{pid}/", "learnersAffected": ticks_on(set(removed), pid) if removed else 0}


@app.post("/api/admin/paths/{pid}/archive")
def api_path_archive(pid: str, request: Request) -> dict:
    """Published -> archived: hidden from the hub, no new enrollments, read-only for enrolled learners."""
    return set_archived(pid, request, True)


@app.post("/api/admin/paths/{pid}/restore")
def api_path_restore(pid: str, request: Request) -> dict:
    """Archived -> published again, with the same content."""
    return set_archived(pid, request, False)


def set_archived(pid: str, request: Request, archived: bool) -> dict:
    me = identify(request)
    require_manage(me, pid)
    doc = path_doc(pid)
    want_from = "published" if archived else "archived"
    if doc.get("status") != want_from:
        raise HTTPException(status_code=400, detail="Only a published path can be archived." if archived else "Only an archived path can be restored.")
    doc["status"] = "archived" if archived else "published"
    doc["archivedAt"], doc["archivedBy"] = (now_ms(), me["name"]) if archived else (None, None)
    save_path(doc)
    activate_content()
    return {"ok": True, "status": doc["status"]}


@app.delete("/api/admin/paths/{pid}")
def api_path_delete(pid: str, request: Request) -> dict:
    me = identify(request)
    require_manage(me, pid)
    doc = path_doc(pid)
    if doc.get("status") in ("published", "archived"):
        raise HTTPException(status_code=400, detail="A published or archived path can't be deleted. Archive it instead.")
    docs.delete(f"path-{pid}")
    CUSTOM.pop(pid, None)
    return {"ok": True}


@app.get("/api/admin/paths/{pid}/export.xlsx")
def api_path_export(pid: str, request: Request) -> Response:
    me = identify(request)
    require_manage(me, pid)
    doc = path_doc(pid)
    c = doc.get("draft") or doc.get("live")
    return Response(cp.export_xlsx(c), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{quote(c["title"])} ({today().isoformat()}).xlsx"'})


@app.post("/api/admin/paths/{pid}/llm-edit")
async def api_path_llm_edit(pid: str, request: Request) -> dict:
    me = identify(request)
    require_manage(me, pid)
    path_doc(pid, editable=True)
    d = await json_body(request, 3_000_000)
    instruction = str(d.get("instruction") or "").strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="Write what should change.")
    if not llm.enabled:
        raise HTTPException(status_code=503, detail="The LLM Gateway isn't available to the app.")
    job = gen.start("edit", me["id"], gen.edit_draft, llm, d.get("content") or CUSTOM[pid]["draft"], instruction[:3000], d.get("scope") or {})
    return {"job": job["id"]}


# Kept so that a browser tab opened on the first version of the app (Agentic path at /) can still save.
@app.get("/api/progress")
def api_get_progress_legacy(request: Request) -> dict:
    return api_get_progress("agentic", request)


@app.put("/api/progress")
async def api_put_progress_legacy(request: Request) -> dict:
    return await api_put_progress("agentic", request)


# ------------------------------------------------------------------ per path

@app.get("/{path_id}", response_class=HTMLResponse)
def path_page_no_slash(path_id: str) -> HTMLResponse:
    if path_id not in CUSTOM:
        require_path(path_id)  # relative redirect, so it works behind DataRobot's /custom_applications/<id>/ prefix
    return RedirectResponse(f"{path_id}/", status_code=307)


@app.get("/{path_id}/", response_class=HTMLResponse)
def path_page(path_id: str) -> HTMLResponse:
    if path_id in PATHS:
        return HTMLResponse(PATHS[path_id].html, headers=NO_CACHE)
    if path_id in CUSTOM:  # a draft: the page loads it after checking you're an owner or an admin
        return HTMLResponse(custom_page(CUSTOM[path_id], None), headers=NO_CACHE)
    raise HTTPException(status_code=404, detail="Unknown learning path.")


@app.get("/{path_id}/api/me")
def path_me(path_id: str, request: Request) -> dict:
    if path_id not in CUSTOM:
        require_path(path_id)
    return identify(request)


@app.get("/{path_id}/api/content")
def path_content(path_id: str, request: Request) -> dict:
    """Content of a path made in the app: the live version for everyone, plus the draft for owners and admins."""
    doc = CUSTOM.get(path_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Unknown learning path.")
    me = identify(request)
    out = {"id": path_id, "status": doc.get("status"), "live": doc.get("live"), "canEdit": can_manage(me, path_id),
           "jira": jira_ready()}
    if out["canEdit"]:
        out.update(draft=doc.get("draft"), owners=doc.get("owners") or [], generation=doc.get("generation"),
                   updatedAt=doc.get("updatedAt"), llm=llm.enabled)
    elif doc.get("status") != "published":
        raise HTTPException(status_code=404, detail="This learning path isn't published yet.")
    return out


@app.get("/{path_id}/api/progress")
def api_get_progress(path_id: str, request: Request) -> dict:
    require_path(path_id)
    me = identify(request)
    return {"state": path_state(store.get(me["id"]), path_id)}


@app.put("/{path_id}/api/progress")
async def api_put_progress(path_id: str, request: Request) -> dict:
    require_path(path_id)
    if getattr(PATHS[path_id], "archived", False):
        raise HTTPException(status_code=409, detail="This path is archived: progress can't be changed.")
    me = identify(request)
    state = (await json_body(request)).get("state")
    if not isinstance(state, dict) or not isinstance(state.get("done", {}), dict):
        raise HTTPException(status_code=400, detail="state.done must be an object.")
    checks = state.get("checks", {})  # checklist ticks inside steps: {step id: {item index: timestamp}}
    if not isinstance(checks, dict) or not all(isinstance(v, dict) for v in checks.values()):
        raise HTTPException(status_code=400, detail="state.checks must be an object of objects.")
    old = store.get(me["id"])
    old_view = learner_path_view(old, path_id)
    before, stage_before = old_view["badge"]["earned"], old_view["mascot"]

    def apply(rec):
        rec["name"], rec["email"] = me["name"], me["email"]
        if path_id == "agentic":
            rec["state"] = state
        else:
            rec.setdefault("paths", {})[path_id] = state
        starts = rec.setdefault("start", {})
        if not starts.get(path_id) and state.get("done"):
            starts[path_id] = start_of(rec, path_id) or today().isoformat()
        enr = rec.setdefault("enrolled", {})
        if state.get("done") and not (isinstance(enr.get(path_id), dict) and not enr[path_id].get("removed")):
            enr[path_id] = {"at": now_ms(), "date": starts[path_id]}

    rec = store.update(me["id"], apply)
    view = learner_path_view(rec, path_id)
    if (view["badge"]["earned"] and not before) or view["mascot"] > stage_before:
        def keep(r):
            if view["badge"]["earned"]:
                r.setdefault("badges", {}).setdefault(path_id, {"at": view["badge"].get("at") or today().isoformat()})
            r.setdefault("mascots", {})[path_id] = view["mascot"]
        rec = store.update(me["id"], keep)
    return {"ok": True, "status": status_payload(view), "newBadge": view["badge"]["earned"] and not before,
            "levelUp": view["mascot"] > stage_before}


def status_payload(view: dict) -> dict:
    return {k: view[k] for k in ("skill", "skillEnabled", "archived", "enrolled", "start", "cohort", "pace", "badge", "mascot", "done", "total", "requiredDone", "requiredTotal",
                                 "length", "author")}


@app.get("/{path_id}/api/status")
def api_status(path_id: str, request: Request) -> dict:
    require_path(path_id)
    me = identify(request)
    return status_payload(learner_path_view(store.get(me["id"]), path_id))


@app.put("/{path_id}/api/start")
async def api_set_start(path_id: str, request: Request) -> dict:
    require_path(path_id)
    me = identify(request)
    data = await json_body(request)
    try:
        date = dt.date.fromisoformat(str(data.get("date", ""))).isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD.")
    key = me["id"]
    if data.get("learner") and data["learner"] != me["id"]:
        require_manage(me, path_id)
        key = data["learner"]
        if not store.exists(key):
            raise HTTPException(status_code=404, detail="No such learner.")
    rec = store.update(key, lambda r: r.setdefault("start", {}).__setitem__(path_id, date))
    if key == me["id"]:
        store.update(key, lambda r: (r.__setitem__("name", me["name"]), r.__setitem__("email", me["email"])))
    return {"ok": True, "status": status_payload(learner_path_view(rec, path_id))}


@app.put("/{path_id}/api/enroll")
async def api_enroll(path_id: str, request: Request) -> dict:
    """Learners enroll themselves (optionally with a start date) and can leave ({"leave": true}). Admins can remove a
    learner from a path ({"learner": id, "remove": true}). Either way their ticks are kept and come back if they
    enroll again."""
    require_path(path_id)
    me = identify(request)
    data = await json_body(request)
    key = me["id"]
    if data.get("learner") and data["learner"] != me["id"]:
        require_manage(me, path_id)
        key = data["learner"]
        if not store.exists(key):
            raise HTTPException(status_code=404, detail="No such learner.")
    if data.get("leave"):
        rec = store.get(me["id"])
        if not is_enrolled(rec, path_id):
            raise HTTPException(status_code=400, detail="You aren't enrolled in this path.")
        rec = store.update(me["id"], lambda r: r.setdefault("enrolled", {}).__setitem__(
            path_id, {"removed": True, "left": True, "at": now_ms(), "by": me["name"]}))
        return {"ok": True, "status": status_payload(learner_path_view(rec, path_id))}
    if data.get("remove"):
        require_manage(me, path_id)
        rec = store.update(key, lambda r: r.setdefault("enrolled", {}).__setitem__(path_id, {"removed": True, "at": now_ms(), "by": me["name"]}))
        return {"ok": True, "status": status_payload(learner_path_view(rec, path_id))}
    if getattr(PATHS[path_id], "archived", False):
        raise HTTPException(status_code=409, detail="This path is archived: new enrollments are closed.")
    try:
        date = dt.date.fromisoformat(str(data.get("date") or today().isoformat())).isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD.")

    def enroll(r):
        if key == me["id"]:
            r["name"], r["email"] = me["name"], me["email"]
        r.setdefault("enrolled", {})[path_id] = {"at": now_ms(), "date": date}
        r.setdefault("start", {})[path_id] = date
    rec = store.update(key, enroll)
    return {"ok": True, "status": status_payload(learner_path_view(rec, path_id))}


# ------------------------------------------------------------------ certificates

CERT_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_cert_id() -> str:
    """DR-XXXX-XXXX, never reused (checked against every issued certificate)."""
    taken = {b.get("certId") for rec in store.all().values() for b in (rec.get("badges") or {}).values() if isinstance(b, dict)}
    while True:
        cid = "DR-" + "".join(secrets.choice(CERT_CHARS) for _ in range(4)) + "-" + "".join(secrets.choice(CERT_CHARS) for _ in range(4))
        if cid not in taken:
            return cid


def path_author(pid: str) -> dict:
    """Who made the path: the creator of an app-made path, or the set author of a built-in one. The name is the one the
    app knows (DataRobot); only the photo comes from Slack (when the bot is set up). People without one get initials."""
    doc = CUSTOM.get(pid)
    email = ((doc or {}).get("createdByEmail") or ((doc or {}).get("owners") or [""])[0]) if doc else BUILTIN_AUTHORS.get(pid, "")
    email = (email or "").lower()
    if not email:
        return {"email": "", "name": "", "photo": "", "initials": ""}
    name = ((doc or {}).get("createdBy") or (users._doc()["users"].get(email) or {}).get("name")
            or next((r.get("name") for r in store.all().values() if (r.get("email") or "").lower() == email and r.get("name")), "")
            or email.split("@")[0].replace(".", " ").title())
    initials = "".join(w[0] for w in name.split()[:2]).upper()
    return {"email": email, "name": name, "photo": slackbot.photo(email), "initials": initials}


@app.get("/{path_id}/api/certificate")
def api_certificate(path_id: str, request: Request) -> dict:
    """The learner's certificate for a finished path. The credential ID is made on first request and kept."""
    p = require_path(path_id)
    me = identify(request)
    view = learner_path_view(store.get(me["id"]), path_id)
    if not view["badge"]["earned"]:
        raise HTTPException(status_code=404, detail="Finish every required step to get your certificate.")
    issued = view["badge"].get("at") or today().isoformat()
    fresh = new_cert_id()  # made outside store.update: reading every record inside it would deadlock

    def ensure(r):
        b = r.setdefault("badges", {}).setdefault(path_id, {"at": issued})
        if not b.get("certId"):
            b["certId"] = fresh
            b["certName"] = me["name"]
            b["certAt"] = now_ms()
        return b
    badge = store.update(me["id"], ensure)["badges"][path_id]
    d = dt.date.fromisoformat(badge.get("at") or issued)
    li = {"startTask": "CERTIFICATION_NAME", "name": p.title, "issueYear": d.year, "issueMonth": d.month, "certId": badge["certId"]}
    li.update({"organizationId": LINKEDIN_ORG_ID} if LINKEDIN_ORG_ID else {"organizationName": "DataRobot"})
    return {"name": badge.get("certName") or me["name"], "course": p.title, "issued": d.isoformat(), "certId": badge["certId"],
            "linkedinUrl": "https://www.linkedin.com/profile/add?" + urlencode(li)}


VERIFY_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Credential check · DataRobot</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow:wght@400&family=DM+Mono:wght@400&display=swap">
<style>
:root{--bg:#fff;--ink:#0B0B0B;--muted:#4C5650;--line:#E4E4E4;--green:#81FBA5;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#0B0B0B;--ink:#EDF1EE;--muted:#A2ACA5;--line:#2A2F2C;color-scheme:dark}}
body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.45 Barlow,system-ui,sans-serif}
main{max-width:720px;margin:0 auto;padding:56px 20px;display:grid;gap:22px}
.k{font:12px/1.4 "DM Mono",ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
h1{font-weight:400;font-size:44px;line-height:1.05;margin:0;letter-spacing:-.015em}
.ok{display:inline-block;background:var(--green);color:#0B0B0B;border-radius:999px;padding:4px 12px;font:12px/1.4 "DM Mono",monospace;letter-spacing:.08em;text-transform:uppercase}
dl{display:grid;grid-template-columns:max-content 1fr;gap:10px 28px;margin:0;border-top:1px solid var(--line);padding-top:20px}
dt{font:12px/1.9 "DM Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}dd{margin:0}
</style></head><body><main>__BODY__</main></body></html>"""


@app.get("/verify/{cert_id}", response_class=HTMLResponse)
def verify_certificate(cert_id: str) -> HTMLResponse:
    """Anyone who can open the app can check a credential ID."""
    import html as H
    cid = cert_id.strip().upper()
    for rec in store.all().values():
        for pid, b in (rec.get("badges") or {}).items():
            if isinstance(b, dict) and b.get("certId") == cid:
                title = PATHS[pid].title if pid in PATHS else (((CUSTOM.get(pid) or {}).get("live") or {}).get("title") or pid)
                when = dt.date.fromisoformat(b["at"]).strftime("%B %-d, %Y") if b.get("at") else ""
                rows = [("Name", b.get("certName") or rec.get("name") or ""), ("Learning path", title), ("Issued", when), ("Credential ID", cid)]
                body = ('<span class="k">DataRobot · Certificate of completion</span><h1>' + H.escape(rows[0][1]) + '</h1><span class="ok">Valid</span><dl>'
                        + "".join(f"<dt>{k}</dt><dd>{H.escape(v)}</dd>" for k, v in rows[1:] if v) + "</dl>")
                return HTMLResponse(VERIFY_PAGE.replace("__BODY__", body), headers=NO_CACHE)
    body = f'<span class="k">DataRobot · Certificate of completion</span><h1>No certificate with this ID</h1><p>Check the credential ID: {H.escape(cid)}</p>'
    return HTMLResponse(VERIFY_PAGE.replace("__BODY__", body), status_code=404, headers=NO_CACHE)


@app.post("/{path_id}/api/reports")
async def api_report(path_id: str, request: Request) -> dict:
    p = require_path(path_id)
    me = identify(request)
    data = await json_body(request, 20_000)
    message = str(data.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Write a short description of the problem.")
    recent = [r for r in docs.get("reports", []) if r.get("learnerId") == me["id"] and r["createdAt"] > now_ms() - 86_400_000]
    if len(recent) >= 30:
        raise HTTPException(status_code=429, detail="You've sent a lot of reports today. Please try again tomorrow.")
    item_id = str(data.get("itemId") or "")[:120]
    kind = "bug" if data.get("kind") == "bug" else "path"
    report = {
        "id": secrets.token_hex(6), "kind": kind,
        "path": path_id, "pathTitle": p.title,
        "itemId": item_id,
        "itemLabel": (p.label_of(item_id) if item_id and item_id in p.ids else str(data.get("itemLabel") or ""))[:200],
        "anchor": re.sub(r"[^A-Za-z0-9_.-]", "", str(data.get("anchor") or ""))[:80],
        "message": message[:4000],
        "learnerId": me["id"], "name": me["name"], "email": me["email"],
        "createdAt": now_ms(), "status": "open",
    }
    out = {"ok": True}
    if kind == "bug":
        files = take_uploads(me, data.get("uploads") or [])
        report["links"] = [str(x).strip()[:500] for x in data.get("links") or [] if re.match(r"^https?://", str(x).strip())][:10]
        report["browser"] = str(data.get("browser") or request.headers.get("user-agent") or "")[:300]
        report["stepText"] = str(data.get("stepText") or "")[:1500]
        report["when"] = dt.datetime.now(TZ).strftime("%Y-%m-%d %H:%M %Z")
        report["files"] = [{"name": f["name"], "size": f["size"], "type": f["type"]} for f in files]
        if jira_ready():
            try:
                report["jira"] = send_bug_to_jira(report, files)
                out["jira"] = {k: report["jira"][k] for k in ("key", "url", "project", "summary", "attached")}
            except (AtlassianError, LLMError) as e:
                log.warning("Couldn't create the Jira issue: %s", e)
                report["jira"] = {"error": str(e)[:300]}
                report["files"] = keep_files(report["id"], files)
                out["jiraError"] = "We couldn't create the Jira issue, so your report went to the onboarding admins instead."
        else:
            report["jira"] = {"error": "Jira isn't connected to the app yet."}
            report["files"] = keep_files(report["id"], files)
            out["jiraError"] = "Jira isn't connected to the app yet, so your report went to the onboarding admins."
    docs.mutate("reports", [], lambda reports: reports.append(report))
    slack.report(report)
    return out


@app.get("/{path_id}/api/team")
def api_team(path_id: str, request: Request) -> JSONResponse:
    require_path(path_id)
    require_manage(identify(request), path_id)
    learners = []
    for k, rec in store.all().items():
        view = learner_path_view(rec, path_id)
        if not view["enrolled"]:
            continue
        learners.append({"id": k, "name": rec.get("name") or rec.get("email") or "", "email": rec.get("email") or "",
                         "state": path_state(rec, path_id) or {}, "meta": {**status_payload(view), "inactiveDays": view["inactiveDays"]}})
    return JSONResponse({"learners": learners, "inactiveAfterDays": INACTIVE_DAYS})


# --------------------------------------------------------------------------- weekly Slack summary

def weekly_summary() -> bool:
    inactive, completed = [], []
    week_ago = today() - dt.timedelta(days=7)
    for r in team_rows():
        for pid, v in r["paths"].items():
            if v["inactiveDays"]:
                inactive.append({"name": r["name"], "path": PATHS[pid].title, "days": v["inactiveDays"], "pace": v["pace"]["label"]})
            at = v["badge"].get("at")
            if v["badge"]["earned"] and at and dt.date.fromisoformat(at) >= week_ago:
                completed.append({"name": r["name"], "path": PATHS[pid].title})
    inactive.sort(key=lambda x: -x["days"])
    open_reports = sum(1 for r in docs.get("reports", []) if r.get("status") == "open" and (r.get("kind") or "path") != "system")
    return slack.weekly(inactive, open_reports, completed)


def weekly_loop() -> None:
    """From Monday 09:00 Europe/Dublin, post once per ISO week. A restart never double-posts: the last
    posted week is stored with the data. The first run only records the current week."""
    while True:
        try:
            if slack.enabled:
                now = dt.datetime.now(TZ)
                week = f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"
                meta = docs.get("meta", {}) or {}
                if not meta.get("lastWeekly"):
                    meta["lastWeekly"] = week
                    docs.put("meta", meta)
                elif meta["lastWeekly"] != week and (now.weekday() > 0 or now.hour >= 9):
                    if weekly_summary():
                        meta["lastWeekly"] = week
                        docs.put("meta", meta)
        except Exception:
            log.exception("Weekly summary failed")
        time.sleep(300)


threading.Thread(target=weekly_loop, daemon=True).start()
