"""Learning-path models: which steps count, what is required, pace, completion badge.

The pages tick steps in the browser; the server uses these models for everything that has to be the
same everywhere (hub cards, team views, CSV export, Slack summaries).
"""

from __future__ import annotations

import datetime as dt
import html as htmllib
import json
import re
from dataclasses import dataclass, field

INACTIVE_DAYS = 7


@dataclass
class Item:
    id: str
    unit: int            # AI Engineer: calendar week the row belongs to (Week 0 counts as week 1). Agentic: working day.
    label: str
    anchor: str          # URL fragment that opens the step's page
    path: str = "Required"
    gate: bool = False
    fast_stretch: bool = False   # AI Engineer Week 1 Days 1-4: Stretch for fast-track learners


@dataclass
class PathModel:
    id: str
    title: str
    blurb: str
    length: str
    unit_name: str       # "Week" / "Day"; "" for a self-paced path (no schedule)
    skill: str           # shown as "your <skill> skill"
    units: int           # 10 weeks / 7 days
    items: list[Item] = field(default_factory=list)
    html: str = ""
    source: dict = field(default_factory=dict)  # where the live content came from (deployed / uploaded)

    @property
    def ids(self) -> set[str]:
        return {i.id for i in self.items}

    def required(self, state: dict) -> list[Item]:
        fast = (state or {}).get("track") == "fast"
        return [i for i in self.items if i.path == "Required" and not (fast and i.fast_stretch)]

    def label_of(self, item_id: str) -> str:
        for i in self.items:
            if i.id == item_id:
                return i.label
        return item_id

    # ------------------------------------------------------------------ progress

    def summarize(self, state: dict | None) -> dict:
        state = state or {}
        done = state.get("done") or {}
        req = self.required(state)
        gates = [i for i in self.items if i.gate]
        return {
            "done": sum(1 for i in self.items if i.id in done),
            "total": len(self.items),
            "requiredDone": sum(1 for i in req if i.id in done),
            "requiredTotal": len(req),
            "gatesDone": sum(1 for i in gates if i.id in done),
            "gatesTotal": len(gates),
            "updatedAt": state.get("updatedAt"),
            "started": bool(done),
        }

    def badge(self, state: dict | None) -> dict:
        """Earned when every required step (and every gate) is ticked. Stretch and optional rows don't block it."""
        done = (state or {}).get("done") or {}
        req = self.required(state or {})
        if not req or any(i.id not in done for i in req):
            return {"earned": False}
        stamps = [done[i.id] for i in req if isinstance(done.get(i.id), (int, float)) and done[i.id] > 10**11]
        at = dt.datetime.fromtimestamp(max(stamps) / 1000, dt.timezone.utc).date().isoformat() if stamps else None
        return {"earned": True, "at": at}

    def first_open(self, state: dict | None) -> Item | None:
        done = (state or {}).get("done") or {}
        for i in self.required(state or {}):
            if i.id not in done:
                return i
        return None

    # ------------------------------------------------------------------ pace

    def current_unit(self, start: dt.date, today: dt.date) -> int:
        if self.unit_name == "Week":
            return (today - start).days // 7 + 1
        # working days, start day counts as day 1
        d, n = start, 0
        while d <= today:
            if d.weekday() < 5:
                n += 1
            d += dt.timedelta(days=1)
        return max(n, 1)

    def pace(self, state: dict | None, start: str | None, today: dt.date) -> dict:
        state = state or {}
        if self.badge(state)["earned"]:
            return {"status": "finished", "label": "Finished"}
        if not self.unit_name:  # self-paced: progress instead of a schedule
            s = self.summarize(state)
            return {"status": "self_paced", "label": f"{s['done']} of {s['total']} steps"}
        if not start:
            return {"status": "not_started", "label": "Not started"}
        s = dt.date.fromisoformat(start)
        if today < s:
            return {"status": "upcoming", "label": f"Starts {s.day} {s.strftime('%b')}"}
        cur = self.current_unit(s, today)
        nxt = self.first_open(state)
        at = nxt.unit if nxt else self.units
        diff = cur - at
        unit = self.unit_name.lower()
        where = f"{self.unit_name} {min(cur, self.units)} of {self.units}" if cur <= self.units else f"Past {unit} {self.units}"
        if diff > 0:
            return {"status": "behind", "by": diff, "current": cur, "label": f"{where} · Behind by {diff} {unit}{'s' if diff > 1 else ''}"}
        if diff < 0:
            return {"status": "ahead", "by": -diff, "current": cur, "label": f"{where} · Ahead by {-diff} {unit}{'s' if diff < -1 else ''}"}
        return {"status": "on_track", "current": cur, "label": f"{where} · On track"}


def cohort_of(start: str | None) -> str:
    if not start:
        return ""
    d = dt.date.fromisoformat(start)
    return d.strftime("%b %Y")


def inactive_days(state: dict | None, badge_earned: bool, now_ms: float) -> int:
    """Days since the last tick, for learners who started and haven't finished; 0 otherwise."""
    state = state or {}
    if badge_earned or not (state.get("done") or {}):
        return 0
    last = state.get("updatedAt")
    if not isinstance(last, (int, float)) or last <= 0:
        return 0
    days = int((now_ms - last) // 86_400_000)
    return days if days >= INACTIVE_DAYS else 0


# ---------------------------------------------------------------------- AI Engineer

AI_BLURB = ("10 weeks, about 5 hours a week: Python, LLM APIs, RAG, MCP, agents, evals, production hardening "
            "and security, with a capstone agent you build week by week.")


def ai_engineer_model(content: dict, page_template: str, source: dict) -> PathModel:
    items: list[Item] = []
    roadmap = content.get("roadmap", {}).get("weeks", {})
    for w in content.get("weeks", []):
        wk = int(w["week"])
        for it in w["items"]:
            items.append(Item(
                id=it["id"], unit=max(wk, 1), label=f"Week {wk}: {it['title']}", anchor=f"w{wk}",
                path=it["path"], gate=it["gate"],
                fast_stretch=(wk == 1 and it["path"] == "Required" and it["day"] in ("1", "2", "3", "4")),
            ))
        if str(wk) in roadmap:
            items.append(Item(id=f"cap.w{wk}", unit=max(wk, 1), label=f"Week {wk}: capstone check", anchor=f"w{wk}"))
    for w in content.get("anyWeek", []):
        for it in w["items"]:
            items.append(Item(id=it["id"], unit=1, label=f"Any week: {it['title']}", anchor="w0", path=it["path"]))
    blob = json.dumps(content, ensure_ascii=False).replace("</", "<\\/")
    page = page_template.replace("<!--CONTENT_JSON-->", f'<script id="content" type="application/json">{blob}</script>')
    return PathModel(id="ai-engineer", title="AI Engineer Learning Plan", blurb=AI_BLURB, length="10 weeks",
                     unit_name="Week", skill="AI Engineering", units=10, items=items, html=page, source=source)


# ---------------------------------------------------------------------- Agentic

AGENTIC_BLURB = ("7 working days on DataRobot Agentic AI: LLM gateway, vector databases and RAG, the Agentic Starter, "
                 "evaluation, deployment and monitoring.")
_TAG = re.compile(r"<[^>]+>")


def _text(fragment: str, limit: int = 90) -> str:
    t = re.sub(r"\s+", " ", htmllib.unescape(_TAG.sub(" ", fragment))).strip()
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


def agentic_model(page: str, source: dict) -> PathModel:
    items: list[Item] = []
    for sec in re.finditer(r'<section data-page="([^"]+)"[^>]*>(.*?)</section>', page, re.S):
        pid, body = sec.group(1), sec.group(2)
        if pid == "team":
            continue
        m = re.match(r"day(\d+)$", pid)
        day = int(m.group(1)) if m else (1 if pid == "start" else 7)
        day_label = f"Day {day}" if m else ("Day 0" if pid == "start" else "Appendix")
        for t in re.finditer(r"<([a-z0-9]+)([^>]*)\bdata-t=\"([^\"]+)\"([^>]*)>", body):
            attrs = t.group(2) + t.group(4)
            if "data-opt" in attrs:
                continue
            tid = t.group(3)
            snippet = body[t.end(): t.end() + 1200]
            if t.group(1) == "span":  # a tick inside a table row or a lab heading: use the row / heading text
                row_start = max(body.rfind("<tr", 0, t.start()), body.rfind("<div class=\"lab-head\"", 0, t.start()))
                snippet = body[row_start: t.start()] + snippet[:300] if row_start >= 0 else snippet
            items.append(Item(id=tid, unit=day, label=f"{day_label}: {_text(snippet)}", anchor=pid))
    return PathModel(id="agentic", title="Agentic AI Learning Path", blurb=AGENTIC_BLURB, length="7 days",
                     unit_name="Day", skill="agentic", units=7, items=items, html=page, source=source)


def validate_agentic_page(page: str) -> None:
    if "<section data-page=" not in page or "data-t=" not in page:
        raise ValueError("This isn't the Agentic learning-path page: it has no learning-path sections or steps. "
                         "Download the current page from this screen, edit it, and upload that file.")
    if 'me.app === "dr-onboarding"' not in page:
        raise ValueError("This page is missing the app's script, so progress wouldn't save. "
                         "Start from the page downloaded from this screen.")
