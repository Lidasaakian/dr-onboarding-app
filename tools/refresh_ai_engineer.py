#!/usr/bin/env python3
"""Rebuild static/ai-engineer/content.json from the Google Sheet (alternative to uploading it in the app).

Usage:
    1. In Google Sheets: File -> Download -> Microsoft Excel (.xlsx).
    2. python3 tools/refresh_ai_engineer.py "path/to/AI Engineer Learning Plan.xlsx"
    3. Check the printed summary, then redeploy the app.

Admins can do the same without a redeploy: hub page -> Content -> AI Engineer Learning Plan -> Upload.
Needs: pip install openpyxl
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ai_engineer_content import build  # noqa: E402

OUT = ROOT / "static" / "ai-engineer" / "content.json"

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    previous = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else None
    content, diff = build(sys.argv[1], previous)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}: {diff['weeks']} weeks, {diff['rows']} plan rows, "
          f"{diff['options']} capstone options, {diff['certs']} certifications.")
    print(f"{len(diff['added'])} new row(s), {len(diff['removed'])} removed row(s).")
    for r in diff["removed"]:
        print("  removed:", r["label"])
