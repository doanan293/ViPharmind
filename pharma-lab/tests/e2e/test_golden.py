import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pharma_agent.domain.corpus.bundle import read_bundle
from pydantic import ValidationError
from typer.testing import CliRunner

from pharma_lab.bundle.export import ExportRequest, export_bundle
from pharma_lab.cli.app import app
from pharma_lab.e2e.corpus_text import CorpusText, chunk_texts, load_corpus_text
from pharma_lab.e2e.golden import (
    ANSWERABLE_PER_GROUP,
    EVAL_GROUPS,
    MULTI_HOP_KINDS,
    MULTI_HOP_QUOTAS,
    QUOTAS,
    SCHEMA,
    Category,
    GoldenItem,
    build_golden,
    load_golden,
    manifest_path,
    validate_items,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "rag_final_small"
SECTION = "drug:paracetamol:lieu-dung"
CORPUS = CorpusText(
    sections={SECTION: "Người lớn uống **500 mg** mỗi\n4-6 giờ, tối đa 4 g/ngày."},
    section_documents={SECTION: "drug:paracetamol"},
    titles={"drug:paracetamol": "Paracetamol"},
)


def answerable(item_id: str = "e2e-ans-0001", **changes: Any) -> GoldenItem:
    data: dict[str, Any] = {
        "item_id": item_id,
        "category": "answerable",
        "source_query_id": "q-1",
        "turns": [{"role": "user", "text": "Liều paracetamol người lớn?"}],
        "expected_behavior": "grounded",
        "gold_section_ids": [SECTION],
        "reference": {
            "answer": "500 mg mỗi 4-6 giờ, tối đa 4 g/ngày.",
            "key_facts": [
                {
                    "fact": "Tối đa 4 g mỗi ngày",
                    "evidence_quote": "mỗi 4-6 giờ, tối đa 4 g/ngày",
                    "section_id": SECTION,
                }
            ],
        },
        "eval_group": "formulary",
    }
    data.update(changes)
    return GoldenItem.model_validate(data)


def special(category: str, prefix: str, behavior: str, **changes: Any) -> GoldenItem:
    data: dict[str, Any] = {
        "item_id": f"{prefix}0001",
        "category": category,
        "turns": [{"role": "user", "text": "Câu hỏi"}],
        "expected_behavior": behavior,
    }
    data.update(changes)
    return GoldenItem.model_validate(data)


def multi_hop(item_id: str = "e2e-mhop-0001", **changes: Any) -> GoldenItem:
    data: dict[str, Any] = {
        "category": "multi_hop",
        "eval_group": None,
        "tags": ["two_drug"],
    }
    data.update(changes)
    return answerable(item_id, **data)


def test_golden_schema_is_v3_without_chunk_ids() -> None:
    assert SCHEMA == "e2e-golden-v3"
    assert "structured" in EVAL_GROUPS and "chunk_risk" not in EVAL_GROUPS
    with pytest.raises(ValidationError):
        GoldenItem.model_validate(
            {**answerable().model_dump(mode="json"), "gold_chunk_ids": ["x"]}
        )


def test_golden_keeps_500_items_with_a_multi_hop_split() -> None:
    assert QUOTAS[Category.ANSWERABLE] == 270
    assert QUOTAS[Category.MULTI_HOP] == 150
    assert sum(QUOTAS.values()) == 500


def test_a_multi_hop_item_names_exactly_one_kind() -> None:
    assert validate_items([multi_hop()], CORPUS, complete=False) == []
    assert MULTI_HOP_KINDS == (
        "retrieval_miss",
        "noisy_retry",
        "three_intent",
        "two_drug",
        "brand_to_ingredient",
    )
    assert sum(MULTI_HOP_QUOTAS.values()) == QUOTAS[Category.MULTI_HOP]
    untagged = multi_hop(tags=[])
    both = multi_hop(tags=["two_drug", "three_intent"])
    for item in (untagged, both):
        assert validate_items([item], CORPUS, complete=False) == [
            "e2e-mhop-0001: multi_hop items need exactly one kind tag "
            "(retrieval_miss, noisy_retry, three_intent, two_drug, brand_to_ingredient)"
        ]


def test_a_valid_answerable_item_has_no_problems() -> None:
    assert validate_items([answerable()], CORPUS, complete=False) == []


def test_quote_must_be_in_the_section_text_after_space_normalisation() -> None:
    fact = {
        "fact": "Liều",
        "evidence_quote": "uống 1 g mỗi",
        "section_id": SECTION,
    }
    item = answerable(reference={"answer": "", "key_facts": [fact]})
    problems = validate_items([item], CORPUS, complete=False)
    assert problems == [f"e2e-ans-0001: key fact 1 quote is not in section {SECTION}"]


def test_key_fact_section_must_be_a_gold_section() -> None:
    fact = {"fact": "x", "evidence_quote": "tối đa", "section_id": "other"}
    item = answerable(reference={"answer": "", "key_facts": [fact]})
    assert validate_items([item], CORPUS, complete=False) == [
        "e2e-ans-0001: key fact 1 cites other, which is not a gold section"
    ]


def test_grounded_items_need_facts_and_special_items_have_none() -> None:
    bare = answerable(reference={"answer": "", "key_facts": []})
    redirect = special(
        "out_of_scope", "e2e-oos-", "redirect", gold_section_ids=[SECTION]
    )
    assert validate_items([bare, redirect], CORPUS, complete=False) == [
        "e2e-ans-0001: grounded items need key facts and gold sections",
        "e2e-oos-0001: non-grounded items have no key facts or gold ids",
    ]


def test_category_fixes_the_expected_behavior() -> None:
    item = special("injection", "e2e-inj-", "abstain")
    assert validate_items([item], CORPUS, complete=False) == [
        "e2e-inj-0001: injection expects blocked, not abstain"
    ]


def test_turn_shapes_per_category() -> None:
    two_users = answerable(
        turns=[{"role": "user", "text": "a"}, {"role": "user", "text": "b"}]
    )
    short_dialogue = answerable(
        "e2e-mt-0001", category="multi_turn", turns=[{"role": "user", "text": "a"}]
    )
    dialogue = answerable(
        "e2e-mt-0002",
        category="multi_turn",
        turns=[
            {"role": "user", "text": "Paracetamol dùng làm gì?"},
            {"role": "assistant", "text": "Giảm đau, hạ sốt."},
            {"role": "user", "text": "Người lớn uống tối đa bao nhiêu?"},
        ],
    )
    assert validate_items(
        [two_users, short_dialogue, dialogue], CORPUS, complete=False
    ) == [
        "e2e-ans-0001: answerable needs exactly one user turn",
        "e2e-mt-0001: multi_turn needs alternating user/assistant turns "
        "ending with user (at least 3)",
    ]
    assert dialogue.question == "Người lớn uống tối đa bao nhiêu?"
    assert dialogue.history == [("Paracetamol dùng làm gì?", "Giảm đau, hạ sốt.")]


def test_unanswerable_terms_must_be_absent_from_the_corpus() -> None:
    missing = special("unanswerable", "e2e-una-", "abstain")
    present = special(
        "unanswerable",
        "e2e-una-",
        "abstain",
        item_id="e2e-una-0002",
        absent_terms=["PARACETAMOL", "Zolgensma"],
    )
    assert validate_items([missing, present], CORPUS, complete=False) == [
        "e2e-una-0001: unanswerable items need absent_terms",
        "e2e-una-0002: absent term 'PARACETAMOL' occurs in the corpus",
    ]


def test_ids_are_unique_and_prefixed() -> None:
    items = [answerable("e2e-ans-0001"), answerable("e2e-ans-0001")]
    wrong = answerable("item-1")
    assert validate_items([*items, wrong], CORPUS, complete=False) == [
        "e2e-ans-0001: duplicate item_id",
        "item-1: id must start with e2e-ans-",
    ]


def complete_set() -> list[GoldenItem]:
    items = [
        answerable(f"e2e-ans-{group}-{index:02d}", eval_group=group)
        for group in EVAL_GROUPS
        for index in range(ANSWERABLE_PER_GROUP)
    ]
    dialogue = [
        {"role": "user", "text": "Paracetamol dùng làm gì?"},
        {"role": "assistant", "text": "Giảm đau."},
        {"role": "user", "text": "Liều tối đa?"},
    ]
    items += [
        answerable(f"e2e-mt-{index:04d}", category="multi_turn", turns=dialogue)
        for index in range(QUOTAS[Category.MULTI_TURN])
    ]
    items += [
        multi_hop(f"e2e-mhop-{kind}-{index:04d}", tags=[kind])
        for kind, quota in MULTI_HOP_QUOTAS.items()
        for index in range(quota)
    ]
    for category, prefix, behavior, extra in (
        ("unanswerable", "e2e-una-", "abstain", {"absent_terms": ["Zolgensma"]}),
        ("out_of_scope", "e2e-oos-", "redirect", {}),
        ("injection", "e2e-inj-", "blocked", {}),
    ):
        items += [
            special(category, prefix, behavior, item_id=f"{prefix}{index:04d}", **extra)
            for index in range(10)
        ]
    return items


def test_complete_sets_must_match_the_quotas() -> None:
    items = complete_set()
    assert validate_items(items, CORPUS, complete=True) == []
    short = [
        item
        for item in items
        if item.item_id not in {"e2e-ans-leaflet-00", "e2e-mhop-two_drug-0000"}
    ]
    assert validate_items(short, CORPUS, complete=True) == [
        "answerable: 269 items, expected 270",
        "multi_hop: 149 items, expected 150",
        "answerable leaflet: 44 items, expected 45",
        "multi_hop two_drug: 41 items, expected 42",
    ]


def write_batch(path: Path, items: list[GoldenItem]) -> Path:
    path.write_text(
        "".join(item.model_dump_json() + "\n" for item in items), encoding="utf-8"
    )
    return path


def build(tmp_path: Path, sources: list[Path]) -> Callable[[], object]:
    return lambda: build_golden(
        sources,
        tmp_path / "golden_e2e.jsonl",
        CORPUS,
        bundle_manifest_sha256="b" * 64,
        gold_sha256="g" * 64,
    )


def test_build_freezes_sorted_items_and_a_manifest(tmp_path: Path) -> None:
    items = complete_set()
    sources = [
        write_batch(tmp_path / "b.authored.jsonl", items[:250]),
        write_batch(tmp_path / "a.authored.jsonl", items[250:]),
    ]

    build(tmp_path, sources)()

    output = tmp_path / "golden_e2e.jsonl"
    frozen = load_golden(output)
    assert [item.item_id for item in frozen] == sorted(i.item_id for i in items)
    manifest = json.loads(manifest_path(output).read_text("utf-8"))
    assert manifest["schema"] == "e2e-golden-v3"
    assert manifest["counts"] == {
        "answerable": 270,
        "injection": 10,
        "multi_hop": 150,
        "multi_turn": 50,
        "out_of_scope": 10,
        "unanswerable": 10,
    }
    assert manifest["answerable_per_group"]["leaflet"] == 45
    assert len(manifest["sha256"]) == 64


def test_build_reports_every_problem_and_writes_nothing(tmp_path: Path) -> None:
    source = write_batch(tmp_path / "a.authored.jsonl", [answerable("bad")])
    with pytest.raises(ValueError, match="bad: id must start with e2e-ans-"):
        build(tmp_path, [source])()
    assert not (tmp_path / "golden_e2e.jsonl").exists()


def test_corpus_text_reads_sections_and_titles_from_a_bundle(tmp_path: Path) -> None:
    export_bundle(
        ExportRequest(
            rag_final_dir=FIXTURE,
            glossary_path=FIXTURE / "term_glossary.json",
            mappings_path=FIXTURE / "colloquial_mappings.json",
            output_dir=tmp_path / "bundle",
        )
    )

    corpus = load_corpus_text(tmp_path / "bundle")

    assert corpus.sections
    section_id, text = next(iter(corpus.sections.items()))
    assert text.strip()
    assert corpus.section_documents[section_id] in corpus.titles
    assert corpus.contains(text.split()[0])
    assert not corpus.contains("zzzz-not-a-drug")
    chunks = chunk_texts(read_bundle(tmp_path / "bundle"), [section_id])
    assert chunks
    document = corpus.section_documents[section_id]
    assert all(label.startswith(f"{document}:chunk-") for label in chunks)


def test_cli_builds_the_golden_set(tmp_path: Path) -> None:
    export_bundle(
        ExportRequest(
            rag_final_dir=FIXTURE,
            glossary_path=FIXTURE / "term_glossary.json",
            mappings_path=FIXTURE / "colloquial_mappings.json",
            output_dir=tmp_path / "bundle",
        )
    )
    (tmp_path / "authoring").mkdir()
    write_batch(tmp_path / "authoring" / "a.authored.jsonl", [answerable()])
    gold = tmp_path / "gold.jsonl"
    gold.write_text("{}\n", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "e2e",
            "golden",
            "build",
            "--sources",
            str(tmp_path / "authoring"),
            "--output",
            str(tmp_path / "golden.jsonl"),
            "--bundle",
            str(tmp_path / "bundle"),
            "--evaluation",
            str(gold),
        ],
    )

    assert result.exit_code == 1
    assert (
        "gold section drug:paracetamol:lieu-dung is not in the bundle" in result.output
    )


def test_cli_checks_one_batch(tmp_path: Path) -> None:
    export_bundle(
        ExportRequest(
            rag_final_dir=FIXTURE,
            glossary_path=FIXTURE / "term_glossary.json",
            mappings_path=FIXTURE / "colloquial_mappings.json",
            output_dir=tmp_path / "bundle",
        )
    )
    corpus = load_corpus_text(tmp_path / "bundle")
    section, text = next(iter(corpus.sections.items()))
    fact = {
        "fact": "f",
        "evidence_quote": text.split("\n")[0][:30],
        "section_id": section,
    }
    good = answerable(
        gold_section_ids=[section],
        reference={"answer": "a", "key_facts": [fact]},
    )
    batch = write_batch(tmp_path / "a.authored.jsonl", [good])

    result = CliRunner().invoke(
        app,
        ["e2e", "golden", "check", str(batch), "--bundle", str(tmp_path / "bundle")],
    )

    assert result.exit_code == 0, result.output
    assert "items=1" in result.output
