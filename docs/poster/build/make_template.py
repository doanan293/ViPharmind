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


KEEP_FONTS = ("Poppins", "IBM Plex Mono")


def drop_unused_fonts(prs) -> None:
    """Keep only the poster's embedded fonts; the deck template carries ~26 others."""
    from pptx.oxml.ns import qn

    lst = prs.part._element.find(qn("p:embeddedFontLst"))
    if lst is None:
        return
    for ef in list(lst):
        face = ef.find(qn("p:font")).get("typeface")
        if face in KEEP_FONTS:
            continue
        for child in ef:
            rid = child.get(qn("r:id"))
            if rid:
                prs.part.drop_rel(rid)
        lst.remove(ef)


VI_DIR = Path.home() / ".local" / "share" / "fonts" / "Montserrat"
VI_FACES = [  # (role, variable source, weight)
    ("regular", "Montserrat-Variable.ttf", 400),
    ("bold", "Montserrat-Variable.ttf", 700),
    ("italic", "Montserrat-Italic-Variable.ttf", 400),
]


def embed_montserrat(prs) -> None:
    """Embed static Montserrat instances (Vietnamese lines; Poppins lacks those glyphs).

    PPTX .fntdata parts here are plain TrueType, as in the deck template.
    """
    import io

    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont
    from lxml import etree
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    from pptx.opc.package import Part
    from pptx.opc.packuri import PackURI
    from pptx.oxml.ns import qn

    lst = prs.part._element.find(qn("p:embeddedFontLst"))
    ef = etree.SubElement(lst, qn("p:embeddedFont"))
    etree.SubElement(ef, qn("p:font")).set("typeface", "Montserrat")
    for role, src, w in VI_FACES:
        buf = io.BytesIO()
        instantiateVariableFont(
            TTFont(VI_DIR / src), {"wght": w}, updateFontNames=True
        ).save(buf)
        part = Part(
            PackURI(f"/ppt/fonts/Montserrat-{role}.fntdata"),
            "application/x-fontdata",
            prs.part.package,
            buf.getvalue(),
        )
        rid = prs.part.relate_to(part, RT.FONT)
        etree.SubElement(ef, qn(f"p:{role}")).set(qn("r:id"), rid)


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
    drop_unused_fonts(prs)
    embed_montserrat(prs)
    prs.save(OUT)
    print("template:", OUT)


if __name__ == "__main__":
    main()
