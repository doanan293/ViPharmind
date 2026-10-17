import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pharma_lab.cli.app import app
from pharma_lab.cli.commands import e2e as e2e_commands
from pharma_lab.e2e.corpus_text import CorpusText
from pharma_lab.e2e.golden_generate import (
    MonographNames,
    benchmark_row,
    brand_candidates,
    brand_name,
    colloquial_benchmark,
    colloquial_candidates,
    drug_name,
    generate,
    generate_probes,
    glossary_benchmark,
    glossary_candidates,
    section_slug,
    single_active,
    three_intent_candidates,
    two_drug_candidates,
)

PARA, WARF, ETH = "drug:paracetamol", "drug:warfarin", "drug:ethanol"
PANADOL, EXTRA, COMBO = (
    "leaflet:t:panadol-500",
    "leaflet:t:panadol-extra",
    "leaflet:t:combo",
)
CORPUS = CorpusText(
    sections={
        f"{PARA}:tuong-tac-thuoc": "Dùng cùng warfarin làm tăng INR. Ethanol tăng độc gan.",
        f"{PARA}:chong-chi-dinh": "Suy gan nặng.",
        f"{PARA}:lieu-luong-va-cach-dung": "500 mg mỗi 4 đến 6 giờ.",
        f"{PARA}:chi-dinh": "Đau nhẹ và vừa, sốt.",
        f"{PARA}:tac-dung-khong-mong-muon-adr": "Ban da, độc gan khi quá liều.",
        f"{WARF}:chi-dinh": "Huyết khối.",
        f"{WARF}:tac-dung-khong-mong-muon-adr": "Chảy máu.",
        f"{WARF}:tuong-tac-thuoc": "Paracetamol liều cao làm tăng tác dụng chống đông.",
        f"{WARF}:lieu-luong-va-cach-dung": "Khởi đầu 5 mg mỗi ngày.",
        f"{ETH}:tuong-tac-thuoc": "Nhiều thuốc.",
        f"{PANADOL}:01-thanh-phan": "Paracetamol 500 mg. Tá dược: tinh bột.",
        f"{PANADOL}:02-qua-lieu": "Gây độc gan.",
        f"{EXTRA}:01-thanh-phan": "Paracetamol 500 mg, cafein 65 mg.",
        f"{COMBO}:01-thanh-phan": "Paracetamol 500 mg và warfarin 1 mg.",
    },
    section_documents={
        f"{PARA}:tuong-tac-thuoc": PARA,
        f"{PARA}:chong-chi-dinh": PARA,
        f"{PARA}:lieu-luong-va-cach-dung": PARA,
        f"{PARA}:chi-dinh": PARA,
        f"{PARA}:tac-dung-khong-mong-muon-adr": PARA,
        f"{WARF}:chi-dinh": WARF,
        f"{WARF}:tac-dung-khong-mong-muon-adr": WARF,
        f"{WARF}:tuong-tac-thuoc": WARF,
        f"{WARF}:lieu-luong-va-cach-dung": WARF,
        f"{ETH}:tuong-tac-thuoc": ETH,
        f"{PANADOL}:01-thanh-phan": PANADOL,
        f"{PANADOL}:02-qua-lieu": PANADOL,
        f"{EXTRA}:01-thanh-phan": EXTRA,
        f"{COMBO}:01-thanh-phan": COMBO,
    },
    titles={
        PARA: "PARACETAMOL",
        WARF: "WARFARIN",
        ETH: "ETHANOL",
        PANADOL: "Viên nén Panadol 500 mg trị đau đầu (10 vỉ x 10 viên)",
        EXTRA: "Panadol Extra trị đau (12 vỉ x 10 viên)",
        COMBO: "Combo trị đau (1 vỉ)",
    },
)


@pytest.mark.parametrize(
    ("title", "name"),
    [
        ("Viên nén Panadol 500 mg trị đau đầu (10 vỉ x 10 viên)", "Panadol 500 mg"),
        ("Thuốc mỡ bôi da TACROLIM 0.1% trị viêm da cơ địa tuýp 10 g", "TACROLIM 0.1%"),
        ("Hỗn dịch xịt mũi Avamys trị viêm mũi dị ứng chai 120 liều xịt", "Avamys"),
        (
            "Corbiere Calcium Plus hỗ trợ tăng cường hấp thu canxi hộp 30 ống",
            "Corbiere Calcium Plus",
        ),
        ("Rosepire thuốc tránh thai hằng ngày (1 vỉ x 28 viên)", "Rosepire"),
        ("Siro Rutantop 30 mg/5 ml trị mày đay chai 70 ml", "Rutantop 30 mg/5 ml"),
        ("Infartan 75", "Infartan 75"),
    ],
)
def test_brand_name_keeps_the_product_name_and_strength(title: str, name: str) -> None:
    assert brand_name(title) == name


def test_drug_name_and_section_slug() -> None:
    assert drug_name("ACID  FOLIC") == "Acid folic"
    assert section_slug("drug:a:tuong-tac-thuoc") == "tuong-tac-thuoc"
    assert section_slug("leaflet:t:x:09-qua-lieu") == "qua-lieu"


@pytest.mark.parametrize(
    ("composition", "expected"),
    [
        ("Hoạt chất: Paracetamol 500 mg. Tá dược: acid citric 10 mg, PEG 6000.", True),
        (
            "- Acid alendronic 70 mg (dưới dạng Alendronat natri 91,35 mg). "
            "- Cholecalciferol 5.600 IU. Thành phần tá dược: lactose",
            False,
        ),
        ("Azelastin hydroclorid 15 mg. Fluticason propionat 5,475 mg.", False),
        ("Paracetamol 500 mg, Cafein 65 mg. Tá dược: avicel", False),
    ],
)
def test_single_active_counts_dose_figures_before_the_excipients(
    composition: str, expected: bool
) -> None:
    assert single_active(composition) is expected


def test_monograph_names_match_whole_words_and_skip_excipients() -> None:
    names = MonographNames(CORPUS)
    assert names.named_in("Dùng cùng warfarin; ethanol; paracetamolx") == [WARF]
    assert names.named_in("paracetamol rồi WARFARIN") == [PARA, WARF]


def test_two_drug_pairs_come_from_interaction_sections() -> None:
    first, second = two_drug_candidates(CORPUS, count=5, seed=0)
    by_a = {c.expected_section_ids[0].rsplit(":", 1)[0]: c for c in (first, second)}
    para, warf = by_a[PARA], by_a[WARF]
    assert para.kind == warf.kind == "two_drug"
    assert para.expected_section_ids[0] == f"{PARA}:tuong-tac-thuoc"
    assert para.expected_section_ids[1].startswith(f"{WARF}:")
    assert warf.expected_section_ids[1].startswith(f"{PARA}:")
    assert para.subjects == ("Paracetamol", "Warfarin")
    assert "Paracetamol" in para.query and "Warfarin" in para.query
    # The asked intent on B starts from a rotating one and B must have that section.
    assert first.expected_section_ids[1].endswith(":lieu-luong-va-cach-dung")
    assert all(c.expected_section_ids[1] in CORPUS.sections for c in (first, second))
    assert [c.query_id for c in (first, second)] == [
        "gen-two-drug-0001",
        "gen-two-drug-0002",
    ]


def test_brand_candidates_need_one_ingredient_and_a_missing_section() -> None:
    (only,) = brand_candidates(CORPUS, count=5, seed=0)
    # Combo names two monographs; Panadol Extra repeats the ingredient.
    assert only.kind == "brand_to_ingredient"
    assert only.expected_section_ids[0].endswith(":01-thanh-phan")
    assert only.expected_section_ids[1] == f"{PARA}:tuong-tac-thuoc"
    assert only.subjects in {("Panadol 500 mg",), ("Panadol Extra",)}
    assert only.subjects[0] in only.query


# Paracetamol's three sections span two chunks; warfarin's sit in one chunk.
CHUNKS = {
    f"{PARA}:chi-dinh": f"{PARA}:chunk-001",
    f"{PARA}:lieu-luong-va-cach-dung": f"{PARA}:chunk-001",
    f"{PARA}:tac-dung-khong-mong-muon-adr": f"{PARA}:chunk-002",
    f"{WARF}:chi-dinh": f"{WARF}:chunk-001",
    f"{WARF}:lieu-luong-va-cach-dung": f"{WARF}:chunk-001",
    f"{WARF}:tac-dung-khong-mong-muon-adr": f"{WARF}:chunk-001",
}


def test_three_intent_needs_sections_in_two_chunks_and_skips_used_drugs() -> None:
    (only,) = three_intent_candidates(CORPUS, CHUNKS, count=5, seed=0)
    assert only.kind == "three_intent"
    assert only.expected_section_ids == (
        f"{PARA}:chi-dinh",
        f"{PARA}:lieu-luong-va-cach-dung",
        f"{PARA}:tac-dung-khong-mong-muon-adr",
    )
    assert only.subjects == ("Paracetamol",) and "Paracetamol" in only.query
    assert (
        three_intent_candidates(
            CORPUS, CHUNKS, count=5, seed=0, exclude_documents=[PARA]
        )
        == []
    )


def test_generate_rows_match_the_candidate_format() -> None:
    rows = generate(
        CORPUS,
        {"three_intent": 1, "two_drug": 1, "brand_to_ingredient": 1},
        seed=0,
        chunks=CHUNKS,
    )
    assert [r["kind"] for r in rows] == [
        "three_intent",
        "two_drug",
        "brand_to_ingredient",
    ]
    assert rows[0]["generated"] is True and rows[0]["missing"] == []
    assert isinstance(rows[0]["subjects"], list) and rows[0]["eval_group"] is None
    assert generate(CORPUS, {"two_drug": 0}, seed=0) == []
    with pytest.raises(ValueError, match="chunk map"):
        generate(CORPUS, {"three_intent": 1}, seed=0)


def test_cli_generate_writes_the_candidates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(e2e_commands, "read_bundle", lambda bundle: object())
    monkeypatch.setattr(e2e_commands, "corpus_text", lambda knowledge: CORPUS)
    monkeypatch.setattr(e2e_commands, "section_chunks", lambda knowledge: CHUNKS)
    # An authored three-intent item on paracetamol keeps that drug out of the candidates.
    (tmp_path / "multi-hop-01.authored.jsonl").write_text(
        json.dumps(
            {
                "item_id": "e2e-mhop-0001",
                "tags": ["three_intent"],
                "gold_section_ids": [f"{PARA}:chi-dinh"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        app,
        [
            "e2e",
            "golden",
            "generate",
            "--authoring-dir",
            str(tmp_path),
            "--two-drug",
            "1",
        ],
    )
    assert result.exit_code == 0, result.output
    rows = [
        json.loads(line)
        for line in (tmp_path / "multi-hop.generated.jsonl")
        .read_text("utf-8")
        .splitlines()
    ]
    assert [r["kind"] for r in rows] == ["two_drug", "brand_to_ingredient"]


def test_colloquial_probe_names_the_product_only_by_an_absent_alias() -> None:
    aliases = [
        ("Panadol đỏ", [f"{PANADOL}:01-thanh-phan"]),
        # Present in the leaflet title, so retrieval needs no enrichment for it.
        ("Panadol Extra", [f"{EXTRA}:01-thanh-phan"]),
    ]
    corpus = CorpusText(
        sections={
            **CORPUS.sections,
            f"{PANADOL}:02-cach-dung-lieu-dung": "Uống 1 viên.",
        },
        section_documents={
            **CORPUS.section_documents,
            f"{PANADOL}:02-cach-dung-lieu-dung": PANADOL,
        },
        titles=CORPUS.titles,
    )
    (only,) = colloquial_candidates(corpus, aliases, count=5, seed=0)
    assert only.kind == "colloquial" and only.subjects == ("Panadol đỏ",)
    assert only.expected_section_ids == (f"{PANADOL}:02-cach-dung-lieu-dung",)
    assert only.query.startswith("Panadol đỏ")


def test_glossary_probe_uses_the_phrase_the_section_does_not_write() -> None:
    nsaid = "drug:x:tuong-tac-thuoc"
    spelled = "drug:y:tuong-tac-thuoc"
    corpus = CorpusText(
        sections={
            nsaid: "Dùng cùng NSAID làm tăng nguy cơ chảy máu.",
            spelled: "NSAID (thuốc kháng viêm không steroid) làm giảm tác dụng.",
        },
        section_documents={nsaid: "drug:x", spelled: "drug:y"},
        titles={"drug:x": "WARFARIN", "drug:y": "FUROSEMID"},
    )
    (only,) = glossary_candidates(corpus, count=5, seed=0)
    assert only.expected_section_ids == (nsaid,)
    assert "thuốc kháng viêm không steroid" in only.query
    assert only.subjects == ("Warfarin", "thuốc kháng viêm không steroid")
    rows = generate_probes(corpus, [], {"glossary": 1, "colloquial": 0}, seed=0)
    assert [r["kind"] for r in rows] == ["glossary"]


def test_enrichment_benchmark_asks_every_alias_and_term_in_benchmark_rows() -> None:
    sections = {
        f"{PANADOL}:02-cach-dung-lieu-dung": "Uống 1 viên.",
        f"{PANADOL}:05-chong-chi-dinh": "Suy gan nặng.",
        "drug:x:tuong-tac-thuoc": "Dùng cùng NSAID làm tăng nguy cơ chảy máu.",
    }
    corpus = CorpusText(
        sections=sections,
        section_documents={
            f"{PANADOL}:02-cach-dung-lieu-dung": PANADOL,
            f"{PANADOL}:05-chong-chi-dinh": PANADOL,
            "drug:x:tuong-tac-thuoc": "drug:x",
        },
        titles={PANADOL: "Panadol Extra", "drug:x": "WARFARIN"},
    )
    aliases = [
        ("Panadol đỏ", [f"{PANADOL}:02-cach-dung-lieu-dung"]),
        ("Panadol hộp đỏ", [f"{PANADOL}:02-cach-dung-lieu-dung"]),
    ]
    colloquial = colloquial_benchmark(corpus, aliases)
    # Two aliases, two leaflet sections each.
    assert len(colloquial) == 4
    assert {c.query_id for c in colloquial} == {
        f"enrich-colloquial-{n:04d}" for n in range(1, 5)
    }
    (glossary,) = glossary_benchmark(corpus)
    row = benchmark_row(glossary)
    assert row["eval_group"] == "glossary" and row["answer_mode"] == "single"
    assert row["expected_section_ids"] == ["drug:x:tuong-tac-thuoc"]
    assert row["intent_category"] == "tuong-tac-thuoc"
