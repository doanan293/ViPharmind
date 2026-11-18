"""Style A components for the poster (soft pastel, rounded cards, pill mascot).

All coordinates are poster px (A0 at 96 px/in). Functions return SVG strings;
the ones that lay out text also return the y just below what they drew.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "presentation" / "build"))

from lib import circle, fmt, mtext, path, rect, text

FONTS = Path(__file__).resolve().parents[2] / "presentation" / "fonts"

# palette (spec §4)
BG_TOP, BG_BOTTOM = "#F3EFFF", "#FFF6EC"
IND = "#0C0A9E"
PUR = "#8208D5"
INK = "#1D1D1D"
MUT = "#55557A"
WHITE = "#FFFFFF"
LAV = "#E6E4FD"
PEACH = "#FFE9CF"
MINT = "#DFF3EA"
CORAL = "#FFE3DE"
GEM = "#8F8CF0"
QWN = "#FFB27A"
WITH = "#7FD1AE"
WITHOUT = "#E3E1EE"
RED = "#C8372D"
GREEN = "#14805E"
CHEEK = "#FFB4A8"
ORANGE_TXT = "#B05F00"

# type sizes in px (spec §4; pt = px × 0.75)
T_TITLE, T_AUTH, T_BIG, T_HEAD, T_BODY, T_SMALL = 133, 50, 68, 54, 37, 30
LH = 1.32
# ppt-master's quality gate estimates text wider than Poppins really is; wrap with headroom
WRAP_SAFETY = 1.12

GRAD_DEFS = (
    f'<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
    f'<stop offset="0" stop-color="{BG_TOP}"/><stop offset="1" stop-color="{BG_BOTTOM}"/>'
    "</linearGradient>"
    '<filter id="soft"><feDropShadow dx="0" dy="10" stdDeviation="18" '
    f'flood-color="{IND}" flood-opacity="0.08"/></filter>'
)


@lru_cache(maxsize=64)
def _font(size: float, bold: bool):
    from PIL import ImageFont

    name = "Poppins-Bold.ttf" if bold else "Poppins-Regular.ttf"
    return ImageFont.truetype(str(FONTS / name), max(1, round(size * 4)))


def text_width(s: str, size: float, bold: bool = False) -> float:
    """Rendered width of s in Poppins at size px (measured at 4x for precision)."""
    return _font(size, bold).getlength(s) / 4


def wrap(s: str, size: float, width: float, bold: bool = False) -> list[str]:
    """Greedy word wrap so every line fits width in Poppins."""
    lines: list[str] = []
    cur = ""
    for word in s.split():
        cand = f"{cur} {word}".strip()
        if cur and text_width(cand, size, bold) * WRAP_SAFETY > width:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def para(x, y, s, size, width, fill=INK, bold=False, italic=False, lh=LH):
    """Wrapped paragraph whose first baseline is y + size; returns (svg, bottom y)."""
    lines = wrap(s, size, width, bold)
    svg = mtext(
        x, y + size, lines, size, lh, fill, "bold" if bold else None, italic=italic
    )
    return svg, y + size + size * lh * (len(lines) - 1) + size * 0.35


def background(w: float, h: float) -> str:
    return f'<rect x="0" y="0" width="{fmt(w)}" height="{fmt(h)}" fill="url(#bg)"/>'


def soft_card(x, y, w, h, fill=WHITE, r=48, shadow=True) -> str:
    f = ' filter="url(#soft)"' if shadow else ""
    return rect(x, y, w, h, fill, None, 1, r).replace("/>", f"{f}/>")


def badge(cx, cy, n: int, r=40) -> str:
    return circle(cx, cy, r, PUR) + text(
        cx, cy + r * 0.38, str(n), r * 1.05, WHITE, "bold", anchor="middle"
    )


def block_heading(x, y, w, n: int, s: str) -> tuple[str, float]:
    r = 40
    svg = badge(x + r, y + r, n, r)
    t, bottom = para(x + 2 * r + 28, y - 4, s, T_HEAD, w - 2 * r - 28, IND, bold=True)
    return svg + t, max(bottom, y + 2 * r) + 24


def bubble(x, y, w, en: str, vi: str, fill=LAV, size=T_BIG * 0.7) -> tuple[str, float]:
    """Chat bubble: bold English question, small Vietnamese original under it."""
    pad = 40
    t1, y1 = para(x + pad, y + pad - 10, en, size, w - 2 * pad, INK, bold=True)
    t2, y2 = para(x + pad, y1 + 4, vi, T_SMALL, w - 2 * pad, MUT, italic=True)
    h = y2 - y + pad - 6
    tail = path(f"M{fmt(x + 40)} {fmt(y + h - 2)} l-24 40 l70 -40 z", "none", 0, fill)
    return rect(x, y, w, h, fill, None, 1, 44) + tail + t1 + t2, y + h + 40


def verdict_card(
    x, y, w, kind: str, label: str, en: str, vi: str, verdict: str
) -> tuple[str, float]:
    fill, stroke, col = (
        (CORAL, "#E8796B", RED) if kind == "bad" else (MINT, "#55B58C", GREEN)
    )
    pad = 36
    parts = []
    t0, yy = para(x + pad, y + pad - 12, label, T_BODY, w - 2 * pad, col, bold=True)
    t1, yy = para(x + pad, yy, en, T_BODY, w - 2 * pad, INK)
    t2, yy = para(x + pad, yy + 2, vi, T_SMALL, w - 2 * pad, MUT, italic=True)
    t3, yy = para(x + pad, yy + 6, verdict, T_BODY * 0.9, w - 2 * pad, col, bold=True)
    h = yy - y + pad - 10
    parts.append(rect(x, y, w, h, fill, stroke, 4, 36))
    parts += [t0, t1, t2, t3]
    return "".join(parts), y + h


def stat_card(x, y, w, h, value: str, label: str, fill) -> str:
    lines = wrap(label, T_BODY * 0.9, w - 60)
    vy = y + h * 0.42 - (len(lines) - 1) * 22
    v = text(x + w / 2, vy, value, T_BIG * 1.15, IND, "bold", anchor="middle")
    lab = mtext(x + w / 2, vy + 75, lines, T_BODY * 0.9, LH, MUT, anchor="middle")
    return rect(x, y, w, h, fill, None, 1, 40) + v + lab


def mascot(x, y, w) -> str:
    """Pill mascot: white and lavender capsule, indigo outline, face, pink cheeks.

    Drawn in a 120 x 80 box, tilted, scaled to width w at (x, y).
    """
    s = w / 120
    body = (
        '<rect x="8" y="18" width="104" height="48" rx="24" fill="#FFFFFF" '
        f'stroke="{IND}" stroke-width="3"/>'
        f'<path d="M60 18 h28 a24 24 0 0 1 0 48 h-28 z" fill="#BFBEF7" stroke="{IND}" stroke-width="3"/>'
        f'<circle cx="44" cy="38" r="3.5" fill="{INK}"/><circle cx="70" cy="38" r="3.5" fill="{INK}"/>'
        f'<path d="M50 47 q7 7 14 0" stroke="{INK}" stroke-width="2.5" fill="none" stroke-linecap="round"/>'
        f'<ellipse cx="37" cy="47" rx="5" ry="3" fill="{CHEEK}"/><ellipse cx="78" cy="47" rx="5" ry="3" fill="{CHEEK}"/>'
    )
    return (
        f'<g transform="translate({fmt(x)} {fmt(y)}) scale({s:.4f}) rotate(-18 60 40)">'
        + body
        + "</g>"
    )
