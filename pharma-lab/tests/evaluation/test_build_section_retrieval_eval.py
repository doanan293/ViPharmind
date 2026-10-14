from pharma_lab.evaluation import build_section_retrieval_eval as b
from pharma_lab.evaluation.section_eval_schema import (
    ALLOWED_EVAL_GROUPS,
    ALLOWED_INTENT_CATEGORIES,
    ALLOWED_QUERY_FORMS,
    EVAL_HEADER,
    FORMULARY_CATEGORY_MAP,
)

TITLE = "Fordia 850 mg trị đái tháo đường type 2 kết hợp ăn kiêng (10 vỉ x 10 viên)"


def _leaflet_section(key: str, title: str, heading: str, text: str) -> dict:
    return {
        "id": key,
        "page_id": key.rsplit(":", 1)[0],
        "content_type": "brand_page",
        "title": title,
        "section": heading,
        "text": f"# {title}\n\n### 3. {heading}\n\n{text}",
        "context_path": [heading],
        "colloquial_mapping": {"product_names": [title, title.split(" trị ")[0]]},
        "hydrate_strategy": "full_section",
        "section_char_count": 120,
    }


def _chunk(section: dict) -> dict:
    return {
        "chunk_id": f"{section['id']}:chunk-001",
        "chunk_text": section["text"],
        "section_id": section["id"],
        "chunk_index": 1,
    }


def test_schema_has_no_difficulty_and_new_groups() -> None:
    assert "difficulty" not in EVAL_HEADER
    assert {
        "formulary",
        "leaflet",
        "chunk_risk",
        "leaflet_short",
        "noisy",
        "multi_intent",
    } == ALLOWED_EVAL_GROUPS
    assert "confuser" not in ALLOWED_QUERY_FORMS
    assert "typo" in ALLOWED_QUERY_FORMS
    assert "overdose" in ALLOWED_INTENT_CATEGORIES
    assert FORMULARY_CATEGORY_MAP["overdose"] == ("overdose", "formulary_overdose")
    assert FORMULARY_CATEGORY_MAP["storage"] == ("storage", "formulary_storage")


def test_unique_query_returns_none_instead_of_appending_a_label() -> None:
    seen = {"liều abacavir?"}
    assert b.unique_query("Liều abacavir?", seen) is None
    assert b.unique_query("Liều acarbose?", seen) == "Liều acarbose?"


def test_leaflet_queries_use_short_product_name_and_no_hint() -> None:
    section = _leaflet_section(
        "leaflet:tieu-duong:fordia-850:03-cach-dung-lieu-dung",
        TITLE,
        "Cách dùng - Liều dùng",
        "Người lớn 1 viên x 2 lần/ngày.",
    )
    assert b.display_product_name(section) == "Fordia 850 mg"
    query, _style = b.leaflet_query_for_category(section, "brand_dosage")
    assert query == "Fordia 850 mg dùng liều thế nào?"
    chunk = _chunk(section)
    assert "(phần" not in b.auto_query_for_chunk(chunk, section, "brand_dosage")
    row = b.make_leaflet_row("q1", section, chunk, "brand_dosage")
    assert "(" not in row["query"]
    assert "difficulty" not in row


def test_typo_query_is_deterministic_and_keeps_numbers() -> None:
    query = "Paracetamol 500 mg uống tối đa bao nhiêu viên mỗi ngày?"
    first = b.typo_query(query, seed=7)
    assert first == b.typo_query(query, seed=7)
    assert first != query
    assert "500 mg" in first


def test_brand_lookup_templates_name_the_brand() -> None:
    for templates in (
        b.PARAPHRASE_TEMPLATES,
        b.NATURAL_TEMPLATES,
        b.CLINICAL_TEMPLATES,
    ):
        for template in templates["brand_lookup"]:
            assert "{brand}" in template


def test_duplicate_chunk_text_widens_expected_sections() -> None:
    first = _leaflet_section(
        "leaflet:t:jardiance-10:01-thanh-phan", "Jardiance 10 mg", "Thành phần", "E."
    )
    second = _leaflet_section(
        "leaflet:t:jardiance-25:01-thanh-phan", "Jardiance 25 mg", "Thành phần", "E."
    )
    chunks = [
        {**_chunk(first), "chunk_text": "Empagliflozin."},
        {**_chunk(second), "chunk_text": "Empagliflozin."},
    ]
    row = b.make_leaflet_row("q1", first, chunks[0], "brand_ingredient")
    widened = b.widen_duplicate_text_rows([row], chunks)
    assert widened[0]["expected_section_ids"] == [first["id"], second["id"]]
    assert widened[0]["answer_mode"] == "any_acceptable"
    assert "duplicate_text" in widened[0]["eval_tags"]
