"""Widen PPTX text boxes that are narrower than their text.

ppt-master sizes each no-wrap text box from a per-character estimate, which is
3–9% short for Poppins in places. PowerPoint draws the text anyway, but other
viewers (LibreOffice) recentre an overflowing box. This step measures every
line with the real fonts and widens the box, keeping its alignment anchor.

Usage: fix_pptx_boxes.py <poster.pptx>   (rewrites the file in place)
"""

from __future__ import annotations

import sys
from pathlib import Path

from pptx import Presentation
from pptx.enum.text import PP_ALIGN

sys.path.insert(0, str(Path(__file__).resolve().parent))

from poster_lib import VI_FAMILY, text_width

EMU_PER_PX = 9525
TOL = 1.01  # accept 1% measuring noise


def _walk(shapes):
    for sh in shapes:
        yield sh
        if sh.shape_type == 6:
            yield from _walk(sh.shapes)


def _needed_width(shape) -> float:
    """Widest paragraph of the shape, in EMU, measured with the run fonts."""
    from pptx.text.text import _Run

    widest = 0.0
    for p in shape.text_frame.paragraphs:
        w = 0.0
        for child in p._p:
            tag = child.tag.split("}")[-1]
            if tag == "br":  # soft line break: measure each line on its own
                widest = max(widest, w)
                w = 0.0
            elif tag == "r":
                r = _Run(child, p)
                if not r.text or r.font.size is None:
                    continue
                px = r.font.size.pt * 96 / 72
                fam = r.font.name or ""
                vi = VI_FAMILY if VI_FAMILY in fam else None
                w += text_width(r.text, px, bool(r.font.bold), vi)
        widest = max(widest, w)
    return widest * EMU_PER_PX


def _text_boxes(prs):
    for sh in _walk(prs.slides[0].shapes):
        if (
            getattr(sh, "has_text_frame", False)
            and sh.has_text_frame
            and sh.text_frame.text.strip()
        ):
            if sh.text_frame.word_wrap is True:
                continue
            yield sh


def _inner(sh) -> float:
    tf = sh.text_frame
    return sh.width - (tf.margin_left or 0) - (tf.margin_right or 0)


def box_problems(path) -> list[str]:
    prs = Presentation(path)
    out = []
    for sh in _text_boxes(prs):
        need = _needed_width(sh)
        if need > _inner(sh) * TOL:
            out.append(
                f"{sh.name}: text {need / EMU_PER_PX:.0f} px > box {_inner(sh) / EMU_PER_PX:.0f} px: {sh.text_frame.text[:40]!r}"
            )
    return out


def fix(path) -> int:
    prs = Presentation(path)
    n = 0
    for sh in _text_boxes(prs):
        need = _needed_width(sh)
        inner = _inner(sh)
        if need <= inner * TOL:
            continue
        delta = int(need * 1.02 - inner)
        align = sh.text_frame.paragraphs[0].alignment
        if align == PP_ALIGN.CENTER:
            sh.left = sh.left - delta // 2
        elif align == PP_ALIGN.RIGHT:
            sh.left = sh.left - delta
        sh.width = sh.width + delta
        n += 1
    prs.save(path)
    return n


if __name__ == "__main__":
    print("widened text boxes:", fix(sys.argv[1]))
