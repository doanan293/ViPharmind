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
