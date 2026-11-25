"""Check that every number shown on the poster appears in the paper sources.

Usage: check_numbers.py <poster.svg>   (prints unmatched numbers, exits 1 if any)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

REPORT = Path(__file__).resolve().parents[2] / "report"
REPORT_TEX = sorted(
    p for d in ("tables", "figures", "sections") for p in (REPORT / d).glob("*.tex")
)

NUM = re.compile(r"[−-]?\d+(?:[.,]\d+)*")

# Numbers on the poster that are not results in docs/report/*.tex, each with its reason.
ALLOW = {
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",  # block badges, citation marks, leaflet dosage
    "1360",  # paper id
    "2026",  # conference year
    "18",
    "25",  # "eighteen- to twenty-five-fold" (prose): 18.3% → 1.0%, 30.6% → 1.2%
    "−1",
    "-1",
    "0",  # truthfulness scoring rule (Eq. 1) and the zero line
    "−0.2",
    "-0.2",
    "0.0",
    "0.2",
    "0.4",
    "0.6",
    "0.8",
    "1.0",  # chart axis ticks
}


def _norm_src(s: str) -> str:
    s = s.replace("{,}", ",").replace("$-$", "-").replace("\\%", "%")
    return s.replace("−", "-")


def numbers_in(texts: list[str]) -> set[str]:
    """Numbers in the texts; tokens glued to letters (ids, model names, emails) are skipped."""
    out: set[str] = set()
    for t in texts:
        for word in re.findall(r"[\w.,@−-]+", t):
            if re.search(r"[A-Za-z]", word):
                continue
            out.update(NUM.findall(word))
    return out


def unmatched(numbers: set[str], sources: list[Path], allow: set[str]) -> set[str]:
    src = _norm_src("\n".join(Path(p).read_text(encoding="utf-8") for p in sources))
    bad = set()
    for n in numbers:
        if n in allow:
            continue
        k = n.replace("−", "-")
        pat = r"(?<![\d.,])" + re.escape(k) + r"(?![\d]|[.,]\d)"
        if k.startswith("-"):
            pat = re.escape(k) + r"(?![\d]|[.,]\d)"
        if not re.search(pat, src):
            bad.add(n)
    return bad


def svg_texts(path) -> list[str]:
    root = ET.parse(path).getroot()
    return [
        "".join(el.itertext()) for el in root.iter() if el.tag.split("}")[-1] == "text"
    ]


if __name__ == "__main__":
    bad = unmatched(numbers_in(svg_texts(sys.argv[1])), REPORT_TEX, ALLOW)
    for n in sorted(bad):
        print("not in the paper:", n)
    sys.exit(1 if bad else 0)
