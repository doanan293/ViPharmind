"""Build the SoICT 2026 A0 poster page into the ppt-master round-trip workspace.

Every number on the poster comes from docs/report/ (see content.py).
Run with /usr/bin/python3 docs/poster/build/build_poster.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "presentation" / "build"))

from lib import group, image, mtext, text  # noqa: E402

ROOT = HERE.parent
WS = ROOT / "projects" / "poster_a0"
SVG_DIR = WS / "authoring-svg-flat"
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)
W, H = 3178.58, 4493.86


def page(groups: list[str], defs: str = "") -> None:
    """Write poster.svg from the template slide SVG plus our groups."""
    tree = ET.parse(SVG_DIR / "slide_01.svg")
    root = tree.getroot()
    for el in list(root):
        root.remove(el)
    if defs:
        frag = ET.fromstring(f'<defs xmlns="{NS}">{defs}</defs>')
        root.insert(0, frag)
    frag = ET.fromstring(f'<g xmlns="{NS}">{"".join(groups)}</g>')
    for child in list(frag):
        root.append(child)
    tree.write(SVG_DIR / "poster.svg", encoding="utf-8", xml_declaration=True)
    (WS / "page_plan.json").write_text(
        json.dumps(
            {
                "schema": "ppt-master.roundtrip-page-plan.v1",
                "pages": [{"source_slide": 1, "svg": "poster.svg"}],
            },
            indent=1,
        )
    )


M = 110  # page margin
CW = W - 2 * M  # content width
IMAGES = {
    "panadol": "panadol-extra-thumb.jpg",
    "yumangel": "yumangel-thumb.jpg",
    "phosphalugel": "phosphalugel-thumb.jpg",
    "qr-github.png": "qr-github.png",
    "qr-kaggle.png": "qr-kaggle.png",
}


def copy_images(max_px: int = 600) -> None:
    """Copy the photos and QR codes into the workspace, downscaled for print."""
    from PIL import Image

    src = HERE.parents[1] / "presentation" / "assets-src"
    out = WS / "images"
    out.mkdir(exist_ok=True)
    for name in IMAGES.values():
        im = Image.open(src / name)
        im.thumbnail((max_px, max_px))
        im.save(out / f"poster-{name}")


def img(key: str) -> str:
    return f"../images/poster-{IMAGES[key]}"


def header_block() -> tuple[list[str], float]:
    import content as C
    import poster_lib as P

    size = 128
    title = mtext(M, 70 + size, C.HEADER["title"], size, 1.12, P.IND, "bold")
    y = 70 + size + size * 1.12 + 110
    auth = [
        text(M, y, C.HEADER["authors"], P.T_AUTH, P.INK, "bold"),
        text(M, y + 66, C.HEADER["affiliation"], P.T_BODY, P.MUT),
        text(M, y + 124, C.HEADER["venue"], P.T_BODY, P.PUR, "bold"),
    ]
    bottom = y + 230
    gs = [
        group("title", (M - 4, 60, CW + 8, size * 2.3 + 20), [title]),
        group("authors", (M - 4, y - 60, 2200, 200), auth),
        group(
            "mascot",
            (W - M - 470, y - 70, 470, 330),
            [P.mascot(W - M - 450, y - 70, 430)],
        ),
    ]
    return gs, bottom


def hook_block(y0: float) -> tuple[list[str], float]:
    import content as C
    import poster_lib as P

    H_ = C.HOOK
    x0, pad = M, 70
    inner = CW - 2 * pad
    gs: list[str] = []
    head, y = P.block_heading(x0 + pad, y0 + pad, inner, 1, H_["heading"])
    gs_head = group(
        "hook-heading", (x0 + pad, y0 + pad - 10, inner, y - y0 - pad), [head]
    )

    # left column: metformin before / after
    lw = inner * 0.53
    lx = x0 + pad
    b, ly = P.bubble(lx, y, lw * 0.92, H_["question_en"], H_["question_vi"])
    gs.append(group("hook-question", (lx, y, lw * 0.92, ly - y), [b]))
    bad, ly2 = P.verdict_card(
        lx, ly, lw, "bad", **{k: H_["bad"][k] for k in ("label", "en", "vi", "verdict")}
    )
    gs.append(group("hook-bad", (lx, ly, lw, ly2 - ly), [bad]))
    good, ly3 = P.verdict_card(
        lx,
        ly2 + 30,
        lw,
        "good",
        **{k: H_["good"][k] for k in ("label", "en", "vi", "verdict")},
    )
    gs.append(group("hook-good", (lx, ly2 + 30, lw, ly3 - ly2 - 30), [good]))

    # right column: nickname → leaflet
    rx = lx + lw + 70
    rw = x0 + pad + inner - rx
    nh, ry = P.para(
        rx, y - 10, H_["nick_heading"], P.T_BODY * 1.15, rw, P.IND, bold=True
    )
    gs.append(group("hook-nick-heading", (rx, y - 10, rw, ry - y + 10), [nh]))
    nb, ry2 = P.bubble(
        rx,
        ry + 10,
        rw,
        H_["nick_question_en"],
        H_["nick_question_vi"],
        size=P.T_BODY * 1.1,
    )
    gs.append(group("hook-nick-question", (rx, ry + 10, rw, ry2 - ry - 10), [nb]))
    mp = text(
        rx + rw / 2,
        ry2 + 10,
        "↓  " + H_["nick_map"],
        P.T_BODY,
        P.PUR,
        "bold",
        anchor="middle",
    )
    gs.append(group("hook-map", (rx, ry2 - 40, rw, 70), [mp]))
    ly_ = ry2 + 50
    photo = 230
    tx = rx + 36 + photo + 30
    tw = rx + rw - 36 - tx
    lab, yy = P.para(tx, ly_ + 26, H_["leaflet_label"], P.T_SMALL, tw, P.PUR, bold=True)
    en, yy = P.para(tx, yy, H_["leaflet_en"], P.T_BODY, tw, P.INK)
    vi, yy = P.para(tx, yy + 2, H_["leaflet_vi"], P.T_SMALL, tw, P.MUT, italic=True)
    lh = max(yy - ly_ + 30, photo + 60)
    leaf = [
        P.soft_card(rx, ly_, rw, lh, P.WHITE, 40),
        image(
            img("yumangel"),
            rx + 36,
            ly_ + (lh - photo) / 2,
            photo,
            photo,
            preserve="xMidYMid meet",
        ),
        lab,
        en,
        vi,
    ]
    gs.append(group("hook-leaflet", (rx, ly_, rw, lh), leaf))
    my = ly_ + lh + 30
    mw = (rw - 30) / 2
    for i, (nick, gloss, prod, key) in enumerate(H_["minis"]):
        mx = rx + i * (mw + 30)
        kids = [
            P.soft_card(mx, my, mw, 170, P.WHITE, 36),
            image(img(key), mx + 20, my + 20, 130, 130, preserve="xMidYMid meet"),
            text(mx + 170, my + 60, nick, P.T_SMALL, P.INK, "bold"),
            text(mx + 170, my + 100, gloss, P.T_SMALL, P.MUT, italic=True),
            text(mx + 170, my + 142, "→ " + prod, P.T_SMALL, P.ORANGE_TXT, "bold"),
        ]
        gs.append(group(f"hook-mini-{i}", (mx, my, mw, 170), kids))
    col_bottom = max(ly3, my + 170)

    # three big numbers
    sy = col_bottom + 50
    sw = (inner - 2 * 40) / 3
    fills = [P.LAV, P.CORAL, P.MINT]
    for i, (v, lab_) in enumerate(H_["stats"]):
        sx = lx + i * (sw + 40)
        gs.append(
            group(
                f"stat-{i}",
                (sx, sy, sw, 300),
                [P.stat_card(sx, sy, sw, 300, v, lab_, fills[i])],
            )
        )
    bottom = sy + 300 + pad
    card = group(
        "hook-card", (x0, y0, CW, bottom - y0), [P.soft_card(x0, y0, CW, bottom - y0)]
    )
    return [card, gs_head, *gs], bottom


def build() -> tuple[str, list[str]]:
    import poster_lib as P

    copy_images()
    gs = [group("background", (0, 0, W, H), [P.background(W, H)])]
    hg, y = header_block()
    gs += hg
    kg, y = hook_block(y + 40)
    gs += kg
    return P.GRAD_DEFS, gs


def main() -> None:
    defs, groups = build()
    page(groups, defs)
    print("poster:", SVG_DIR / "poster.svg")


if __name__ == "__main__":
    main()
