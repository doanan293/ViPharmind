import random

from pharma_lab.e2e.conversational import (
    PHENOMENA,
    Item,
    _Index,
    answer_text,
    build_conversational,
    build_item,
    single_ingredient_leaflets,
    strip_diacritics,
)
from pharma_lab.e2e.corpus_text import CorpusText

LONG = " ".join(["chữ"] * 30)
PARA, WARF, LEAF = "drug:paracetamol", "drug:warfarin", "leaflet:t:panadol"
SECTIONS = {
    f"{PARA}:lieu-luong-va-cach-dung": f"Người lớn uống 500 mg. Tối đa 4 g. {LONG}",
    f"{PARA}:chi-dinh": f"Giảm đau, hạ sốt. {LONG}",
    f"{PARA}:chong-chi-dinh": f"Suy gan nặng. {LONG}",
    f"{PARA}:ten-thuong-mai": "Panadol; Efferalgan.",
    f"{WARF}:lieu-luong-va-cach-dung": f"Khởi đầu 5 mg mỗi ngày. {LONG}",
    f"{WARF}:chi-dinh": f"Huyết khối. {LONG}",
    f"{LEAF}:01-thanh-phan": f"Hoạt chất: Paracetamol 500 mg. Tá dược: tinh bột. {LONG}",
}
CORPUS = CorpusText(
    sections=SECTIONS,
    section_documents={k: k.rsplit(":", 1)[0] for k in SECTIONS},
    titles={PARA: "PARACETAMOL", WARF: "WARFARIN", LEAF: "Panadol 500 mg trị đau"},
)


def row(qid: str, section: str, intent: str, query: str, **extra: object) -> dict:
    return {
        "query_id": qid,
        "query": query,
        "eval_group": extra.pop("eval_group", "formulary"),
        "intent_category": intent,
        "expected_section_id": section,
        "expected_section_ids": extra.pop("sections", [section]),
        "answer_mode": extra.pop("answer_mode", "single"),
        **extra,
    }


ROWS = [
    row("p-dose", f"{PARA}:lieu-luong-va-cach-dung", "dosage", "PARACETAMOL liều?"),
    row("p-ind", f"{PARA}:chi-dinh", "indication", "PARACETAMOL chữa gì?"),
    row(
        "p-ci",
        f"{PARA}:chong-chi-dinh",
        "contraindication",
        "Ai không dùng PARACETAMOL?",
    ),
    row("p-brand", f"{PARA}:ten-thuong-mai", "brand_lookup", "Biệt dược PARACETAMOL?"),
    row("w-dose", f"{WARF}:lieu-luong-va-cach-dung", "dosage", "WARFARIN liều?"),
    row("w-ind", f"{WARF}:chi-dinh", "indication", "WARFARIN chữa gì?"),
    row(
        "p-multi",
        f"{PARA}:chi-dinh",
        "multi_intent",
        "PARACETAMOL chữa gì và liều?",
        sections=[f"{PARA}:chi-dinh", f"{PARA}:lieu-luong-va-cach-dung"],
        answer_mode="multi_required",
        eval_group="multi_intent",
    ),
]


def make(phenomenon: str, parent_id: str, depth: int = 2) -> Item:
    item = maybe(phenomenon, parent_id, depth)
    assert item is not None
    return item


def maybe(phenomenon: str, parent_id: str, depth: int = 2) -> Item | None:
    parent = next(r for r in ROWS if r["query_id"] == parent_id)
    return build_item(
        phenomenon,
        parent,
        _Index(ROWS, CORPUS),
        CORPUS,
        single_ingredient_leaflets(CORPUS),
        random.Random(0),
        depth,
    )


def test_follow_ups_keep_the_parent_gold_and_hide_the_drug() -> None:
    for phenomenon, last in [
        ("pronoun", "Thuốc này dùng liều thế nào?"),
        ("ellipsis", "Dùng liều thế nào?"),
        ("intent_shift", "Còn liều dùng thì sao?"),
        ("noisy_followup", "con lieu dung thi sao?"),
    ]:
        item = make(phenomenon, "p-dose")
        assert item.turns[-1] == ("user", last)
        assert item.expected_section_ids == (f"{PARA}:lieu-luong-va-cach-dung",)
        # The history names the drug and asks another intent of it.
        assert (
            "PARACETAMOL" in item.turns[0][1]
            and item.turns[0][1] != "PARACETAMOL liều?"
        )
        assert item.turns[1][0] == "assistant"


def test_drug_shift_topic_switch_answer_entity_and_multi_intent() -> None:
    shift = make("drug_shift", "p-dose")
    assert shift.turns[0][1] == "WARFARIN liều?"
    assert shift.turns[-1][1] == "Còn Paracetamol thì sao?"
    switch = make("topic_switch", "p-dose")
    assert (
        switch.turns[-1][1] == "PARACETAMOL liều?" and "WARFARIN" in switch.turns[0][1]
    )
    entity = make("answer_entity", "p-dose")
    assert entity.turns[0][1] == "Panadol 500 mg có thành phần gì?"
    assert "Paracetamol" in entity.turns[1][1]
    assert entity.turns[-1][1] == "Hoạt chất đó dùng liều thế nào?"
    multi = make("multi_intent", "p-multi")
    assert multi.turns[-1][1] == "Cho mình hỏi luôn công dụng và liều dùng?"
    assert len(multi.expected_section_ids) == 2


def test_parents_that_do_not_fit_give_no_item() -> None:
    # A trade-name list is not a section a templated question can ask for.
    assert maybe("pronoun", "p-brand") is None
    assert maybe("multi_intent", "p-dose") is None
    assert maybe("pronoun", "p-multi") is None


def test_answer_text_and_diacritics() -> None:
    assert answer_text(CORPUS, f"{PARA}:lieu-luong-va-cach-dung").startswith(
        "Người lớn uống 500 mg. Tối đa 4 g."
    )
    assert strip_diacritics("Còn Đau đầu thì sao?") == "con dau dau thi sao?"


def test_build_spreads_items_over_the_phenomena_with_benchmark_rows() -> None:
    items = build_conversational(ROWS, CORPUS, total=16, seed=0)
    assert items, "some phenomena fit the tiny corpus"
    assert {i["query_form"] for i in items} <= set(PHENOMENA)
    first = items[0]
    turns = first["turns"]
    assert isinstance(turns, list)
    assert first["query_id"] == f"conv-{first['query_form']}-{first['parent_query_id']}"
    assert first["eval_group"] == "conversational"
    assert first["query"] == turns[-1]["text"]
    assert first["parent_query_id"] in {r["query_id"] for r in ROWS}
    assert "missing" not in first


def test_heading_intents_are_never_asked_by_their_noun_phrase() -> None:
    general = f"{PARA}:thong-tin-chung"
    corpus = CorpusText(
        sections={**SECTIONS, general: f"Paracetamol là thuốc giảm đau. {LONG}"},
        section_documents={**CORPUS.section_documents, general: PARA},
        titles=CORPUS.titles,
    )
    parent = row("p-gen", general, "general_info", "PARACETAMOL là thuốc gì?")
    rows = [*ROWS, parent]

    def build(phenomenon: str) -> Item | None:
        return build_item(
            phenomenon, parent, _Index(rows, corpus), corpus, {}, random.Random(0), 2
        )

    assert build("intent_shift") is None and build("noisy_followup") is None
    pronoun = build("pronoun")
    assert pronoun is not None and pronoun.turns[-1][1] == "Thuốc này là thuốc gì?"


def test_build_takes_only_questions_dedupes_and_marks_the_control() -> None:
    pasted = row(
        "p-pasted",
        f"{PARA}:chi-dinh",
        "indication",
        "Giảm đau, hạ sốt trong các trường hợp đau đầu đau răng",
    )
    items = build_conversational([*ROWS, pasted], CORPUS, total=64, seed=0)
    assert all(i["parent_query_id"] != "p-pasted" for i in items)
    assert all(pasted["query"] not in str(i["turns"]) for i in items)
    keys = [(i["query"], str(i["expected_section_ids"])) for i in items]
    assert len(keys) == len(set(keys))
    for item in items:
        assert ("'control'" in str(item["eval_tags"])) == (
            item["query_form"] == "topic_switch"
        )


def test_history_never_answers_from_the_section_the_last_turn_asks() -> None:
    same = row(
        "p-dose-2",
        f"{PARA}:lieu-luong-va-cach-dung",
        "administration",
        "PARACETAMOL uống mấy lần một ngày?",
    )
    rows = [*ROWS, same]
    parent = ROWS[0]
    for seed in range(20):
        item = build_item(
            "pronoun",
            parent,
            _Index(rows, CORPUS),
            CORPUS,
            {},
            random.Random(seed),
            4,
        )
        assert item is not None
        assert same["query"] not in [text for _, text in item.turns]


def test_items_stay_when_an_unrelated_row_goes() -> None:
    full = build_conversational(ROWS, CORPUS, total=16, seed=0)
    fewer = build_conversational(
        [r for r in ROWS if r["query_id"] != "w-ind"], CORPUS, total=16, seed=0
    )
    untouched = {
        str(i["query_id"]): i
        for i in full
        if "w-ind" not in str(i["turns"])
        and i["parent_query_id"] != "w-ind"
        and "WARFARIN chữa gì?" not in str(i["turns"])
    }
    kept = {str(i["query_id"]): i for i in fewer}
    assert untouched and all(kept.get(q) == i for q, i in untouched.items())


def test_an_excipient_is_not_the_active_ingredient_of_a_leaflet() -> None:
    dut = "leaflet:t:dutaon"
    sections = {
        **SECTIONS,
        f"{dut}:01-thanh-phan": f"Dutasterid 0,5 mg. Tá dược: glycin, gelatin. {LONG}",
        "drug:glycin:than-trong": f"Thận trọng khi dùng glycin. {LONG}",
    }
    corpus = CorpusText(
        sections=sections,
        section_documents={k: k.rsplit(":", 1)[0] for k in sections},
        titles={**CORPUS.titles, dut: "Dutaon 0.5 mg", "drug:glycin": "GLYCIN"},
    )
    assert "drug:glycin" not in single_ingredient_leaflets(corpus)
