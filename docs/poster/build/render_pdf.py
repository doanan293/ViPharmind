"""Print the authored poster SVG to an A0 PDF with headless Chromium.

Poppins and IBM Plex Mono are loaded from docs/presentation/fonts with
@font-face, so Chromium embeds them in the PDF.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
POSTER = HERE.parent
WS = POSTER / "projects" / "poster_a0"
FONTS = POSTER.parent / "presentation" / "fonts"
OUT = POSTER / "SoICT2026_ViPharmInd_poster.pdf"

FACES = [
    ("Poppins", "Poppins-Regular.ttf", 400, "normal"),
    ("Poppins", "Poppins-Italic.ttf", 400, "italic"),
    ("Poppins", "Poppins-Medium.ttf", 500, "normal"),
    ("Poppins", "Poppins-SemiBold.ttf", 600, "normal"),
    ("Poppins", "Poppins-Bold.ttf", 700, "normal"),
    ("IBM Plex Mono", "IBMPlexMono-Regular.ttf", 400, "normal"),
    ("IBM Plex Mono", "IBMPlexMono-Bold.ttf", 700, "normal"),
]
# Vietnamese lines (Poppins lacks Vietnamese glyphs): Montserrat variable fonts
VI_DIR = Path.home() / ".local" / "share" / "fonts" / "Montserrat"
VI_STATIC = [
    # (variable source, weight, style, static file)
    ("Montserrat-Variable.ttf", 400, "normal", "Montserrat-Regular.ttf"),
    ("Montserrat-Variable.ttf", 700, "normal", "Montserrat-Bold.ttf"),
    ("Montserrat-Italic-Variable.ttf", 400, "italic", "Montserrat-Italic.ttf"),
]


def vi_static_fonts() -> list[tuple[str, int, str, Path]]:
    """Static Montserrat instances, so Chromium embeds a named TrueType font, not Type3."""
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont

    out = WS / "fonts"
    out.mkdir(exist_ok=True)
    faces = []
    for src, w, s, name in VI_STATIC:
        dst = out / name
        if not dst.exists():
            inst = instantiateVariableFont(
                TTFont(VI_DIR / src), {"wght": w}, updateFontNames=True
            )
            inst.save(dst)
        faces.append(("Montserrat", w, s, dst))
    return faces


def main() -> None:
    svg = (WS / "authoring-svg-flat" / "poster.svg").read_text(encoding="utf-8")
    svg = svg[svg.index("<svg") :]
    svg = svg.replace('href="../images/', f'href="{(WS / "images").as_uri()}/')
    faces = "".join(
        f"@font-face{{font-family:'{fam}';src:url('{(FONTS / f).as_uri()}');"
        f"font-weight:{w};font-style:{s}}}"
        for fam, f, w, s in FACES
    ) + "".join(
        f"@font-face{{font-family:'{fam}';src:url('{p.as_uri()}');"
        f"font-weight:{w};font-style:{s}}}"
        for fam, w, s, p in vi_static_fonts()
    )
    html = (
        f"<html><head><style>{faces}@page{{size:841mm 1189mm;margin:0}}"
        "body{margin:0}svg{width:841mm;height:1189mm;display:block}</style></head>"
        f"<body>{svg}</body></html>"
    )
    tmp = WS / "validation" / "pdf_page.html"
    tmp.write_text(html, encoding="utf-8")
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page()
        pg.goto(tmp.as_uri())
        pg.wait_for_timeout(1500)
        pg.pdf(path=str(OUT), width="841mm", height="1189mm", print_background=True)
        b.close()
    print("pdf:", OUT)


if __name__ == "__main__":
    main()
