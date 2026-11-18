"""Check the poster SVG, PPTX and PDF against the spec's format and text rules.

Usage: check_poster.py svg|pptx|pdf <path>   (prints problems, exits 1 if any)
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

VIEWBOX = (3178.58, 4493.86)  # A0 at 96 px/in
MIN_FONT_PX = 29
SLIDE_EMU = (30_276_000, 42_804_000)
EMU_TOL = 36_000  # 1 mm
PDF_PT = (2383.9, 3370.4)
PDF_TOL = 3.0
MAX_BYTES = 10 * 1024 * 1024
ALLOWED_SYMBOLS = {"✓", "✗", "✉"}  # ✓ ✗ ✉
BANNED = ("big lever", "heavy lifting", "k = 2 works")


def _is_emoji(ch: str) -> bool:
    o = ord(ch)
    if ch in ALLOWED_SYMBOLS:
        return False
    return 0x1F000 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF


def _texts(root):
    for el in root.iter():
        if el.tag.split("}")[-1] == "text":
            yield el, "".join(el.itertext())


def _font_px(el, inherited=None):
    v = el.attrib.get("font-size", inherited)
    return float(v) if v is not None else None


def _fit_problems(root) -> list[str]:
    from poster_lib import text_width

    probs = []
    for g in root.iter():
        b = g.attrib.get("data-pptx-bounds")
        if not b or g.attrib.get("data-pptx-replace-with"):
            continue
        bx, _by, bw, _bh = (float(v) for v in b.split())
        for el in g.iter():
            if el.tag.split("}")[-1] != "text":
                continue
            size = float(el.attrib.get("font-size", "16"))
            bold = el.attrib.get("font-weight") in ("bold", "700", "800")
            anchor = el.attrib.get("text-anchor", "start")
            # one entry per rendered line: the direct text, then each tspan with its own x
            lines = [(el.attrib.get("x", "0"), el.text or "")]
            line_x = lines[0][0]
            for ts in el:
                if "x" in ts.attrib:
                    line_x = ts.attrib["x"]
                    lines.append((line_x, "".join(ts.itertext())))
                else:
                    lines[-1] = (lines[-1][0], lines[-1][1] + "".join(ts.itertext()))
                lines[-1] = (lines[-1][0], lines[-1][1] + (ts.tail or ""))
            for xs, s in lines:
                if not s.strip():
                    continue
                w = text_width(s, size, bold)
                x = float(xs)
                x0 = (
                    x - w if anchor == "end" else x - w / 2 if anchor == "middle" else x
                )
                if x0 < bx - 2 or x0 + w > bx + bw + 2:
                    probs.append(
                        f"text overflow in group {g.attrib.get('id')}: {s[:50]!r}"
                    )
    return probs


def check_svg(path) -> list[str]:
    probs: list[str] = []
    root = ET.parse(path).getroot()
    vb = [float(v) for v in root.attrib.get("viewBox", "0 0 0 0").split()]
    if vb[:2] != [0, 0] or abs(vb[2] - VIEWBOX[0]) > 1 or abs(vb[3] - VIEWBOX[1]) > 1:
        probs.append(f"viewBox is {vb}, expected 0 0 {VIEWBOX[0]} {VIEWBOX[1]}")
    for el, s in _texts(root):
        if not s.strip():
            continue
        sizes = [_font_px(el)] + [
            _font_px(t) for t in el.iter() if t is not el and "font-size" in t.attrib
        ]
        sizes = [x for x in sizes if x is not None]
        if sizes and min(sizes) < MIN_FONT_PX:
            probs.append(f"text below {MIN_FONT_PX} px ({min(sizes)}): {s[:50]!r}")
        if ";" in s:
            probs.append(f"semicolon ; in text: {s[:60]!r}")
        if "—" in s:
            probs.append(f"em dash in text: {s[:60]!r}")
        if any(_is_emoji(c) for c in s):
            probs.append(f"emoji in text: {s[:60]!r}")
        low = s.lower()
        for b in BANNED:
            if b in low:
                probs.append(f"banned phrase {b!r}: {s[:60]!r}")
    probs += _fit_problems(root)
    return probs


def check_pptx(path) -> list[str]:
    from pptx import Presentation

    probs: list[str] = []
    path = Path(path)
    prs = Presentation(path)
    w, h = prs.slide_width, prs.slide_height
    if abs(w - SLIDE_EMU[0]) > EMU_TOL or abs(h - SLIDE_EMU[1]) > EMU_TOL:
        probs.append(f"slide size {w}x{h} EMU, expected {SLIDE_EMU[0]}x{SLIDE_EMU[1]}")
    if len(prs.slides) != 1:
        probs.append(f"{len(prs.slides)} slides, expected 1")
    with zipfile.ZipFile(path) as z:
        fonts = [n for n in z.namelist() if n.startswith("ppt/fonts/")]
    if not any("poppins" in n.lower() for n in fonts):
        probs.append(f"Poppins not embedded (ppt/fonts: {fonts})")
    if path.stat().st_size > MAX_BYTES:
        probs.append(f"file is {path.stat().st_size / 1e6:.1f} MB, over 10 MB")
    return probs


def check_pdf(path) -> list[str]:
    import pymupdf

    probs: list[str] = []
    path = Path(path)
    doc = pymupdf.open(path)
    if doc.page_count != 1:
        probs.append(f"{doc.page_count} pages, expected 1")
    r = doc[0].rect
    if abs(r.width - PDF_PT[0]) > PDF_TOL or abs(r.height - PDF_PT[1]) > PDF_TOL:
        probs.append(f"page {r.width:.1f}x{r.height:.1f} pt, expected {PDF_PT}")
    names = [f[3] for f in doc[0].get_fonts()]
    if not any(re.search("poppins", n, re.I) for n in names):
        probs.append(f"Poppins not embedded in PDF (fonts: {names})")
    if path.stat().st_size > MAX_BYTES:
        probs.append(f"file is {path.stat().st_size / 1e6:.1f} MB, over 10 MB")
    return probs


if __name__ == "__main__":
    kind, p = sys.argv[1], sys.argv[2]
    fn = {"svg": check_svg, "pptx": check_pptx, "pdf": check_pdf}[kind]
    problems = fn(p)
    for m in problems:
        print(m)
    sys.exit(1 if problems else 0)
