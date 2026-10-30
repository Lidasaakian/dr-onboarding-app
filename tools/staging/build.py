"""Assemble the staging page: the app's real pages + the simulated backend + the shell, in one file."""
import base64, io, json, re, sys
from pathlib import Path
from PIL import Image

SEED_VERSION = "2"  # bump to reset everyone's staging data to the seed
APP = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]  # the app folder
HERE = Path(__file__).parent
S = APP / "static"

DOCS = "https://docs.datarobot.com/en/docs/"
def st(title, details="", typ="Required", gate=False, link=None, source=""):
    return {"id": "new", "title": title, "details": details, "type": typ, "gate": gate, "link": link, "source": source}

generated = {
    "title": "Agent Workforce Monitoring", "blurb": "Monitor deployed agents: what monitoring tracks, alerts and costs, and a hands-on gate.",
    "length": "", "pace": "weeks", "level": "Module", "useDays": True, "skill": {"enabled": False, "name": ""},
    "groups": [
        {"title": "What agent monitoring is", "days": [
            {"title": "The basics", "steps": [
                st("Read the design page and note the three things monitoring tracks", "Cost, latency and quality. Write one sentence on each.", link={"url": DOCS, "label": "DataRobot docs"}, source="S1, S5"),
                st("Watch the launch demo (12 min)", "Pause at the traces view and find the token count for one call.", source="S2"),
                st("Check yourself: which metric would you alert on first, and why?", "", "Stretch", source="S1")]},
            {"title": "First hands-on", "steps": [
                st("Lab 1.1: turn on monitoring for a deployed agent", "Deployments → Monitoring. Done when the tab shows data.", source="S1"),
                st("Lab 1.2: find the slowest tool call in the last 24 hours", "Use the traces filter. Note the tool name and its latency.", source="S3")]}]},
        {"title": "Alerts and costs", "days": [
            {"title": "Alerts", "steps": [
                st("Create a cost alert with a daily threshold", "Needs a 7-day baseline before it fires.", source="S2"),
                st("Create a latency alert for p95 over 8 seconds", "", source="S2"),
                st("Read the FAQ on alert noise", "", "Optional", link={"url": DOCS, "label": "DataRobot docs"}, source="S6")]},
            {"title": "Costs", "steps": [
                st("Lab 2.1: compare cost per task for two agents", "Which one costs more per completed task?", source="S4"),
                st("Check yourself: why does a cost alert need a baseline?", "", "Stretch", source="S1")]}]},
        {"title": "Show it works", "days": [
            {"title": "", "steps": [
                st("Gate: monitor one deployed agent and share a screenshot", "Post it in #agent-monitoring with one thing you'd change.", gate=True, source="S1")]}]}],
}
generate_meta = {
    "coverage": {"used": 7, "total": 9, "unused": [{"title": "PBMP-3: Quality dashboards v2", "reason": "Describes work that hasn't shipped"},
                                                   {"title": "screen.png (attached to PBMP-1)", "reason": "Duplicates the design page"}]},
    "broken": [],
    "warnings": ["1 Google Doc linked from the issues. The app can't open Google Docs: https://docs.google.com/document/d/abc/edit. Download them as PDF and upload them below.",
                 "1 page is restricted. The app's Atlassian account can't open them. Learners may not be able to either."],
}
found = json.loads((HERE / "found.json").read_text())  # a sample "What we found" result from the real app

def webp(p):
    im = Image.open(p)
    b = io.BytesIO(); im.save(b, "WEBP", quality=80, method=6)
    return "data:image/webp;base64," + base64.b64encode(b.getvalue()).decode()

src = {
    "version": SEED_VERSION,
    "pages": {
        "hub": (S / "index.html").read_text(), "admin": (S / "admin.html").read_text(), "path": (S / "path" / "index.html").read_text(),
        "aiTemplate": (S / "ai-engineer" / "index.html").read_text(), "agentic": (S / "agentic" / "index.html").read_text(),
    },
    "css": (S / "assets" / "common.css").read_text(), "js": (S / "assets" / "common.js").read_text(),
    "aiContent": json.loads((S / "ai-engineer" / "content.json").read_text()),
    "generated": generated, "generateMeta": generate_meta, "found": found,
    "mascots": [webp(S / "assets" / "mascots" / f"year-{i:02d}.png") for i in range(1, 11)],
}
blob = json.dumps(src, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\u0021--")
shell = (HERE / "shell.html").read_text()
out = shell.replace("/*BACKEND*/", (HERE / "backend.js").read_text()).replace("<!--SRC-->", f'<script id="stg-src" type="application/json">{blob}</script>')
(HERE / "dist").mkdir(exist_ok=True)
(HERE / "dist" / "onboarding-staging.html").write_text(out)
print("bytes", len(out.encode()), "version", src["version"])
