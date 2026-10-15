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
        "chunk_id": f"{section['page_id']}:chunk-001",
        "document_id": section["page_id"],
        "ordinal": 1,
        "section_ids": [section["id"]],
        "chunk_text": section["text"],
        "has_table": False,
        "has_list": False,
        "structured_section_ids": [],
    }


def test_schema_has_no_difficulty_and_new_groups() -> None:
    assert "difficulty" not in EVAL_HEADER
    assert {
        "formulary",
        "leaflet",
        "structured",
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
    row = b.make_leaflet_row("q1", first, _chunk(first), "brand_ingredient")
    widened = b.widen_duplicate_text_rows([row], [first, second])
    assert widened[0]["expected_section_ids"] == [first["id"], second["id"]]
    assert widened[0]["answer_mode"] == "any_acceptable"
    assert "any_acceptable" in widened[0]["eval_tags"]


def _page_sections(page: str, title: str, aliases: list[str]) -> list[dict]:
    sections = []
    for index, (heading, body) in enumerate(
        [("Thành phần", "Paracetamol 500 mg."), ("Công dụng (Chỉ định)", "Giảm đau.")],
        start=1,
    ):
        section = _leaflet_section(f"{page}:0{index}-x", title, heading, body)
        section["page_id"] = page
        section["colloquial_mapping"]["aliases"] = aliases
        sections.append(section)
    return sections


def test_alias_is_ambiguous_only_across_pages() -> None:
    red = _page_sections("leaflet:t:panadol-extra", "Panadol Extra", ["Panadol đỏ"])
    blue = _page_sections(
        "leaflet:t:panadol", "Panadol 500 mg", ["Panadol xanh", "Panadol"]
    )
    other = _page_sections("leaflet:t:panadol-cold", "Panadol Cold", ["Panadol"])
    overlap = b.build_colloquial_alias_overlap_index([*red, *blue, *other])
    assert "panadol đỏ" not in overlap
    assert overlap["panadol"]["section_ids"] == [
        "leaflet:t:panadol-cold:02-x",
        "leaflet:t:panadol:02-x",
    ]


def test_brand_product_question_targets_the_indication_section_only() -> None:
    sections = _page_sections("leaflet:t:panadol", "Panadol", [])
    candidates = b.leaflet_candidates(
        {section["id"]: section for section in sections},
        {section["id"]: [_chunk(section)] for section in sections},
    )
    product = [item for item in candidates if item[2] == "brand_product"]
    assert [item[0]["id"] for item in product] == ["leaflet:t:panadol:02-x"]


def test_same_intent_siblings_on_a_page_are_all_accepted() -> None:
    page = "leaflet:t:agi-neurin"
    how = _leaflet_section(f"{page}:04-cach-dung", "Agi-Neurin", "Cách dùng", "Uống.")
    dose = _leaflet_section(
        f"{page}:05-lieu-dung", "Agi-Neurin", "Liều dùng", "1 viên."
    )
    other = _leaflet_section(f"{page}:01-thanh-phan", "Agi-Neurin", "Thành phần", "B1.")
    sections = {s["id"]: {**s, "page_id": page} for s in (how, dose, other)}
    row = b.make_leaflet_row("q1", sections[how["id"]], None, "brand_dosage")
    widened = b.widen_leaflet_intent_siblings([row], sections)
    assert widened[0]["expected_section_ids"] == [how["id"], dose["id"]]
    assert widened[0]["answer_mode"] == "any_acceptable"
    assert "same_intent_sections" in widened[0]["eval_tags"]


def test_short_leaflet_queries_are_unique_per_page_and_intent() -> None:
    from pharma_lab.evaluation.patient_query_generation import (
        build_patient_query_candidates,
    )

    page = "leaflet:t:agi-neurin"
    sections = [
        {
            **_leaflet_section(
                f"{page}:04-cach-dung", "Agi-Neurin", "Cách dùng", "Uống."
            ),
            "page_id": page,
        },
        {
            **_leaflet_section(
                f"{page}:05-lieu-dung", "Agi-Neurin", "Liều dùng", "1 viên."
            ),
            "page_id": page,
        },
    ]
    chunks = [_chunk(section) for section in sections]
    dosage = [
        c
        for c in build_patient_query_candidates(sections, chunks)
        if c.category == "brand_dosage"
    ]
    assert [c.section_id for c in dosage] == [f"{page}:04-cach-dung"]


def test_coverage_question_follows_the_section_intent_not_the_chunk() -> None:
    section = _leaflet_section(
        "leaflet:t:meloxicam:07-tac-dung-phu",
        "Meloxicam Domesco 7.5 mg",
        "Tác dụng phụ",
        "Buồn nôn.",
    )
    later_chunk = {
        **_chunk(section),
        "chunk_text": "Hiếm gặp: phù mạch.",
        "ordinal": 2,
    }
    assert b.auto_query_for_chunk(later_chunk, section, "drug_fact") == (
        "Meloxicam Domesco 7.5 mg có tác dụng phụ nào?"
    )


def test_auto_query_on_a_leaflet_chunk_uses_the_section_intent() -> None:
    section = _leaflet_section(
        "leaflet:t:quincef-125:13-bao-quan", "Quincef 125", "Bảo quản", "Dưới 30 độ C."
    )
    query = b.auto_query_for_chunk(_chunk(section), section, "drug_fact")
    assert query == "Quincef 125 bảo quản ra sao?"


def test_leaflet_sections_without_a_lookup_intent_get_no_generic_question() -> None:
    section = _leaflet_section(
        "leaflet:t:pracetam:12-dac-diem", "Pracetam 400", "Đặc điểm", "Viên nang."
    )
    assert b.auto_query_for_chunk(_chunk(section), section, "drug_fact") == ""


def test_adr_handling_and_usage_guide_headings_have_an_intent() -> None:
    assert b.leaflet_category_for_heading("Hướng dẫn cách xử trí ADR") == "brand_adr"
    assert b.leaflet_category_for_heading("Hướng dẫn sử dụng") == "brand_dosage"


def test_multi_intent_rows_accept_section_category_role_items() -> None:
    def section(slug: str, heading: str) -> dict:
        return {
            "id": f"drug:abacavir:{slug}",
            "content_type": "drug_monograph",
            "title": "ABACAVIR",
            "section": heading,
            "context_path": [heading],
            "text": f"{heading}.",
        }

    items = [
        (section("chi-dinh", "Chỉ định"), "indication", "prose"),
        (
            section("lieu-luong-va-cach-dung", "Liều lượng và cách dùng"),
            "dosage",
            "prose",
        ),
    ]
    rows = b.build_multi_intent_eval_rows(items, {}, target_count=1)
    assert [row["expected_section_ids"] for row in rows] == [
        ["drug:abacavir:chi-dinh", "drug:abacavir:lieu-luong-va-cach-dung"]
    ]


def test_sections_left_out_of_the_bundle_get_no_questions() -> None:
    sections = [{"id": "drug:a:chi-dinh"}, {"id": "drug:a:huong-dan-cach-xu-tri-adr"}]
    chunks = [{"chunk_id": "drug:a:chunk-001", "section_ids": ["drug:a:chi-dinh"]}]
    assert b.sections_in_bundle(sections, chunks) == [{"id": "drug:a:chi-dinh"}]
