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

from lib import group, text  # noqa: E402

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


def style_sheet() -> tuple[str, list[str]]:
    """One of each style A component, to check the look before the real blocks."""
    import poster_lib as P

    gs = [group("background", (0, 0, W, H), [P.background(W, H)])]
    gs.append(group("mascot", (2700, 80, 400, 300), [P.mascot(2700, 80, 400)]))
    gs.append(
        group(
            "title",
            (120, 120, 2500, 340),
            [text(140, 260, "Style sheet", P.T_TITLE, P.IND, "bold")],
        )
    )
    gs.append(
        group("card", (120, 500, 2940, 1500), [P.soft_card(120, 500, 2940, 1500)])
    )
    h, _ = P.block_heading(
        180, 560, 2800, 1, "A block heading that states one finding in plain words"
    )
    gs.append(group("heading", (180, 560, 2800, 200), [h]))
    b, by = P.bubble(
        180,
        800,
        1300,
        "Is metformin OK while breastfeeding?",
        "Đang cho con bú dùng metformin có sao không?",
    )
    gs.append(group("bubble", (180, 800, 1300, by - 800), [b]))
    v, vy = P.verdict_card(
        1600,
        800,
        1380,
        "bad",
        "✗  Gemini 3.8 Flash, no documents",
        "Breastfeeding women CAN USE metformin…",
        "Phụ nữ đang cho con bú CÓ THỂ DÙNG ĐƯỢC Metformin…",
        "Contradicts the formulary",
    )
    gs.append(group("verdict-bad", (1600, 800, 1380, vy - 800), [v]))
    v2, vy2 = P.verdict_card(
        1600,
        vy + 30,
        1380,
        "good",
        "✓  Same model in our pipeline",
        "Metformin passes into breast milk [2, 3]…",
        "Metformin có bài tiết vào sữa mẹ [2, 3]…",
        "Matches the formulary, with citations",
    )
    gs.append(group("verdict-good", (1600, vy + 30, 1380, vy2 - vy - 30), [v2]))
    gs.append(
        group(
            "stat",
            (180, 1500, 900, 400),
            [
                P.stat_card(
                    180,
                    1500,
                    900,
                    400,
                    "2,409",
                    "everyday nicknames mapped to products",
                    P.LAV,
                )
            ],
        )
    )
    return P.GRAD_DEFS, gs


def main() -> None:
    defs, groups = style_sheet()
    page(groups, defs)
    print("poster:", SVG_DIR / "poster.svg")


if __name__ == "__main__":
    main()
