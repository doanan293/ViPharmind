"""Tests on the built poster files. Run after make.sh:
/usr/bin/python3 docs/poster/build/test_poster_output.py
"""

import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
POSTER = HERE.parent
PDF = POSTER / "SoICT2026_ViPharmInd_poster.pdf"
PPTX = POSTER / "SoICT2026_ViPharmInd_poster.pptx"
SVG = POSTER / "projects" / "poster_a0" / "authoring-svg-flat" / "poster.svg"


def pdf_text() -> str:
    import pymupdf

    t = pymupdf.open(PDF)[0].get_text()
    return re.sub(r"\s+", " ", t)


def group_text(gid: str) -> str:
    root = ET.parse(SVG).getroot()
    for g in root.iter():
        if g.attrib.get("id") == gid:
            return " ".join(
                " ".join(e.itertext()) for e in g.iter() if e.tag.endswith("text")
            )
    raise AssertionError(f"no group {gid}")


def test_hook_strings_in_pdf():
    text = pdf_text()
    for s in [
        "Thuốc bao tử chữ Y uống trước hay sau ăn?",
        "Đang cho con bú dùng metformin có sao không?",
        "Yumangel leaflet",
        "Contradicts the formulary",
        "2,409",
        "0.913 vs 0.923",
        "Panadol đỏ",
        "SoICT 2026 · Paper 1360",
    ]:
        assert s in text, s


def test_resources_and_pipeline_in_pdf():
    text = pdf_text()
    for s in [
        "24,946",
        "13,790",
        "11,031",
        "5,000",
        "2,500",
        "420 answerable",
        "≤ 3",
        "RRF k = 2",
        "A Vietnamese drug-information corpus and benchmark, all released",
    ]:
        assert s in text, s
    head = " ".join(group_text("pipeline-heading").split())
    assert head.endswith("each model call makes one small decision"), head


def _shapes():
    from pptx import Presentation

    def walk(shapes):
        for sh in shapes:
            yield sh
            if sh.shape_type == 6:  # group
                yield from walk(sh.shapes)

    return list(walk(Presentation(PPTX).slides[0].shapes))


def native_chart_values() -> dict:
    for sh in _shapes():
        if getattr(sh, "has_chart", False) and sh.has_chart:
            return {
                s.name: [round(v, 3) for v in s.values]
                for s in sh.chart.plots[0].series
            }
    raise AssertionError("no native chart")


def native_table_cells() -> list[list[str]]:
    for sh in _shapes():
        if getattr(sh, "has_table", False) and sh.has_table:
            return [[c.text for c in row.cells] for row in sh.table.rows]
    raise AssertionError("no native table")


def test_grounding_chart_values():
    v = native_chart_values()
    assert v["Qwen3.5-9B"] == [-0.06, 0.792, 0.913], v
    assert v["Gemini 3.8 Flash"] == [0.268, 0.816, 0.923], v


def test_retrieval_table_row():
    rows = native_table_cells()
    assert ["+ Qwen3-Reranker-4B", "4.0/s", "97.5", "99.2", "0.859"] in rows, rows
    assert len(rows) == 8, rows


def test_results_text_in_pdf():
    text = pdf_text()
    for s in [
        "k = 2 gives the best Hit@10 (95.9) and Hit@30 (99.2) before reranking",
        "wrong −1",
        "Each step pays off on the questions it targets",
        "0.020",
        "10/10",
        "p = 0.056",
        "0.920 vs 0.750",
    ]:
        assert s in text, s


def test_negative_bar_hangs_below_zero_line():
    root = ET.parse(SVG).getroot()
    zero = bar = None
    for el in root.iter():
        i = el.attrib.get("id", "")
        if i == "grounding-zero":
            zero = float(el.attrib["y1"])
        if i == "grounding-bar-Qwen3.5-9B-0":
            bar = float(el.attrib["y"]), float(el.attrib["height"])
    assert zero is not None and bar is not None, (zero, bar)
    assert abs(bar[0] - zero) < 0.5 and bar[1] > 0, (zero, bar)


def test_leaflet_card_is_not_a_model_answer():
    t = group_text("hook-leaflet")
    assert "Yumangel leaflet" in t
    assert "Qwen" not in t and "Gemini" not in t, t


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for f in fns:
        f()
    print(f"{len(fns)} tests passed")
    sys.exit(0)
