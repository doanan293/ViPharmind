"""Plain-assert tests for check_numbers.py. Run: /usr/bin/python3 docs/poster/build/test_check_numbers.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from check_numbers import REPORT_TEX, numbers_in, unmatched


def test_numbers_in():
    got = numbers_in(["0.923 vs 0.913", "18× fewer", "97.5%"])
    assert got == {"0.923", "0.913", "18", "97.5"}, got


def test_ids_inside_words_are_not_numbers():
    got = numbers_in(["project T2025-PC-019", "an.dv252778m@sis", "Qwen3-Emb-4B"])
    assert got == set(), got


def test_unknown_number_is_reported():
    assert unmatched({"0.923", "0.999"}, REPORT_TEX, set()) == {"0.999"}


def test_latex_thousands_separator():
    assert unmatched({"24,946"}, REPORT_TEX, set()) == set()


def test_latex_minus():
    assert unmatched({"−0.060"}, REPORT_TEX, set()) == set()


def test_allow_list():
    assert unmatched({"1360"}, REPORT_TEX, {"1360"}) == set()


def test_leaflet_quote_is_from_the_mapped_yumangel_section():
    import json

    import content

    data = Path(__file__).resolve().parents[3] / "pharma-lab" / "data"
    maps = json.loads((data / "corpus/formulary/colloquial_mappings.json").read_text())
    entry = next(m for m in maps if "thuốc bao tử chữ Y" in m["aliases"])
    (key,) = entry["section_keys"]
    for line in (data / "corpus/rag-final/sections.jsonl").open(encoding="utf-8"):
        sec = json.loads(line)
        if key in (sec.get("key"), sec.get("section_id"), sec.get("id")):
            body = json.dumps(sec, ensure_ascii=False)
            break
    quote = content.HOOK["leaflet_vi"].strip("“”")
    assert quote in body, quote


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for f in fns:
        f()
    print(f"{len(fns)} tests passed")
