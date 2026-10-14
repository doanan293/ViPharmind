from collections.abc import Iterable

from pharma_lab.e2e.corpus_text import CorpusText
from pharma_lab.e2e.golden import GoldenItem
from pharma_lab.e2e.golden_remap import remap_item, strip_hint

PAGE = "leaflet:t:pramital-20"
PRECAUTION = f"{PAGE}:05-luu-y"
PREGNANCY = f"{PAGE}:06-thai-ky-va-cho-con-bu"
QUOTE = "Không dùng trong ba tháng đầu."
CORPUS = CorpusText(
    sections={
        PRECAUTION: "# Pramital 20 mg\n\n### 5. Lưu ý\n\nTheo dõi ý định tự sát.",
        PREGNANCY: f"# Pramital 20 mg\n\n### 6. Thai kỳ và cho con bú\n\n{QUOTE}",
    },
    section_documents={PRECAUTION: PAGE, PREGNANCY: PAGE},
    titles={PAGE: "Pramital 20 mg trị trầm cảm (2 vỉ x 14 viên)"},
)


def _chunks_for(corpus: CorpusText):
    def lookup(section_ids: Iterable[str]) -> dict[str, str]:
        return {f"{sid}:chunk-001": corpus.sections[sid] for sid in section_ids}

    return lookup


def _item() -> GoldenItem:
    return GoldenItem.model_validate(
        {
            "item_id": "e2e-ans-0001",
            "category": "answerable",
            "source_query_id": "q",
            "turns": [
                {
                    "role": "user",
                    "text": "Khi dùng Pramital 20 mg trị trầm cảm (2 vỉ x 14 viên) "
                    "cần lưu ý gì? (phần thai kỳ và cho con bú)",
                }
            ],
            "expected_behavior": "grounded",
            "gold_section_ids": [PAGE],
            "gold_chunk_ids": [f"{PAGE}:chunk-003"],
            "reference": {
                "answer": QUOTE,
                "key_facts": [
                    {
                        "fact": "Không dùng ba tháng đầu",
                        "evidence_quote": QUOTE,
                        "section_id": PAGE,
                    }
                ],
            },
            "eval_group": "patient_natural",
        }
    )


def test_strip_hint_removes_trailing_phan_suffix_only() -> None:
    assert strip_hint("A cần lưu ý gì? (phần thai kỳ)") == "A cần lưu ý gì?"
    assert strip_hint("X dùng để làm gì? (phần công dụng (chỉ định))") == (
        "X dùng để làm gì?"
    )
    kept = "Fordia 850 mg (10 vỉ x 10 viên) dùng liều thế nào?"
    assert strip_hint(kept) == kept


def test_remap_moves_gold_ids_to_the_subsection_holding_the_quote() -> None:
    result = remap_item(_item(), CORPUS, _chunks_for(CORPUS))
    item = result.item
    assert item.gold_section_ids == [PREGNANCY]
    assert item.gold_chunk_ids == [f"{PREGNANCY}:chunk-001"]
    assert item.reference.key_facts[0].section_id == PREGNANCY
    assert item.eval_group == "leaflet_short"
    assert item.turns[-1].text == (
        "Khi dùng Pramital 20 mg trị trầm cảm (2 vỉ x 14 viên) cần lưu ý gì?"
    )
    assert any("hint removed" in note for note in result.notes)


def test_remap_reports_quotes_found_in_several_subsections() -> None:
    corpus = CorpusText(
        sections={
            **CORPUS.sections,
            PRECAUTION: CORPUS.sections[PRECAUTION] + f"\n\n{QUOTE}",
        },
        section_documents=CORPUS.section_documents,
        titles=CORPUS.titles,
    )
    result = remap_item(_item(), corpus, _chunks_for(corpus))
    assert any("ambiguous" in note for note in result.notes)
    assert result.item.gold_section_ids == [PRECAUTION, PREGNANCY]


def test_remap_leaves_formulary_items_unchanged() -> None:
    section = "drug:paracetamol:lieu-dung"
    corpus = CorpusText(
        sections={section: "Người lớn tối đa 4 g/ngày."},
        section_documents={section: "drug:paracetamol"},
        titles={"drug:paracetamol": "Paracetamol"},
    )
    item = GoldenItem.model_validate(
        {
            **_item().model_dump(mode="json"),
            "turns": [{"role": "user", "text": "Liều tối đa paracetamol?"}],
            "gold_section_ids": [section],
            "gold_chunk_ids": [f"{section}:chunk-001"],
            "reference": {
                "answer": "4 g/ngày",
                "key_facts": [
                    {
                        "fact": "Tối đa 4 g",
                        "evidence_quote": "tối đa 4 g/ngày",
                        "section_id": section,
                    }
                ],
            },
            "eval_group": "formulary",
        }
    )
    result = remap_item(item, corpus, _chunks_for(corpus))
    assert result.item == item
    assert result.notes == []
