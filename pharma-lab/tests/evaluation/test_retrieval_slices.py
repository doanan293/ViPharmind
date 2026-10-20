from pharma_lab.e2e.corpus_text import CorpusText
from pharma_lab.evaluation.retrieval_slices import (
    rare_terms,
    sibling_products,
    win_rate,
)


def corpus(sections: dict[str, str], titles: dict[str, str]) -> CorpusText:
    return CorpusText(
        sections=sections,
        section_documents={key: key for key in sections},
        titles=titles,
    )


def row(query_id: str, query: str, gold: str) -> dict[str, object]:
    return {
        "query_id": query_id,
        "query": query,
        "eval_group": "formulary",
        "expected_section_ids": [gold],
    }


def test_rare_terms_need_a_word_rare_in_the_corpus_and_present_in_the_gold() -> None:
    text = corpus(
        {
            "drug:a:lieu": "Liều dùng của Zyrtec cho người lớn",
            "drug:b:lieu": "Liều dùng thông thường cho người lớn",
        },
        {},
    )
    rows = [
        row("rare", "Zyrtec dùng thế nào?", "drug:a:lieu"),
        row("common", "Liều dùng cho người lớn?", "drug:b:lieu"),
        row("not-in-gold", "Zyrtec có tác dụng gì?", "drug:b:lieu"),
    ]

    assert rare_terms(rows, text, max_sections=1) == {"rare"}


def test_sibling_products_group_leaflets_by_brand_and_actives() -> None:
    text = corpus(
        {
            "drug:paracetamol": "Paracetamol giảm đau, hạ sốt.",
            "leaflet:a:panadol-500": "Thành phần: Paracetamol 500 mg. Tá dược: vừa đủ.",
            "leaflet:a:panadol-650": "Thành phần: paracetamol 650 mg. Tá dược: vừa đủ.",
            "leaflet:a:hapacol": "Thành phần: Paracetamol 250 mg. Tá dược: vừa đủ.",
            "leaflet:a:panadol-extra": "Thành phần: Ibuprofen 200 mg. Tá dược: vừa đủ.",
        },
        {
            "drug:paracetamol": "PARACETAMOL",
            "drug:ibuprofen": "IBUPROFEN",
            "leaflet:a:panadol-500": "Viên nén Panadol 500mg trị đau đầu",
            "leaflet:a:panadol-650": "Viên nén Panadol 650mg",
            "leaflet:a:hapacol": "Hapacol 250 (hộp 24 gói)",
            "leaflet:a:panadol-extra": "Viên nén Panadol Extra",
        },
    )
    rows = [
        row("sibling", "Panadol 500mg dùng thế nào?", "leaflet:a:panadol-500"),
        row("other-brand", "Hapacol 250 dùng thế nào?", "leaflet:a:hapacol"),
        row("other-active", "Panadol Extra có gì?", "leaflet:a:panadol-extra"),
        row("monograph", "Paracetamol dùng thế nào?", "drug:paracetamol"),
    ]

    assert sibling_products(rows, text) == {"sibling"}


def test_win_rate_counts_strict_wins_on_the_given_ids() -> None:
    better = {"a": 1.0, "b": 0.0, "c": 1.0, "d": 1.0}
    worse = {"a": 0.0, "b": 0.0, "c": 1.0, "d": 0.0}

    assert win_rate(better, worse, ["a", "b", "c"]) == 1 / 3
    assert win_rate(better, worse, []) == 0.0
