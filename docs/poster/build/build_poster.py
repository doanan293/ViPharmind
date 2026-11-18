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

from lib import chart_marker, group, rect, text  # noqa: E402

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


def spike() -> list[str]:
    from build_deck import simple_table

    defs = (
        '<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#F3EFFF"/><stop offset="1" stop-color="#FFF6EC"/>'
        "</linearGradient>"
    )
    bg = group(
        "background",
        (0, 0, W, H),
        [f'<rect x="0" y="0" width="{W}" height="{H}" fill="url(#bg)"/>'],
    )
    card = group(
        "card",
        (120, 500, 2940, 1800),
        [rect(120, 500, 2940, 1800, "#FFFFFF", None, 1, 48)],
    )
    title = group(
        "title",
        (120, 120, 2940, 340),
        [
            text(140, 260, "Agentic RAG for Vietnamese", 133, "#0C0A9E", "bold"),
            text(140, 400, "Pharmaceutical Documents", 133, "#0C0A9E", "bold"),
        ],
    )
    table = simple_table(
        "spike-table",
        200,
        600,
        [900, 400, 400],
        80,
        ["Method", "Hit@10", "nDCG@10"],
        [["BM25", "81.3", "0.621"], ["Hybrid", "95.9", "0.784"]],
        font=40,
        hfont=40,
    )
    cats = ["Gemini 3.8 Flash", "Qwen3.5-9B"]
    payload = {
        "name": "spike-chart",
        "type": "column",
        "grouping": "clustered",
        "x": 200,
        "y": 1000,
        "width": 2700,
        "height": 1200,
        "plot_area": {"x": 400, "y": 1100, "width": 2400, "height": 1000},
        "categories": cats,
        "series": [
            {"name": "Closed-book", "values": [0.268, -0.060]},
            {"name": "Full agent", "values": [0.923, 0.913]},
        ],
        "gap_width": 80,
        "overlap": 0,
        "axes": {
            "value": {
                "minimum": -0.2,
                "maximum": 1.0,
                "major_unit": 0.2,
                "number_format": "0.0",
            },
            "category": {"label_position": "low"},
        },
        "show_legend": True,
        "legend_position": "top",
        "style": {"colors": ["#8F8CF0", "#FFB27A"]},
    }
    fb = [
        rect(400, 1100, 2400, 1000, "#FFFFFF", None, 1, 0),
        text(400, 1080, "Closed-book", 40, "#1D1D1D"),
        text(900, 1080, "Full agent", 40, "#1D1D1D"),
        text(1000, 2160, "Gemini 3.8 Flash", 40, "#1D1D1D", anchor="middle"),
        text(2200, 2160, "Qwen3.5-9B", 40, "#1D1D1D", anchor="middle"),
    ]
    chart = chart_marker("spike-chart", payload, fb, (200, 1000, 2700, 1200))
    return defs, [bg, card, title, table, chart]


def main() -> None:
    defs, groups = spike()
    page(groups, defs)
    print("poster:", SVG_DIR / "poster.svg")


if __name__ == "__main__":
    main()
