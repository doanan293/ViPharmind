"""Render the authored SVG pages to a vector PDF backup with headless Chromium."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

pres = Path(__file__).resolve().parents[1]
ws = pres / "projects" / "soict2026_20261104"
plan = json.loads((ws / "page_plan.json").read_text())["pages"]
svg_dir = ws / "authoring-svg-flat"
img_uri = (ws / "images").as_uri() + "/"


def inline(name):
    t = (svg_dir / name).read_text(encoding="utf-8")
    t = t[t.index("<svg") :]
    return t.replace('href="../images/', f'href="{img_uri}')


body = "".join(f'<div class="p">{inline(p["svg"])}</div>' for p in plan)
html = (
    "<html><head><style>@page{size:960px 540px;margin:0}body{margin:0}"
    ".p{width:960px;height:540px;page-break-after:always;overflow:hidden}"
    ".p svg{width:960px;height:540px;display:block}</style></head><body>"
    + body
    + "</body></html>"
)
tmp = ws / "validation" / "pdf_pages.html"
tmp.write_text(html)
out = pres / "SoICT2026_ViPharmInd_talk_backup.pdf"
with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page()
    pg.goto(tmp.as_uri())
    pg.wait_for_timeout(1500)
    pg.pdf(path=str(out), width="960px", height="540px", print_background=True)
    b.close()
print(out)
