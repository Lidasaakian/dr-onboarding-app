#!/usr/bin/env python3
"""Rebuild the hub, admin, AI Engineer and app-made path pages in static/ from tools/src/.

Both pages share the brand stylesheet of the Agentic path (the first <style> block in
static/agentic/index.html), so the three pages always look the same. Run after editing
anything in tools/src/.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
agentic = (ROOT / "static" / "agentic" / "index.html").read_text(encoding="utf-8")
brand = re.search(r"<style>.*?</style>", agentic, re.S).group(0)

for src, dst in [("hub.html", "static/index.html"), ("ai-engineer.html", "static/ai-engineer/index.html"), ("admin.html", "static/admin.html"),
                 ("path.html", "static/path/index.html")]:
    html = (ROOT / "tools" / "src" / src).read_text(encoding="utf-8").replace("<!--BRAND_CSS-->", brand)
    out = ROOT / dst
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print("wrote", dst)
