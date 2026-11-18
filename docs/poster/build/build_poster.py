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

from lib import (  # noqa: E402
    arrow_marker,
    circle,
    fmt,
    group,
    icon,
    image,
    line,
    mtext,
    path,
    rect,
    text,
)

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


GAP = 60  # gap between blocks
COLW = (CW - GAP) / 2
PAD = 60  # inner card padding


def card_block(gid: str, x: float, y: float, w: float, bottom: float) -> str:
    import poster_lib as P

    return group(gid, (x, y, w, bottom - y), [P.soft_card(x, y, w, bottom - y)])


def resources_block(x: float, y0: float, w: float) -> tuple[list[str], float]:
    import content as C
    import poster_lib as P

    R = C.RESOURCES
    ix, iw = x + PAD, w - 2 * PAD
    gs: list[str] = []
    h, y = P.block_heading(ix, y0 + PAD, iw, 2, R["heading"])
    gs.append(group("resources-heading", (ix, y0 + PAD - 10, iw, y - y0 - PAD), [h]))

    def kv(gid, label, body, y):
        a, yy = P.para(ix, y, label, P.T_BODY, iw, P.PUR, bold=True)
        b, yy = P.para(ix, yy, body, P.T_BODY, iw, P.INK)
        gs.append(group(gid, (ix, y, iw, yy - y), [a, b]))
        return yy + 24

    y = kv("resources-corpus", *R["corpus"], y)
    y = kv("resources-enrichment", *R["enrichment"], y)
    y = kv("resources-benchmark", *R["benchmark"], y)
    # stacked bar of the six benchmark groups
    total = sum(n for _, n, _ in R["groups"])
    fills = ["#BFBEF7", "#FFD3A8", "#BFE8D6", "#FFC2B8", "#FFE7A3", "#D8C2F5"]
    bar_h, bx = 90, ix
    kids = []
    for i, (name, n, lab) in enumerate(R["groups"]):
        bw_ = iw * n / total
        kids.append(rect(bx, y, bw_, bar_h, fills[i], None, 1, 0))
        if n >= 1000:
            s = f"{name} {lab}" if n > 1000 else lab
            kids.append(
                text(bx + bw_ / 2, y + 58, s, P.T_SMALL, P.INK, "bold", anchor="middle")
            )
        bx += bw_
    gs.append(group("resources-bar", (ix, y, iw, bar_h), kids))
    y += bar_h + 24
    # legend for the three 500-question groups
    leg = []
    lx = ix
    for i, (name, _n, lab) in enumerate(R["groups"][3:], start=3):
        leg.append(rect(lx, y + 4, 32, 32, fills[i], None, 1, 8))
        s = f"{name} {lab}"
        leg.append(text(lx + 44, y + 32, s, P.T_SMALL, P.INK))
        lx += 44 + P.text_width(s, P.T_SMALL) + 50
    gs.append(group("resources-legend", (ix, y, iw, 44), leg))
    y += 60
    note, y = P.para(ix, y, R["groups_note"], P.T_SMALL, iw, P.MUT, italic=True)
    gs.append(group("resources-note", (ix, y - 50, iw, 60), [note]))
    y = kv("resources-golden", *R["golden"], y + 24)
    bottom = y + PAD - 24
    return [card_block("resources-card", x, y0, w, bottom), *gs], bottom


def pipeline_block(x: float, y0: float, w: float) -> tuple[list[str], float]:
    """Pipeline as two rows of icon nodes; refine loop from Judge back to search."""
    import content as C
    import poster_lib as P

    PL = C.PIPELINE
    ix, iw = x + PAD, w - 2 * PAD
    gs: list[str] = []
    h, y = P.block_heading(ix, y0 + PAD, iw, 3, PL["heading"])
    gs.append(group("pipeline-heading", (ix, y0 + PAD - 10, iw, y - y0 - PAD), [h]))
    rows = [PL["nodes"][:3], PL["nodes"][3:]]
    r = 54
    slot = iw / 4
    row_h = 2 * r + 30 + P.T_BODY * 1.3 + 2 * P.T_SMALL * P.LH + 20
    row_gap = 100
    centers = []
    for ri, row in enumerate(rows):
        cy = y + r + ri * (row_h + row_gap)
        for ci, (name, sub, ic) in enumerate(row):
            cx = ix + slot * ci + slot / 2
            centers.append((cx, cy))
            last = ri == 1 and ci == len(row) - 1
            fill = P.PEACH if last else P.LAV
            sub_lines = (
                list(sub)
                if isinstance(sub, tuple)
                else P.wrap(sub, P.T_SMALL, slot - 20)
            )
            kids = [
                circle(cx, cy, r, fill),
                icon(ic, cx, cy, r * 1.15, P.IND),
                text(cx, cy + r + 52, name, P.T_BODY, P.IND, "bold", anchor="middle"),
                mtext(
                    cx,
                    cy + r + 52 + P.T_SMALL * 1.35,
                    sub_lines,
                    P.T_SMALL,
                    P.LH,
                    P.MUT,
                    anchor="middle",
                ),
            ]
            gs.append(
                group(
                    f"pipeline-node-{ri}-{ci}",
                    (cx - slot / 2 + 4, cy - r, slot - 8, row_h),
                    kids,
                )
            )
    label_bottom = lambda cy: cy - r + row_h - 10  # noqa: E731
    arrows = []
    for i in range(len(centers) - 1):
        (x1, y1), (x2, y2) = centers[i], centers[i + 1]
        if y1 == y2:
            arrows.append(line(x1 + r + 12, y1, x2 - r - 18, y2, P.IND, 5, marker="pa"))
        else:  # Rephrase (end of row 1) down to Hybrid search (start of row 2)
            ymid = label_bottom(y1) + row_gap / 2
            arrows.append(
                path(
                    f"M{fmt(x1)} {fmt(label_bottom(y1))} V{fmt(ymid)} H{fmt(x2)} V{fmt(y2 - r - 16)}",
                    P.IND,
                    5,
                    marker="pa",
                )
            )
    gs.append(group("pipeline-arrows", (ix, y, iw, 2 * row_h + row_gap), arrows))
    # refine loop under row 2: Judge back to Hybrid search
    (hx, hy), (jx, jy) = centers[3], centers[5]
    ylow = label_bottom(jy) + 50
    loop = [
        path(
            f"M{fmt(jx)} {fmt(label_bottom(jy))} V{fmt(ylow)} H{fmt(hx)} V{fmt(label_bottom(hy) + 14)}",
            P.PUR,
            5,
            marker="pp",
        ),
        text(
            (hx + jx) / 2,
            ylow + P.T_SMALL + 14,
            PL["loop_label"],
            P.T_SMALL,
            P.PUR,
            "bold",
            anchor="middle",
        ),
    ]
    gs.append(group("pipeline-loop", (ix, label_bottom(jy) - 10, iw, 130), loop))
    y = ylow + P.T_SMALL + 50
    for gid, s in (
        ("pipeline-exits", PL["exits"]),
        ("pipeline-settings", PL["settings"]),
    ):
        tx, yy = P.para(ix, y, s, P.T_SMALL, iw, P.MUT)
        gs.append(group(gid, (ix, y, iw, yy - y), [tx]))
        y = yy + 10
    bottom = y + PAD - 10
    return [card_block("pipeline-card", x, y0, w, bottom), *gs], bottom


PIPE_DEFS = arrow_marker("pa", "#0C0A9E") + arrow_marker("pp", "#8208D5")


def build() -> tuple[str, list[str]]:
    import poster_lib as P

    copy_images()
    gs = [group("background", (0, 0, W, H), [P.background(W, H)])]
    hg, y = header_block()
    gs += hg
    kg, y = hook_block(y + 40)
    gs += kg
    y += GAP
    rg, ry = resources_block(M, y, COLW)
    pg, py = pipeline_block(M + COLW + GAP, y, COLW)
    gs += rg + pg
    y = max(ry, py)
    return P.GRAD_DEFS + PIPE_DEFS, gs


def main() -> None:
    defs, groups = build()
    page(groups, defs)
    print("poster:", SVG_DIR / "poster.svg")


if __name__ == "__main__":
    main()
