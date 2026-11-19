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
        "Panadol đỏ",
        "SoICT 2026 · Paper 1360",
    ]:
        assert s in text, s


def test_contributions_in_header():
    text = pdf_text()
    for s in [
        "Contribution 1",
        "Contribution 2",
        "Contribution 3",
        "10,000",
        "97.5%",
        "18× / 25×",
        "fewer hallucinated answers,",
    ]:
        assert s in text, s


def test_open_model_score_in_grounding_heading():
    head = " ".join(group_text("grounding-heading").split())
    assert "reaches 0.913 against Gemini's 0.923" in head, head


def test_hook_wording_is_cautious():
    text = pdf_text()
    assert "Grounded in official labelling, it follows the formulary." in text
    assert "dangerous" not in text
    assert "gets them right" not in text
    assert "judged severe harm" not in text
    assert "Contradicts the formulary" in text


def bounds(gid: str) -> tuple[float, ...]:
    root = ET.parse(SVG).getroot()
    for g in root.iter():
        if g.attrib.get("id") == gid:
            return tuple(float(v) for v in g.attrib["data-pptx-bounds"].split())
    raise AssertionError(f"no group {gid}")


def test_pipeline_is_full_width_after_hook():
    _px, py, pw, _ph = bounds("pipeline-card")
    _, hy, _, hh = bounds("hook-card")
    _, ry, _, _ = bounds("resources-card")
    assert pw > 2990, pw
    assert hy + hh < py < ry, (hy + hh, py, ry)
    tops = {round(bounds(f"pipeline-node-{i}")[1]) for i in range(7)}
    assert len(tops) == 1, tops  # one row


def test_pipeline_principle_panel():
    t = " ".join(group_text("pipeline-principle").split())
    assert "Is the evidence enough?" in t, t
    assert "Qwen3.5-9B runs every step" in t, t
    # paper: "at most three search rounds", "lets each step be ablated"
    assert "caps search at 3 rounds and lets each step be ablated" in t, t


def test_badges_follow_reading_order():
    for gid, n in [
        ("hook-heading", "1"),
        ("pipeline-heading", "2"),
        ("resources-heading", "3"),
        ("retrieval-heading", "4"),
        ("grounding-heading", "5"),
        ("steps-heading", "6"),
    ]:
        assert group_text(gid).split()[0] == n, (gid, group_text(gid)[:20])


def test_cards_inside_page():
    root = ET.parse(SVG).getroot()
    page_h = float(root.attrib["viewBox"].split()[3])
    for g in root.iter():
        gid = g.attrib.get("id", "")
        if gid.endswith("-card"):
            _, y, _, h = (float(v) for v in g.attrib["data-pptx-bounds"].split())
            assert y + h <= page_h - 90 + 0.5, (gid, round(y + h), round(page_h - 90))


def test_columns_end_level():
    _, ry, _, rh = bounds("retrieval-card")
    _, fy, _, fh = bounds("future-card")
    assert abs((ry + rh) - (fy + fh)) < 2, (round(ry + rh), round(fy + fh))


def group_lines(gid: str) -> list[str]:
    """Rendered lines of the texts in group gid (direct text and each tspan)."""
    root = ET.parse(SVG).getroot()
    for g in root.iter():
        if g.attrib.get("id") == gid:
            out = []
            for e in g.iter():
                is_text = e.tag.endswith("text") or e.tag.endswith("tspan")
                if is_text and e.text and e.text.strip():
                    out.append(e.text.strip())
            return out
    raise AssertionError(f"no group {gid}")


def test_principle_panel_has_no_orphan_word():
    lines = group_lines("pipeline-principle")
    orphans = [ln for ln in lines if len(ln.split()) < 2]
    assert not orphans, (orphans, lines)


def test_resources_and_pipeline_in_pdf():
    text = pdf_text()
    for s in [
        "24,946",
        "13,790",
        "11,031",
        "5,000",
        "2,500",
        "420 answerable",
        "Chunk 1,000",
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


def qr_decodes() -> set[str]:
    import cv2
    import numpy as np
    import pymupdf

    page = pymupdf.open(PDF)[0]
    pix = page.get_pixmap(dpi=150)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n
    )
    ok, texts, _pts, _ = cv2.QRCodeDetector().detectAndDecodeMulti(img[:, :, :3].copy())
    return {s for s in texts if s} if ok else set()


def test_future_work_and_links_in_pdf():
    text = pdf_text()
    for s in [
        "T2025-PC-019",
        "an.dv252778m@sis.hust.edu.vn",
        "tuannq@soict.hust.edu.vn",
        "linear-algebraic logic programming",  # the paper's term (conclusion)
        "to cut cost and latency",
        "a ReAct agent",
    ]:
        assert s in text, s


def test_takeaways_list_removed():
    text = pdf_text()
    assert "Takeaways" not in text
    assert "Self-hosted retrieval is enough." not in text
    assert "Real user questions" not in text


def test_future_badge_is_seven():
    assert group_text("future-heading").split()[0] == "7"


def test_no_limits_line():
    assert "Limits" not in pdf_text()


def test_qr_codes_decode():
    assert qr_decodes() == {
        "https://github.com/doanan293/ViPharmind/tree/v1.1.0",
        "https://www.kaggle.com/datasets/doanvanan0209/vipharma-rag",
    }, qr_decodes()


VI_ONLY = set("ạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹđơưĐƠƯ")


def test_vietnamese_text_uses_a_vietnamese_font():
    import pymupdf

    bad = set()
    for b in pymupdf.open(PDF)[0].get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln["spans"]:
                if set(sp["text"].lower()) & VI_ONLY and "Montserrat" not in sp["font"]:
                    bad.add((sp["font"], sp["text"][:30]))
    assert not bad, sorted(bad)[:8]


def test_review_wording_fixes():
    text = pdf_text()
    assert "redirect rate, no reranker" in text
    assert "Guard: redirect rate" not in text  # the legend note stays short
    assert "nếu có chỉ định của bác sĩ" in text
    assert "if prescribed by a doctor" in text


def test_pptx_embeds_only_poster_fonts():
    import zipfile

    with zipfile.ZipFile(PPTX) as z:
        fonts = [n for n in z.namelist() if n.startswith("ppt/fonts/")]
    extra = [
        f
        for f in fonts
        if not any(k in f for k in ("Poppins", "IBMPlexMono", "Montserrat"))
    ]
    assert not extra, extra
    assert any("Montserrat" in f for f in fonts), fonts  # Vietnamese lines


def test_pptx_text_boxes_fit_their_text():
    import sys

    sys.path.insert(0, str(HERE))
    from fix_pptx_boxes import box_problems

    probs = box_problems(PPTX)
    assert not probs, probs[:5]


def test_leaflet_card_is_not_a_model_answer():
    t = group_text("hook-leaflet")
    assert "Yumangel leaflet" in t
    assert "Qwen" not in t and "Gemini" not in t, t


def _last_leg(gid: str) -> float:
    """Length of the final vertical leg of the bent path in group gid."""
    root = ET.parse(SVG).getroot()
    for g in root.iter():
        if g.attrib.get("id") == gid:
            for e in g.iter():
                d = e.attrib.get("d", "")
                if e.tag.endswith("path") and "H" in d:
                    vs = [float(v) for v in re.findall(r"V\s*(-?[\d.]+)", d)]
                    return abs(vs[-1] - vs[-2])
    raise AssertionError(f"no bent path in {gid}")


def test_bent_arrows_leave_room_for_the_head():
    # arrowhead is 7 x stroke 5 = 35 px; the last leg must show line above it
    for gid in ("pipeline-loop",):  # one-row diagram: only the loop is bent
        assert _last_leg(gid) >= 50, (gid, _last_leg(gid))


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for f in fns:
        f()
    print(f"{len(fns)} tests passed")
    sys.exit(0)
