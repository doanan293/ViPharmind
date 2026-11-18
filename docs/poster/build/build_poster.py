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
    chart_marker,
    circle,
    fmt,
    group,
    icon,
    image,
    line,
    mtext,
    path,
    rect,
    runs_text,
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


M = 90  # page margin
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
    """Title, authors on the left, the three big numbers on the right."""
    import content as C
    import poster_lib as P

    size = 128
    title = mtext(M, 60 + size, C.HEADER["title"], size, 1.1, P.IND, "bold")
    y = 60 + size + size * 1.1 + 88
    auth = [
        text(M, y, C.HEADER["authors"], P.T_AUTH, P.INK, "bold"),
        mtext(M, y + 58, C.HEADER["affiliation"], P.T_BODY, 1.25, P.MUT),
        text(
            M, y + 58 + P.T_BODY * 1.25 * 2, C.HEADER["venue"], P.T_BODY, P.PUR, "bold"
        ),
    ]
    gs = [
        group("title", (M - 4, 40, CW + 8, size * 2.6), [title]),
        group("authors", (M - 4, y - 55, 1080, 240), auth),
    ]
    sx0 = M + 1080
    mascot_w = 300
    sw = (W - M - mascot_w - 20 - sx0 - 2 * 30) / 3
    sy, sh = y - 70, 225
    fills = [P.LAV, P.CORAL, P.MINT]
    for i, (v, lab) in enumerate(C.HOOK["stats"]):
        sx = sx0 + i * (sw + 30)
        gs.append(
            group(
                f"stat-{i}",
                (sx, sy, sw, sh),
                [P.stat_card(sx, sy, sw, sh, v, lab, fills[i])],
            )
        )
    mx = W - M - mascot_w
    gs.append(
        group("mascot", (mx, sy + 10, mascot_w, 210), [P.mascot(mx, sy + 10, mascot_w)])
    )
    return gs, sy + sh


def hook_block(y0: float) -> tuple[list[str], float]:
    import content as C
    import poster_lib as P

    H_ = C.HOOK
    x0, pad = M, 48
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
    vi, yy = P.para(
        tx,
        yy + 2,
        H_["leaflet_vi"],
        P.T_SMALL,
        tw,
        P.MUT,
        italic=True,
        family=P.VI_FAMILY,
    )
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
            text(mx + 170, my + 60, nick, P.T_SMALL, P.INK, "bold", P.VI_FAMILY),
            text(mx + 170, my + 100, gloss, P.T_SMALL, P.MUT, italic=True),
            text(mx + 170, my + 142, "→ " + prod, P.T_SMALL, P.ORANGE_TXT, "bold"),
        ]
        gs.append(group(f"hook-mini-{i}", (mx, my, mw, 170), kids))
    col_bottom = max(ly3, my + 170)

    bottom = col_bottom + pad
    card = group(
        "hook-card", (x0, y0, CW, bottom - y0), [P.soft_card(x0, y0, CW, bottom - y0)]
    )
    return [card, gs_head, *gs], bottom


GAP = 40  # gap between blocks
COLW = (CW - GAP) / 2
PAD = 50  # inner card padding


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
        if n > 1000:
            s = f"{name} {lab}"
            kids.append(
                text(bx + bw_ / 2, y + 58, s, P.T_SMALL, P.INK, "bold", anchor="middle")
            )
        bx += bw_
    gs.append(group("resources-bar", (ix, y, iw, bar_h), kids))
    y += bar_h + 24
    # legend for the groups too narrow to label inside the bar
    leg = []
    lx = ix
    for i, (name, _n, lab) in enumerate(R["groups"][2:], start=2):
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
    r = 48
    slot = iw / 4
    row_h = 2 * r + 30 + P.T_BODY * 1.3 + 2 * P.T_SMALL * P.LH + 20
    row_gap = 90
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
            ymid = label_bottom(y1) + 22
            arrows.append(
                path(
                    f"M{fmt(x1)} {fmt(label_bottom(y1))} V{fmt(ymid)} H{fmt(x2)} V{fmt(y2 - r - 8)}",
                    P.IND,
                    5,
                    marker="pa",
                )
            )
    gs.append(group("pipeline-arrows", (ix, y, iw, 2 * row_h + row_gap), arrows))
    # refine loop under row 2: Judge back to Hybrid search
    (hx, hy), (jx, jy) = centers[3], centers[5]
    ylow = label_bottom(jy) + 64
    loop = [
        path(
            f"M{fmt(jx)} {fmt(label_bottom(jy))} V{fmt(ylow)} H{fmt(hx)} V{fmt(label_bottom(hy) + 6)}",
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
    for gid, s in (("pipeline-exits", PL["exits"]),):
        tx, yy = P.para(ix, y, s, P.T_SMALL, iw, P.MUT)
        gs.append(group(gid, (ix, y, iw, yy - y), [tx]))
        y = yy + 10
    bottom = y + PAD - 10
    return [card_block("pipeline-card", x, y0, w, bottom), *gs], bottom


PIPE_DEFS = arrow_marker("pa", "#0C0A9E") + arrow_marker("pp", "#8208D5")


def retrieval_block(x: float, y0: float, w: float) -> tuple[list[str], float]:
    import content as C
    import poster_lib as P
    from build_deck import simple_table

    ix, iw = x + PAD, w - 2 * PAD
    gs: list[str] = []
    h, y = P.block_heading(ix, y0 + PAD, iw, 4, C.RETRIEVAL_HEADING)
    gs.append(group("retrieval-heading", (ix, y0 + PAD - 10, iw, y - y0 - PAD), [h]))
    rows = [list(r[:5]) for r in C.RETRIEVAL_ROWS]
    hl = [i for i, r in enumerate(C.RETRIEVAL_ROWS) if r[5]]
    first = iw - 4 * 205
    colw = [first, 205, 205, 205, 205]
    rowh = 56
    best = {(i, j) for i in hl for j in range(5)}
    gs.append(
        simple_table(
            "retrieval-table",
            ix,
            y,
            colw,
            rowh,
            C.RETRIEVAL_COLUMNS,
            rows,
            font=P.T_BODY,
            hfont=P.T_BODY,
            best=best,
            fills=dict.fromkeys(hl, P.PEACH),
        )
    )
    y += rowh * (len(rows) + 1) + 16
    note, y = P.para(ix, y, C.RETRIEVAL_NOTE, P.T_SMALL, iw, P.MUT, italic=True)
    gs.append(group("retrieval-note", (ix, y - 60, iw, 60), [note]))
    for i, s in enumerate(C.RETRIEVAL_LESSONS):
        tip, yy = P.para(ix + 30, y + 22, s, P.T_BODY, iw - 60, P.INK)
        gs.append(
            group(
                f"retrieval-lesson-{i}",
                (ix, y + 6, iw, yy - y + 6),
                [rect(ix, y + 6, iw, yy - y + 6, P.LAV, None, 1, 28), tip],
            )
        )
        y = yy + 30
    bottom = y + PAD - 30
    return [card_block("retrieval-card", x, y0, w, bottom), *gs], bottom


def grounding_block(x: float, y0: float, w: float) -> tuple[list[str], float]:
    import content as C
    import poster_lib as P

    G = C.GROUNDING
    ix, iw = x + PAD, w - 2 * PAD
    gs: list[str] = []
    h, y = P.block_heading(ix, y0 + PAD, iw, 5, G["heading"])
    gs.append(group("grounding-heading", (ix, y0 + PAD - 10, iw, y - y0 - PAD), [h]))
    cats, series = G["categories"], G["series"]
    colors = [P.GEM, P.QWN]
    cy0 = y
    px, pw = ix + 110, iw - 130
    py, ph = cy0 + 80, 310
    vmin, vmax = -0.2, 1.0

    def Y(v):
        return py + ph - ph * (v - vmin) / (vmax - vmin)

    fb = [rect(px, py, pw, ph, P.WHITE, None, 1, 0)]
    for tk in [-0.2, 0.0, 0.2, 0.4, 0.6, 0.8, 1.0]:
        fb.append(line(px, Y(tk), px + pw, Y(tk), "#E6E4F2", 2))
        fb.append(
            text(px - 16, Y(tk) + 11, f"{tk:.1f}", P.T_SMALL, P.MUT, anchor="end")
        )
    fb.append(line(px, Y(0), px + pw, Y(0), P.MUT, 3, id="grounding-zero"))
    slot = pw / len(cats)
    bar = slot / 3
    notes = []
    for ci, c in enumerate(cats):
        x0 = px + ci * slot + (slot - 2 * bar) / 2
        fb.append(
            text(
                px + ci * slot + slot / 2,
                py + ph + 52,
                c,
                P.T_BODY,
                P.INK,
                "bold",
                anchor="middle",
            )
        )
        for si, (sn, vals) in enumerate(series):
            v = vals[ci]
            y1, y2 = Y(max(v, 0)), Y(min(v, 0))
            bx = x0 + si * bar
            fb.append(
                rect(
                    bx,
                    y1,
                    bar - 8,
                    y2 - y1,
                    colors[si],
                    None,
                    1,
                    0,
                    id=f"grounding-bar-{sn}-{ci}",
                )
            )
            lab = f"{v:.3f}".replace("-", "−")
            ly = y1 - 14 if v >= 0 else y2 + P.T_SMALL + 6
            fb.append(
                text(
                    bx + (bar - 8) / 2,
                    ly,
                    lab,
                    P.T_SMALL,
                    P.INK,
                    "bold",
                    anchor="middle",
                )
            )
            notes.append(
                {"text": lab, "font_size": P.T_SMALL, "bold": True, "width": 140}
            )
    lx = px
    for si, (sn, _v) in enumerate(series):
        fb.append(rect(lx, cy0 + 14, 34, 34, colors[si], None, 1, 8))
        fb.append(text(lx + 48, cy0 + 44, sn, P.T_BODY, P.INK))
        lx += 48 + P.text_width(sn, P.T_BODY) + 60
    payload = {
        "name": "grounding-truthfulness",
        "type": "column",
        "grouping": "clustered",
        "x": ix,
        "y": cy0,
        "width": iw,
        "height": ph + 90 + 80,
        "plot_area": {"x": px, "y": py, "width": pw, "height": ph},
        "categories": cats,
        "series": [{"name": sn, "values": vals} for sn, vals in series],
        "gap_width": 100,
        "overlap": 0,
        "axes": {
            "value": {
                "minimum": vmin,
                "maximum": vmax,
                "major_unit": 0.2,
                "number_format": "0.0",
            },
            "category": {"label_position": "low"},
        },
        "show_legend": True,
        "legend_position": "top",
        "style": {"colors": colors},
        "notes": notes,
    }
    gs.append(
        chart_marker("grounding-truthfulness", payload, fb, (ix, cy0, iw, ph + 170))
    )
    y = cy0 + ph + 170 + 10
    for gid, s, sz, col in (
        ("grounding-scoring", G["axis_label"] + ". " + G["scoring"], P.T_SMALL, P.PUR),
        ("grounding-halluc", G["hallucination"], P.T_BODY, P.INK),
    ):
        tx, yy = P.para(ix, y, s, sz, iw, col, bold=gid == "grounding-halluc")
        gs.append(group(gid, (ix, y, iw, yy - y), [tx]))
        y = yy + 12
    bottom = y + PAD - 12
    return [card_block("grounding-card", x, y0, w, bottom), *gs], bottom


def steps_block(x: float, y0: float, w: float) -> tuple[list[str], float]:
    import content as C
    import poster_lib as P

    S = C.STEPS
    ix, iw = x + PAD, w - 2 * PAD
    gs: list[str] = []
    h, y = P.block_heading(ix, y0 + PAD, iw, 6, S["heading"])
    gs.append(group("steps-heading", (ix, y0 + PAD - 10, iw, y - y0 - PAD), [h]))
    leg = [
        rect(ix, y + 4, 34, 34, P.WITHOUT, None, 1, 8),
        text(ix + 48, y + 32, S["legend"][0], P.T_SMALL, P.INK),
        rect(ix + 200, y + 4, 34, 34, P.WITH, None, 1, 8),
        text(ix + 248, y + 32, S["legend"][1], P.T_SMALL, P.INK),
        text(ix + iw, y + 32, S["note"], P.T_SMALL, P.MUT, anchor="end"),
    ]
    gs.append(group("steps-legend", (ix, y, iw, 44), leg))
    y += 54
    name_w, val_w = 470, 400
    bx, bw = ix + name_w, iw - name_w - val_w - 20
    for i, (step, target, a, b, la, lb, extra) in enumerate(S["rows"]):
        kids = [
            text(ix, y + 34, step, P.T_BODY, P.IND, "bold"),
            text(ix, y + 80, target, P.T_SMALL, P.MUT),
            rect(bx, y + 12, max(bw * a, 6), 28, P.WITHOUT, None, 1, 14),
            rect(bx, y + 48, bw * b, 28, P.WITH, None, 1, 14),
            runs_text(
                ix + iw,
                y + 36,
                [(la + " → ", {}), (lb, {"font-weight": "bold"})],
                P.T_BODY,
                P.INK,
                anchor="end",
            ),
        ]
        if extra:
            kids.append(text(ix + iw, y + 72, extra, P.T_SMALL, P.MUT, anchor="end"))
        gs.append(group(f"steps-row-{i}", (ix, y, iw, 104), kids))
        y += 87
    y += 14
    top = y
    tx, y = P.para(ix, y, S["concat"], P.T_BODY, iw, P.INK, bold=True)
    gs.append(group("steps-concat", (ix, top, iw, y - top), [tx]))
    bottom = y + PAD - 10
    return [card_block("steps-card", x, y0, w, bottom), *gs], bottom


def takeaways_block(x: float, y0: float, w: float, bottom: float) -> list[str]:
    """Block 7: takeaways, contacts and funding; QR codes stacked on the right."""
    import content as C
    import poster_lib as P

    T, L = C.TAKEAWAYS, C.LINKS
    ix, iw = x + PAD, w - 2 * PAD
    qr = 165
    lw = iw - qr - 50
    gs: list[str] = []
    h, y = P.block_heading(ix, y0 + PAD, lw, 7, T["heading"])
    gs.append(group("takeaways-heading", (ix, y0 + PAD - 10, lw, y - y0 - PAD), [h]))
    y -= 22
    for i, s in enumerate(T["items"]):
        tx, yy = P.para(ix + 44, y, s, P.T_BODY, lw - 44, P.INK)
        tick = text(ix, y + P.T_BODY, "✓", P.T_BODY, P.GREEN, "bold")
        gs.append(group(f"takeaway-{i}", (ix, y, lw, yy - y), [tick, tx]))
        y = yy
    top = y + 16
    lines = ["  ·  ".join(L["emails"]), *P.wrap(L["funding"], P.T_SMALL, lw)]
    foot = mtext(ix, top + P.T_SMALL, lines, P.T_SMALL, P.LH, P.MUT)
    fh = P.T_SMALL * P.LH * len(lines) + 6
    gs.append(group("takeaways-footer", (ix, top, lw, fh), [foot]))
    used = top + fh
    assert used <= bottom - PAD + 25, (
        f"takeaways overflow by {used - (bottom - PAD)} px"
    )
    qx = ix + iw - qr
    kids = []
    qy = y0 + PAD
    for lab, fname, _url in L["qr"]:
        kids.append(image(img(fname), qx, qy, qr, qr, preserve="xMidYMid meet"))
        kids.append(
            text(
                qx + qr / 2,
                qy + qr + 34,
                lab,
                P.T_SMALL,
                P.IND,
                "bold",
                anchor="middle",
            )
        )
        qy += qr + 60
    gs.append(group("takeaways-qr", (qx, y0 + PAD, qr, qy - y0 - PAD), kids))
    return [card_block("takeaways-card", x, y0, w, bottom), *gs]


def build() -> tuple[str, list[str]]:
    import poster_lib as P

    copy_images()
    gs = [group("background", (0, 0, W, H), [P.background(W, H)])]
    hg, y = header_block()
    gs += hg
    kg, y = hook_block(y + 34)
    gs += kg
    y += GAP
    # two independent columns
    lx, rx = M, M + COLW + GAP
    ly = ry = y
    for f in (resources_block, retrieval_block):
        g, ly = f(lx, ly, COLW)
        gs += g
        ly += GAP
    for f in (pipeline_block, grounding_block, steps_block):
        g, ry = f(rx, ry, COLW)
        gs += g
        ry += GAP
    print("bottoms: left", round(ly - GAP), "right", round(ry - GAP), "page", round(H))
    gs += takeaways_block(lx, ly, COLW, ry - GAP)
    return P.GRAD_DEFS + PIPE_DEFS, gs


def main() -> None:
    defs, groups = build()
    page(groups, defs)
    print("poster:", SVG_DIR / "poster.svg")


if __name__ == "__main__":
    main()
