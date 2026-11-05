"""Small helpers that emit canonical compact SVG for the round-trip workspace."""

from __future__ import annotations

import json
from xml.sax.saxutils import escape

IND = "#0C0A9E"  # template dk2 (indigo)
ORA = "#EB9109"  # template lt2 (orange)
PUR = "#8208D5"  # template accent1
LAV = "#BFBEF7"  # template accent2
LAV2 = "#E6E4FD"
INK = "#1D1D1D"
MUT = "#55557A"
SOFT = "#8A8AA8"
WHITE = "#FFFFFF"
RED = "#C8372D"
GREEN = "#14805E"
GRID = "#D9D8F2"
MONO = "IBM Plex Mono, monospace"
SANS = "Poppins, sans-serif"


def esc(s: str) -> str:
    return escape(str(s), {'"': "&quot;"})


def fmt(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def text(
    x,
    y,
    s,
    size=16,
    fill=INK,
    weight=None,
    family=None,
    anchor=None,
    italic=False,
    ls=None,
):
    a = [f'x="{fmt(x)}"', f'y="{fmt(y)}"', f'font-size="{fmt(size)}"', f'fill="{fill}"']
    if weight:
        a.append(f'font-weight="{weight}"')
    if family:
        a.append(f'font-family="{family}"')
    if anchor:
        a.append(f'text-anchor="{anchor}"')
    if italic:
        a.append('font-style="italic"')
    if ls is not None:
        a.append(f'letter-spacing="{ls}"')
    return f"<text {' '.join(a)}>{esc(s)}</text>"


def runs_text(x, y, runs, size=16, fill=INK, family=None, anchor=None, weight=None):
    """One paragraph with inline runs: runs = [(text, {fill, weight, ...}), ...]."""
    a = [f'x="{fmt(x)}"', f'y="{fmt(y)}"', f'font-size="{fmt(size)}"', f'fill="{fill}"']
    if family:
        a.append(f'font-family="{family}"')
    if anchor:
        a.append(f'text-anchor="{anchor}"')
    if weight:
        a.append(f'font-weight="{weight}"')
    inner = ""
    for _i, (s, st) in enumerate(runs):
        if not st:
            inner += esc(s)
        else:
            sa = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in st.items())
            inner += f"<tspan {sa}>{esc(s)}</tspan>"
    return f"<text {' '.join(a)}>{inner}</text>"


def mtext(
    x,
    y,
    lines,
    size=16,
    lh=1.45,
    fill=INK,
    weight=None,
    family=None,
    anchor=None,
    italic=False,
):
    """One paragraph broken into positioned lines (first line direct text)."""
    a = [f'x="{fmt(x)}"', f'y="{fmt(y)}"', f'font-size="{fmt(size)}"', f'fill="{fill}"']
    if weight:
        a.append(f'font-weight="{weight}"')
    if family:
        a.append(f'font-family="{family}"')
    if anchor:
        a.append(f'text-anchor="{anchor}"')
    if italic:
        a.append('font-style="italic"')
    first, rest = lines[0], lines[1:]
    dy = fmt(size * lh)
    inner = esc(first) + "".join(
        f'<tspan x="{fmt(x)}" dy="{dy}">{esc(ln)}</tspan>' for ln in rest
    )
    return f"<text {' '.join(a)}>{inner}</text>"


def rect(
    x, y, w, h, fill="none", stroke=None, sw=1, rx=0, opacity=None, dash=None, id=None
):
    a = [f'x="{fmt(x)}"', f'y="{fmt(y)}"', f'width="{fmt(w)}"', f'height="{fmt(h)}"']
    if rx:
        a.append(f'rx="{fmt(rx)}"')
    a.append(f'fill="{fill}"')
    if stroke:
        a.append(f'stroke="{stroke}" stroke-width="{fmt(sw)}"')
    if dash:
        a.append(f'stroke-dasharray="{dash}"')
    if opacity is not None:
        a.append(f'fill-opacity="{opacity}"')
    if id:
        a.insert(0, f'id="{id}"')
    return f"<rect {' '.join(a)}/>"


def line(x1, y1, x2, y2, stroke=INK, sw=1, dash=None, marker=None, id=None, cap=None):
    a = [
        f'x1="{fmt(x1)}"',
        f'y1="{fmt(y1)}"',
        f'x2="{fmt(x2)}"',
        f'y2="{fmt(y2)}"',
        f'stroke="{stroke}"',
        f'stroke-width="{fmt(sw)}"',
    ]
    if dash:
        a.append(f'stroke-dasharray="{dash}"')
    if marker:
        a.append(f'marker-end="url(#{marker})"')
    if cap:
        a.append(f'stroke-linecap="{cap}"')
    if id:
        a.insert(0, f'id="{id}"')
    return f"<line {' '.join(a)}/>"


def path(d, stroke=INK, sw=1, fill="none", dash=None, marker=None):
    a = [
        f'd="{d}"',
        f'fill="{fill}"',
        f'stroke="{stroke}"',
        f'stroke-width="{fmt(sw)}"',
    ]
    if dash:
        a.append(f'stroke-dasharray="{dash}"')
    if marker:
        a.append(f'marker-end="url(#{marker})"')
    return f"<path {' '.join(a)}/>"


def circle(cx, cy, r, fill=IND, stroke=None, sw=1):
    a = [f'cx="{fmt(cx)}"', f'cy="{fmt(cy)}"', f'r="{fmt(r)}"', f'fill="{fill}"']
    if stroke:
        a.append(f'stroke="{stroke}" stroke-width="{fmt(sw)}"')
    return f"<circle {' '.join(a)}/>"


def image(href, x, y, w, h, clip=None, preserve="xMidYMid slice"):
    c = f' clip-path="url(#{clip})"' if clip else ""
    return f'<image href="{href}" x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}" preserveAspectRatio="{preserve}"{c}/>'


def group(id, bounds, children, extra=""):
    b = " ".join(fmt(v) for v in bounds)
    return (
        f'<g id="{id}" data-pptx-bounds="{b}" font-family="{SANS}"{extra}>'
        + "".join(children)
        + "</g>"
    )


def arrow_marker(id, color):
    return (
        f'<marker id="{id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
        f'<polygon points="0,0 10,5 0,10" fill="{color}"/></marker>'
    )


# ---------------------------------------------------------------- page chrome


def header(tag, title, sub=None, title_size=26):
    kids = [
        text(60, 40, tag, 12, ORA, "bold", MONO, ls="1.5"),
        text(60, 76, title, title_size, IND, "bold", MONO),
    ]
    h = 64
    if sub:
        kids.append(text(60, 100, sub, 14, MUT))
        h = 86
    return group("header", (56, 24, 848, h), kids)


def footer(
    num,
    label="Doan & Nguyen · Agentic RAG for Vietnamese Pharmaceutical Documents · SoICT 2026",
):
    return group(
        "footer",
        (56, 512, 848, 20),
        [
            text(60, 526, label, 10, SOFT),
            text(900, 526, str(num), 11, IND, "bold", MONO, anchor="end"),
        ],
        ' data-pptx-role="footer"',
    )


def card(x, y, w, h, fill=WHITE, stroke=LAV, rx=10, sw=1):
    return rect(x, y, w, h, fill, stroke, sw, rx)


def chart_marker(id, payload: dict, fallback: list[str], bounds):
    meta = json.dumps(payload, ensure_ascii=False)
    meta = meta.replace("&", "&amp;").replace("<", "&lt;")
    b = " ".join(fmt(v) for v in bounds)
    return (
        f'<g id="{id}" data-pptx-bounds="{b}" font-family="{SANS}" data-pptx-replace-with="chart">'
        f'<metadata type="application/json">{meta}</metadata>'
        + "".join(fallback)
        + "</g>"
    )


def table_marker(id, payload: dict, fallback: list[str], bounds):
    meta = json.dumps(payload, ensure_ascii=False)
    meta = meta.replace("&", "&amp;").replace("<", "&lt;")
    b = " ".join(fmt(v) for v in bounds)
    return (
        f'<g id="{id}" data-pptx-bounds="{b}" font-family="{SANS}" data-pptx-replace-with="table">'
        f'<metadata type="application/json">{meta}</metadata>'
        + "".join(fallback)
        + "</g>"
    )
