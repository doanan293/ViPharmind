"""Make an A0-portrait, one-slide copy of the deck template for the poster.

Keeps the deck theme and its embedded fonts; the single slide uses the BLANK
layout, so no template decoration lands on the poster.
Run: /usr/bin/python3 docs/poster/build/make_template.py
"""

from pathlib import Path

from pptx import Presentation

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[1] / "presentation" / "template.pptx"
OUT = HERE / "template-a0.pptx"
A0_EMU = (30_276_000, 42_804_000)  # 841 x 1189 mm


def main() -> None:
    prs = Presentation(SRC)
    sld_ids = prs.slides._sldIdLst
    for sld_id in list(sld_ids):
        prs.part.drop_rel(sld_id.rId)
        sld_ids.remove(sld_id)
    prs.slide_width, prs.slide_height = A0_EMU
    blank = next(
        lay for lay in prs.slide_masters[0].slide_layouts if lay.name == "BLANK"
    )
    prs.slides.add_slide(blank)
    prs.save(OUT)
    print("template:", OUT)


if __name__ == "__main__":
    main()
