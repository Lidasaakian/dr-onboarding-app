#!/usr/bin/env python3
"""Extract the 10 anniversary mascots from the "Anniversary T-Shirt Designs" deck into static/assets/mascots/.

Usage: python3 tools/extract_mascots.py "Anniversary T-Shirt Designs 2023.pptx"
Finds the slide titled "DATAROBOT ANNIVERSARY MASCOTS", orders its pictures in two rows (Year 1-5, Year 6-10),
trims transparent edges and saves year-01.png ... year-10.png (max 480 px). Needs: pip install pillow
"""
import io
import re
import sys
import zipfile
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent.parent / "static" / "assets" / "mascots"


def main(pptx: str) -> None:
    z = zipfile.ZipFile(pptx)
    slides = [n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)]
    slide = next(n for n in slides if "ANNIVERSARY MASCOTS" in z.read(n).decode("utf-8", "ignore"))
    rels = z.read(slide.replace("slides/", "slides/_rels/") + ".rels").decode()
    target = dict(re.findall(r'Id="([^"]+)"[^>]*Target="\.\./media/([^"]+)"', rels))
    pics = []
    for blk in re.findall(r"<p:pic>.*?</p:pic>", z.read(slide).decode(), re.S):
        rid = re.search(r'r:embed="([^"]+)"', blk).group(1)
        x, y = map(int, re.search(r'<a:off x="(\d+)" y="(\d+)"/>', blk).groups())
        pics.append((y, x, target[rid]))
    if len(pics) != 10:
        sys.exit(f"Expected 10 mascot pictures on the slide, found {len(pics)}.")
    pics.sort()
    rows = [sorted(pics[:5], key=lambda p: p[1]), sorted(pics[5:], key=lambda p: p[1])]
    OUT.mkdir(parents=True, exist_ok=True)
    for k, (_, _, media) in enumerate(rows[0] + rows[1], start=1):
        im = Image.open(io.BytesIO(z.read("ppt/media/" + media))).convert("RGBA")
        im = im.crop(im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox())
        im.thumbnail((480, 480), Image.LANCZOS)
        im.save(OUT / f"year-{k:02d}.png", optimize=True)
        print(f"year-{k:02d}.png  <- {media}  {im.size}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
