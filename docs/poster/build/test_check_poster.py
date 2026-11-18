"""Plain-assert tests for check_poster.py. Run: /usr/bin/python3 docs/poster/build/test_check_poster.py"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from check_poster import check_pptx, check_svg
from pptx import Presentation

TMP = Path(tempfile.mkdtemp())


def svg(name, body, vb="0 0 3179 4494"):
    p = TMP / f"{name}.svg"
    p.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}">{body}</svg>',
        encoding="utf-8",
    )
    return p


def t(s, size=40):
    return f'<text x="10" y="50" font-size="{size}">{s}</text>'


def test_svg_ok():
    assert check_svg(svg("ok", t("Hello"))) == []


def test_svg_exact_a0_viewbox():
    assert check_svg(svg("a0", t("Hi"), "0 0 3178.58268 4493.85827")) == []


def test_svg_wrong_viewbox():
    assert any("viewBox" in p for p in check_svg(svg("169", t("Hi"), "0 0 960 540")))


def test_svg_small_text():
    assert any("29" in p for p in check_svg(svg("small", t("tiny", 20))))


def test_svg_text_below_22pt_is_flagged():
    assert any("below" in p for p in check_svg(svg("21pt", t("almost", 29))))


def test_svg_semicolon():
    assert any(";" in p for p in check_svg(svg("semi", t("a; b"))))


def test_svg_emoji():
    assert any("emoji" in p for p in check_svg(svg("emoji", t("💡 tip"))))


def test_svg_allowed_symbols():
    assert check_svg(svg("sym", t("✓ ✗ ✉ → ↓ ≤ ×"))) == []


def test_svg_banned_phrase():
    assert any("big lever" in p for p in check_svg(svg("ban", t("the big lever"))))


def grp(bw, s):
    return (
        f'<g id="g" data-pptx-bounds="100 0 {bw} 200">'
        f'<text x="100" y="50" font-size="40">{s}</text></g>'
    )


def test_svg_text_overflows_group():
    p = svg("over", grp(300, "A sentence far too long for a narrow box"))
    assert any("overflow" in m for m in check_svg(p))


def test_svg_text_fits_group():
    assert check_svg(svg("fit", grp(2000, "Short line"))) == []


def test_svg_multiline_text_measured_per_line():
    body = (
        '<g id="g" data-pptx-bounds="100 0 400 300">'
        '<text x="100" y="50" font-size="40">Short line one'
        '<tspan x="100" dy="50">Short line two</tspan></text></g>'
    )
    assert check_svg(svg("multi", body)) == []


def test_pptx_wrong_size():
    p = TMP / "d.pptx"
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[6])
    prs.save(p)
    assert any("slide size" in m for m in check_pptx(p))


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for f in fns:
        f()
    print(f"{len(fns)} tests passed")
