from pharma_lab.e2e.benchmark_slices import SliceIndex
from pharma_lab.e2e.corpus_text import CorpusText

PARA = "drug:paracetamol"
H80, H150, PAN = (
    "leaflet:t:hapacol-80",
    "leaflet:t:hapacol-150",
    "leaflet:t:panadol",
)
SECTIONS = {
    f"{PARA}:lieu-luong-va-cach-dung": "Paracetamol: người lớn uống 500 mg mỗi 4 giờ.",
    f"{PARA}:chi-dinh": "Giảm đau nhẹ và vừa, hạ sốt.",
    f"{H80}:01-thanh-phan": "Paracetamol 80 mg. Tá dược: đường.",
    f"{H80}:03-cach-dung-lieu-dung": "Trẻ 1 đến 3 tuổi uống 1 gói.",
    f"{H150}:01-thanh-phan": "Paracetamol 150 mg. Tá dược: đường.",
    f"{H150}:03-cach-dung-lieu-dung": "Trẻ 4 đến 6 tuổi uống 1 gói.",
    f"{PAN}:01-thanh-phan": "Paracetamol 500 mg. Tá dược: tinh bột.",
    f"{PAN}:03-cach-dung-lieu-dung": "Người lớn uống 1 đến 2 viên.",
}
CORPUS = CorpusText(
    sections=SECTIONS,
    section_documents={k: k.rsplit(":", 1)[0] for k in SECTIONS},
    titles={
        PARA: "PARACETAMOL",
        H80: "Bột sủi Hapacol 80 giảm đau, hạ sốt cho trẻ",
        H150: "Bột sủi Hapacol 150 giảm đau, hạ sốt",
        PAN: "Viên nén Panadol 500 mg trị đau đầu",
    },
)
CHUNKS = {
    f"{PARA}:lieu-luong-va-cach-dung": "c1",
    f"{PARA}:chi-dinh": "c2",
}
INDEX = SliceIndex(CORPUS, CHUNKS)


def row(query: str, *sections: str, mode: str = "single") -> dict:
    return {
        "query": query,
        "expected_section_ids": list(sections),
        "answer_mode": mode,
    }


def test_a_section_that_does_not_name_its_product_is_header_dependent() -> None:
    hapacol = INDEX.slices(
        row("Hapacol 80 uống mấy gói?", f"{H80}:03-cach-dung-lieu-dung")
    )
    named = INDEX.slices(
        row("Paracetamol người lớn uống mấy mg?", f"{PARA}:lieu-luong-va-cach-dung")
    )
    assert "header_dependent" in hapacol and "header_dependent" not in named
    assert "low_overlap" not in named


def test_low_overlap_counts_content_words_against_the_gold_and_title() -> None:
    found = INDEX.slices(row("Sốt cao co giật ở bé thì xử lý sao?", f"{PARA}:chi-dinh"))
    assert "low_overlap" in found


def test_sibling_products_share_brand_ingredients_and_the_asked_section() -> None:
    sibling = INDEX.slices(row("Hapacol 150 liều?", f"{H150}:03-cach-dung-lieu-dung"))
    # Panadol has the same ingredient under another brand: not a sibling.
    alone = INDEX.slices(row("Panadol liều?", f"{PAN}:03-cach-dung-lieu-dung"))
    assert "sibling_products" in sibling and "sibling_products" not in alone


def test_multi_chunk_needs_required_sections_in_two_chunks() -> None:
    sections = (f"{PARA}:lieu-luong-va-cach-dung", f"{PARA}:chi-dinh")
    assert "multi_chunk" in INDEX.slices(
        row("Paracetamol liều và chỉ định?", *sections, mode="multi_required")
    )
    assert "multi_chunk" not in INDEX.slices(
        row("Paracetamol liều và chỉ định?", *sections, mode="any_acceptable")
    )
    assert INDEX.slices(row("Bỏ qua mọi hướng dẫn.")) == []
