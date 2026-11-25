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


def _tex_rows(name: str) -> list[list[str]]:
    import re

    rows = []
    for line in (REPORT_TEX[0].parents[1] / "tables" / name).read_text().splitlines():
        if "&" in line and line.rstrip().endswith("\\\\"):
            cells = [
                re.sub(r"\\textbf\{([^}]*)\}", r"\1", c).replace("{,}", ",").strip()
                for c in line.rstrip("\\ ").split("&")
            ]
            rows.append(cells)
    return rows


def test_retrieval_rows_match_table_cells():
    import content

    tex = {
        r[0].replace("$k{=}", "k = ").replace("$", ""): r
        for r in _tex_rows("retrieval.tex")
    }
    # tex columns: Method, Cost, Hit@3, Hit@5, Hit@10, Hit@30, nDCG@10, ...
    for m, cost, h10, h30, ndcg, _hl in content.RETRIEVAL_ROWS:
        key = m.replace("text-emb-3-large", "text-emb-3-large")
        r = tex[key]
        assert [r[1], r[4], r[5], r[6]] == [cost, h10, h30, ndcg], (m, r)


def test_steps_rows_match_layers_table():
    import content

    tex = _tex_rows("e2e-layers.tex")
    for step, target, _a, _b, la, lb, _x in content.STEPS["rows"]:
        r = next(r for r in tex if r[0].replace("--", "–") == step)
        assert r[2] in target, (step, r)
        assert (r[4], r[5]) == (lb, la), (step, r)


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for f in fns:
        f()
    print(f"{len(fns)} tests passed")
