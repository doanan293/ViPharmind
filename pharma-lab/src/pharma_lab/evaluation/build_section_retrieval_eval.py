import json
import random
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from pharma_lab.config.paths import (
    EVALUATION_CHUNKS_PATH,
    GOLD_DIR,
    RAG_FINAL_DIR,
)
from pharma_lab.corpus.metadata.payload_layers import compact_colloquial_mapping
from pharma_lab.evaluation.section_eval_schema import (
    ALLOWED_ANSWER_MODES,
    ALLOWED_EVAL_GROUPS,
    ALLOWED_INTENT_CATEGORIES,
    ALLOWED_QUERY_FORMS,
    ALLOWED_RETRIEVAL_GRANULARITIES,
    ALLOWED_SOURCE_FAMILIES,
    DEFAULT_EVAL_GROUP_QUOTAS,
    DEFAULT_MAX_ROWS,
    DEFAULT_MIN_ROWS,
    DEFAULT_TARGET_ROWS,
    EVAL_HEADER,
    FORMULARY_QUERY_FORM_TARGETS,
    LEAFLET_ALIAS_ANSWER_MODE_TARGETS,
    LEAFLET_QUERY_FORM_TARGETS,
    NOISY_QUERY_FORM_TARGETS,
    answer_mode_for_expected_ids,
    clean_query_label,
    normalize_eval_tags,
    retrieval_granularity_from_hydrate_strategy,
    source_family_for_section,
    taxonomy_for_source_category,
)

DEFAULT_SECTIONS_PATH = RAG_FINAL_DIR / "sections.jsonl"
DEFAULT_CHUNKS_PATH = EVALUATION_CHUNKS_PATH
DEFAULT_OUTPUT_PATH = GOLD_DIR / "section_retrieval_eval.jsonl"

SECTION_CATEGORY_RULES = [
    ("contraindication", ("chống chỉ định",), "easy", "prose"),
    ("indication", ("chỉ định",), "easy", "prose"),
    ("dosage", ("liều lượng", "cách dùng"), "medium", "prose"),
    ("adr", ("tác dụng không mong muốn", "tác dụng phụ", "adr"), "medium", "prose"),
    ("interaction", ("tương tác",), "medium", "prose"),
    ("pregnancy", ("mang thai", "cho con bú", "thời kỳ mang thai"), "medium", "prose"),
    ("overdose", ("quá liều", "xử trí", "ngộ độc"), "medium", "prose"),
    ("storage", ("bảo quản", "độ ổn định", "hạn dùng"), "medium", "prose"),
    ("precaution", ("thận trọng", "cảnh báo", "lưu ý"), "medium", "prose"),
    (
        "pharmacology",
        ("dược lý", "cơ chế tác dụng", "dược lực học", "dược động học"),
        "medium",
        "prose",
    ),
    ("dosage_form", ("dạng thuốc", "hàm lượng", "chế phẩm"), "medium", "prose"),
    (
        "general_guidance",
        ("kê đơn", "người cao tuổi", "sử dụng thuốc"),
        "medium",
        "prose",
    ),
    ("atc_appendix", ("atc", "phân loại thuốc"), "hard", "appendix_list"),
    (
        "brand_lookup",
        ("biệt dược", "tên thương mại", "tên chung quốc tế"),
        "medium",
        "index_entry",
    ),
]

LEAFLET_CATEGORY_RULES = [
    ("brand_ingredient", ("thành phần",)),
    ("brand_contraindication", ("chống chỉ định",)),
    ("brand_indication", ("công dụng", "chỉ định")),
    (
        "brand_dosage",
        (
            "cách dùng",
            "liều dùng",
            "cách dùng - liều dùng",
            "cách dùng -liều dùng",
            "hướng dẫn sử dụng",
        ),
    ),
    ("brand_adr", ("tác dụng phụ", "xử trí adr")),
    (
        "brand_precaution",
        ("lưu ý", "thận trọng", "thai kỳ", "cho con bú", "lái xe", "vận hành máy móc"),
    ),
    ("brand_interaction", ("tương tác thuốc",)),
    ("brand_pharmacology", ("dược lý", "dược lực học", "dược động học")),
    ("brand_storage", ("bảo quản", "hạn dùng", "hạn sử dụng")),
    ("brand_manufacturer", ("nhà sản xuất", "thương hiệu", "quy cách đóng gói")),
]

LEAFLET_CATEGORY_PRIORITY = [
    "brand_dosage",
    "brand_indication",
    "brand_ingredient",
    "brand_contraindication",
    "brand_adr",
    "brand_precaution",
    "brand_interaction",
    "brand_storage",
    "brand_pharmacology",
    "brand_manufacturer",
    "brand_product",
]


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} is not valid JSON") from exc
    return records


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_heading(value: str) -> str:
    cleaned = normalize_spaces(value).lower()
    cleaned = re.sub(r"^[-–—]\s*", "", cleaned)
    cleaned = re.sub(r"^\d+\.\s*", "", cleaned)
    return cleaned.strip()


def markdown_headings(text: str) -> list[str]:
    headings = []
    for match in re.finditer(r"(?m)^#{2,4}\s+(.+?)\s*$", text or ""):
        headings.append(normalize_heading(match.group(1)))
    return headings


def infer_leaflet_category(text: str) -> str:
    headings = markdown_headings(text)
    haystack = " ".join(headings) if headings else normalize_heading(text[:240])
    for category, keywords in LEAFLET_CATEGORY_RULES:
        if any(keyword in haystack for keyword in keywords):
            return category
    return "brand_product"


def leaflet_category_for_heading(heading: str) -> str:
    normalized = normalize_heading(heading)
    for category, keywords in LEAFLET_CATEGORY_RULES:
        if any(keyword in normalized for keyword in keywords):
            return category
    return ""


def leaflet_categories_for_text(text: str) -> list[str]:
    categories: list[str] = []
    for heading in markdown_headings(text):
        category = leaflet_category_for_heading(heading)
        if category and category not in categories:
            categories.append(category)
    if categories:
        return categories

    fallback = infer_leaflet_category(text)
    return [fallback] if fallback else ["brand_product"]


def leaflet_label_for_category(text: str, category: str) -> str:
    if category == "brand_product":
        return ""
    for heading in markdown_headings(text):
        if leaflet_category_for_heading(heading) == category:
            return clean_query_label(heading)
    return chunk_context_label({"chunk_text": text})


def section_label(section: dict) -> str:
    title = normalize_spaces(section.get("title", ""))
    section_name = normalize_spaces(section.get("section", ""))
    if section_name and section_name.lower() != "nội dung":
        return f"{title} - {section_name}"
    return title


def extract_section_entity_anchors(section: dict, chunks: list[dict]) -> list[str]:
    candidates = []
    title = normalize_spaces(section.get("title", ""))
    if title:
        candidates.append(title)

    def add_from_record(rec: dict):
        mapping = colloquial_mapping_for_record(rec)
        candidates.extend(mapping.get("product_names") or [])
        candidates.extend(mapping.get("aliases") or [])
        for key in ("colloquial_names", "product_aliases", "aliases", "product_names"):
            val = rec.get(key)
            if isinstance(val, list):
                candidates.extend(val)
            elif isinstance(val, str) and val:
                candidates.append(val)

    add_from_record(section)
    for chunk in chunks:
        add_from_record(chunk)

    deduped = []
    for c in candidates:
        cleaned = normalize_spaces(c)
        if cleaned and len(cleaned) >= 3 and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped if deduped else [title]


def build_hybrid_entity_intent_query(
    section: dict, category: str, anchors: list[str]
) -> str:
    anchor = anchors[0] if anchors else normalize_spaces(section.get("title", ""))
    category_templates = {
        "contraindication": f"Chống chỉ định và lưu ý khi sử dụng {anchor}",
        "indication": f"Thuốc {anchor} chỉ định điều trị bệnh gì",
        "dosage": f"Liều dùng và cách dùng chuẩn của {anchor}",
        "adr": f"Tác dụng phụ không mong muốn của {anchor}",
        "interaction": f"Tương tác thuốc và cẩn trọng khi dùng {anchor}",
        "pregnancy": f"Sử dụng {anchor} cho phụ nữ mang thai và cho con bú",
        "brand_ingredient": f"Thành phần hoạt chất chính của {anchor}",
        "brand_storage": f"Hướng dẫn bảo quản và hạn dùng {anchor}",
    }
    return category_templates.get(category, f"Thông tin chi tiết về {anchor}")


def chunk_role_for_section(
    section_id: str, chunks_by_section: dict[str, list[dict]]
) -> str:
    roles = [
        chunk.get("chunk_role", "")
        for chunk in chunks_by_section.get(section_id, [])
        if chunk.get("chunk_role")
    ]
    if not roles:
        return ""
    return sorted(set(roles))[0]


def category_for_section(section: dict, chunks: list[dict]) -> tuple[str, str, str]:
    haystack = " ".join(
        [
            section.get("id", ""),
            section.get("title", ""),
            section.get("section", ""),
            " ".join(section.get("context_path", []) or []),
            section.get("context_header", ""),
        ]
    ).lower()
    for category, keywords, difficulty, expected_role in SECTION_CATEGORY_RULES:
        if any(keyword in haystack for keyword in keywords):
            return category, difficulty, expected_role
    if any(chunk.get("chunk_content_type") == "table" for chunk in chunks):
        return "table_lookup", "hard", "table"
    sid = section.get("id", "")
    if section.get("content_type") == "general_monograph":
        return (
            "general_guidance",
            "medium",
            chunk_role_for_section(sid, {sid: chunks}) if sid else "prose",
        )
    return (
        "drug_fact",
        "medium",
        chunk_role_for_section(sid, {sid: chunks}) if sid else "prose",
    )


def make_row(
    query_id: str,
    query: str,
    eval_group: str,
    source_family: str,
    query_form: str,
    intent_category: str,
    source_subcategory: str,
    section: dict,
    expected_chunk_role: str,
    notes: str,
    expected_section_ids: list[str] | None = None,
    answer_mode: str = "single",
    expected_chunk_id: str = "",
    expected_chunk_index: int = -1,
    retrieval_granularity: str = "section",
    eval_tags: list[str] | set[str] | tuple[str, ...] = (),
) -> dict:
    all_expected_ids = expected_section_ids or [section["id"]]
    base_tags = {
        eval_group,
        source_family,
        query_form,
        intent_category,
        source_subcategory,
    }
    base_tags.update(eval_tags)
    return {
        "query_id": query_id,
        "query": normalize_spaces(query),
        "eval_group": eval_group,
        "source_family": source_family,
        "query_form": query_form,
        "intent_category": intent_category,
        "source_subcategory": source_subcategory,
        "expected_section_id": section["id"],
        "expected_section_ids": all_expected_ids,
        "query_intent_count": len(all_expected_ids),
        "answer_mode": answer_mode,
        "expected_title": section_label(section),
        "expected_chunk_id": expected_chunk_id,
        "expected_chunk_index": (
            expected_chunk_index if expected_chunk_index is not None else None
        ),
        "expected_chunk_role": expected_chunk_role,
        "retrieval_granularity": retrieval_granularity,
        "eval_tags": normalize_eval_tags(base_tags),
        "notes": notes,
    }


def unique_query(query: str, seen_queries: set[str]) -> str | None:
    """A question already used for another section drops the candidate; no label is appended."""
    normalized = normalize_spaces(query)
    if not normalized or normalized.lower() in seen_queries:
        return None
    return normalized


def curated_query_for_section(section: dict, category: str) -> str:
    title = normalize_spaces(section.get("title", ""))
    section_name = normalize_spaces(section.get("section", ""))
    if category == "indication":
        return f"{title} được chỉ định trong những trường hợp nào?"
    if category == "contraindication":
        return f"Khi nào không được dùng {title}?"
    if category == "dosage":
        return f"Liều lượng và cách dùng {title} như thế nào?"
    if category == "adr":
        return f"{title} có những tác dụng không mong muốn nào?"
    if category == "interaction":
        return f"{title} có tương tác thuốc cần lưu ý gì?"
    if category == "pregnancy":
        return f"Cần lưu ý gì khi dùng {title} trong thời kỳ {section_name.lower()}?"
    if category == "overdose":
        return f"Cách xử trí khi dùng quá liều thuốc {title} là gì?"
    if category == "storage":
        return f"Hướng dẫn bảo quản và hạn dùng của {title} như thế nào?"
    if category == "precaution":
        return f"Những điều cần thận trọng khi sử dụng {title} là gì?"
    if category == "pharmacology":
        return f"Dược lý và cơ chế tác dụng của thuốc {title} như thế nào?"
    if category == "dosage_form":
        return f"Các dạng thuốc và hàm lượng thương mại của {title} là gì?"
    if category == "brand_lookup":
        return f"{title} có những tên biệt dược nào?"
    if category == "atc_appendix":
        return "Tra cứu phân loại thuốc theo mã ATC"
    if category == "table_lookup":
        return f"Tìm bảng thông tin liên quan đến {section_label(section)}"
    return f"Nội dung chính của mục {section_label(section)} là gì?"


PARAPHRASE_TEMPLATES = {
    "indication": [
        "{title} dùng để điều trị gì?",
        "{title} thường được dùng trong bệnh hoặc tình trạng nào?",
        "Trường hợp nào có thể cần dùng {title}?",
    ],
    "contraindication": [
        "Ai không nên dùng {title}?",
        "Trường hợp nào cần tránh {title}?",
        "{title} bị chống dùng trong những tình huống nào?",
    ],
    "dosage": [
        "{title} dùng liều ra sao?",
        "Cách sử dụng {title} thế nào?",
        "Dùng {title} bao nhiêu và dùng như thế nào?",
    ],
    "adr": [
        "{title} có tác dụng phụ gì?",
        "Dùng {title} có thể gặp phản ứng bất lợi nào?",
        "Các biểu hiện không mong muốn khi dùng {title} là gì?",
    ],
    "interaction": [
        "{title} có kỵ với thuốc nào không?",
        "Khi phối hợp {title} cần lưu ý tương tác gì?",
        "{title} dùng chung với thuốc khác có vấn đề gì?",
    ],
    "pregnancy": [
        "Bà bầu hoặc mẹ cho con bú dùng {title} có an toàn không?",
        "{title} có dùng được khi mang thai hoặc cho con bú không?",
        "Cần cân nhắc gì với {title} ở phụ nữ có thai hoặc đang nuôi con bú?",
    ],
    "overdose": [
        "Trường hợp sử dụng quá liều {title} xử lý ra sao?",
        "Cách xử trí ngộ độc và quá liều thuốc {title} là gì?",
        "Dùng quá liều {title} thì cần cấp cứu như thế nào?",
    ],
    "storage": [
        "Điều kiện bảo quản chuẩn của {title} là gì?",
        "Hướng dẫn giữ gìn và bảo quản thuốc {title} đúng cách?",
        "Hạn dùng và yêu cầu nhiệt độ bảo quản {title} ra sao?",
    ],
    "precaution": [
        "Lưu ý quan trọng trước khi dùng {title} gồm những gì?",
        "Những điều cần thận trọng khi sử dụng {title} là gì?",
        "Cần cảnh báo những vấn đề gì khi kê đơn {title}?",
    ],
    "pharmacology": [
        "Thuốc {title} tác động vào cơ thể theo cơ chế dược lý nào?",
        "Dược lý và dược lực học của {title} ra sao?",
        "Cơ chế tác dụng của thuốc {title} diễn ra như thế nào?",
    ],
    "dosage_form": [
        "Dạng đóng gói và hàm lượng phổ biến của {title} là gì?",
        "Các dạng chế phẩm bào chế của {title} gồm những gì?",
        "Nồng độ và hàm lượng thương mại của {title} ra sao?",
    ],
    "brand_lookup": [
        "{brand} là biệt dược của hoạt chất nào?",
        "{brand} chứa hoạt chất gì?",
        "Thuốc {brand} tương ứng với hoạt chất nào trong Dược thư?",
    ],
    "atc_appendix": [
        "Tra mã ATC của nhóm thuốc này",
        "Tìm phân loại ATC cho thuốc",
        "Thuốc này thuộc nhóm ATC nào?",
    ],
    "table_lookup": [
        "Tra thông tin trong bảng của {label}",
        "Bảng ở mục {label} có dữ liệu gì?",
        "Tìm số liệu hoặc hàng trong bảng liên quan đến {label}",
    ],
    "general_guidance": [
        "Hướng dẫn chung về {label} là gì?",
        "Quy định cần nhớ trong mục {label}",
        "Tìm khuyến cáo thực hành về {label}",
    ],
    "drug_fact": [
        "{title} là thuốc gì?",
        "Tìm thông tin tổng quan về {title}",
        "{title} có thông tin dược thư nào cần biết?",
    ],
}

NATURAL_TEMPLATES = {
    "indication": [
        "thuốc {title} dùng chữa gì?",
        "{title} dùng cho bệnh gì vậy?",
    ],
    "contraindication": [
        "ai nên tránh {title}?",
        "{title} có trường hợp nào không được uống không?",
    ],
    "dosage": [
        "{title} uống như nào?",
        "liều {title} thường dùng là bao nhiêu?",
    ],
    "adr": [
        "{title} có gây tác dụng phụ không?",
        "uống {title} có thể bị vấn đề gì?",
    ],
    "interaction": [
        "{title} có dùng chung thuốc khác được không?",
        "{title} có kỵ thuốc nào không?",
    ],
    "pregnancy": [
        "có bầu dùng {title} được không?",
        "đang cho con bú dùng {title} có sao không?",
    ],
    "overdose": [
        "uống quá liều {title} phải làm sao?",
        "cách xử trí khi quá liều {title} là gì?",
    ],
    "storage": [
        "bảo quản {title} thế nào cho đúng?",
        "thuốc {title} để ngoài trời có hỏng không?",
    ],
    "precaution": [
        "dùng {title} cần chú ý gì không?",
        "những ai phải cẩn thận khi dùng {title}?",
    ],
    "pharmacology": [
        "cơ chế tác dụng của {title} là gì?",
        "{title} hoạt động trong cơ thể thế nào?",
    ],
    "dosage_form": [
        "{title} có những hàm lượng nào?",
        "{title} dạng viên hay dạng tiêm?",
    ],
    "brand_lookup": [
        "{brand} là thuốc gì vậy?",
        "xem giúp {brand} chứa hoạt chất gì",
    ],
    "atc_appendix": [
        "xem mã ATC của thuốc này",
        "thuốc này nằm nhóm ATC nào?",
    ],
    "table_lookup": [
        "tìm trong bảng phần {label}",
        "xem bảng liên quan đến {label}",
    ],
    "general_guidance": [
        "tôi cần hướng dẫn về {label}",
        "xem giúp quy định trong {label}",
    ],
    "drug_fact": [
        "cho tôi thông tin về {title}",
        "{title} là thuốc như thế nào?",
    ],
}

CLINICAL_TEMPLATES = {
    "indication": [
        "Bệnh nhân đang có triệu chứng cần điều trị, khi nào cân nhắc dùng {title}?",
        "Trong thực hành lâm sàng, {title} phù hợp cho tình trạng nào?",
    ],
    "contraindication": [
        "Bệnh nhân có tiền sử dị ứng hoặc bệnh nền nào thì cần tránh {title}?",
        "Trước khi kê {title}, cần loại trừ chống chỉ định nào?",
    ],
    "dosage": [
        "Bệnh nhân cần dùng {title}, nên tra liều và cách dùng ở đâu?",
        "Khi kê {title}, liều dùng và cách sử dụng cần kiểm tra thế nào?",
    ],
    "adr": [
        "Sau khi dùng {title}, bệnh nhân có biểu hiện bất thường nào cần nghĩ tới ADR?",
        "Theo dõi tác dụng phụ nào khi người bệnh dùng {title}?",
    ],
    "interaction": [
        "Bệnh nhân đang dùng nhiều thuốc, {title} có tương tác gì cần kiểm tra?",
        "Khi phối hợp thuốc với {title}, cần thận trọng nguy cơ tương tác nào?",
    ],
    "pregnancy": [
        "Đánh giá yếu tố nguy cơ khi kê {title} cho phụ nữ mang thai hoặc nuôi con nhỏ?",
        "Thực hành lâm sàng cần chú ý gì về độc tính của {title} trên thai kỳ?",
        "Người bệnh đang mang thai hoặc cho con bú có dùng {title} được không?",
        "Tư vấn gì nếu phụ nữ có thai hỏi về {title}?",
    ],
    "overdose": [
        "Bệnh nhân nhập viện do quá liều {title}, phác đồ xử trí ngộ độc như thế nào?",
        "Triệu chứng ngộ độc cấp {title} và hướng xử trí lâm sàng?",
    ],
    "storage": [
        "Điều kiện bảo quản và độ ổn định của chế phẩm {title} trong cơ sở y tế?",
        "Yêu cầu về môi trường và nhiệt độ lưu trữ thuốc {title}?",
    ],
    "precaution": [
        "Cần cảnh báo và theo dõi những chỉ số lâm sàng gì khi dùng {title}?",
        "Khuyên người bệnh những điều cần cẩn trọng gì khi kê {title}?",
    ],
    "pharmacology": [
        "Đặc điểm dược lý, dược lực học và dược động học của {title}?",
        "Cơ chế phân bố và chuyển hóa của {title} trong lâm sàng?",
    ],
    "dosage_form": [
        "Các dạng bào chế và nồng độ hàm lượng chuẩn của {title} trong điều trị?",
        "Chế phẩm {title} có những hàm lượng kê đơn nào?",
    ],
    "brand_lookup": [
        "Người bệnh đang dùng {brand}, hoạt chất của thuốc này là gì?",
        "Biệt dược {brand} có hoạt chất gốc là gì?",
    ],
    "atc_appendix": [
        "Cần phân nhóm thuốc theo ATC để báo cáo, tra ở mục nào?",
        "Khi cần mã ATC của thuốc, nên tìm phần nào trong Dược thư?",
    ],
    "table_lookup": [
        "Cần đối chiếu dữ liệu dạng bảng trong {label}",
        "Thông tin bảng liên quan {label} cần được tra ở đâu?",
    ],
    "general_guidance": [
        "Trong thực hành, cần xem hướng dẫn chung về {label}",
        "Khi xử trí ca bệnh, quy định trong {label} cần tra thế nào?",
    ],
    "drug_fact": [
        "Cần tra thông tin dược thư tổng quát về {title} cho ca bệnh",
        "Bệnh nhân hỏi về {title}, cần xem chuyên luận nào?",
    ],
}


LEAFLET_QUERY_TEMPLATES = {
    "brand_product": ("{title} là thuốc gì?", "brand_product"),
    "brand_ingredient": ("{title} có thành phần gì?", "brand_ingredient"),
    "brand_indication": ("{title} dùng để làm gì?", "brand_indication"),
    "brand_dosage": ("{title} dùng liều thế nào?", "brand_dosage"),
    "brand_contraindication": ("{title} có chống chỉ định gì?", "brand_safety"),
    "brand_adr": ("{title} có tác dụng phụ nào?", "brand_safety"),
    "brand_precaution": ("Khi dùng {title} cần lưu ý gì?", "brand_safety"),
    "brand_interaction": ("{title} có tương tác thuốc gì?", "brand_safety"),
    "brand_pharmacology": ("Dược lý của {title} là gì?", "brand_product"),
    "brand_storage": ("{title} bảo quản ra sao?", "brand_storage"),
    "brand_manufacturer": ("{title} của hãng nào?", "brand_product"),
}

COLLOQUIAL_ALIAS_QUERY_TEMPLATES = {
    "brand_product": "{alias} là thuốc gì?",
    "brand_ingredient": "{alias} có thành phần gì?",
    "brand_indication": "{alias} dùng để làm gì?",
    "brand_dosage": "{alias} dùng liều thế nào?",
    "brand_contraindication": "{alias} có chống chỉ định gì?",
    "brand_adr": "{alias} có tác dụng phụ nào?",
    "brand_precaution": "Khi dùng {alias} cần lưu ý gì?",
    "brand_interaction": "{alias} có tương tác thuốc gì?",
    "brand_pharmacology": "Dược lý của {alias} là gì?",
    "brand_storage": "{alias} bảo quản ra sao?",
    "brand_manufacturer": "{alias} của hãng nào?",
}


FRIENDLY_ALIASES = {
    "VẮC XIN HAEMOPHILUS INFLUENZAE TYP B CỘNG HỢP": [
        "vắc-xin Hib",
        "vắc-xin viêm màng não do Hib",
        "mũi tiêm Hib",
    ],
    "CÁC CHẤT ỨC CHẾ HMG-CoA REDUCTASE": [
        "thuốc statin",
        "thuốc hạ mỡ máu nhóm statin",
    ],
    "SẮT DEXTRAN": ["sắt tiêm", "thuốc sắt dextran"],
    "ACID ACETYLSALICYLIC": ["Aspirin"],
}


def extract_brand_names(sections: list[dict]) -> dict[str, list[str]]:
    brand_names_by_title = {}
    for section in sections:
        if section.get("section") == "Tên thương mại" and section.get("title"):
            title = normalize_spaces(section["title"])
            text = section.get("text", "")
            if not text:
                continue
            names = []
            for part in re.split(r"[;,]", text):
                clean_name = part.strip().strip(".")
                if clean_name and clean_name.lower() != title.lower():
                    names.append(clean_name)
            if names:
                brand_names_by_title[title] = names
    return brand_names_by_title


def styled_query_for_section(
    section: dict,
    category: str,
    query_style: str,
    variant_index: int,
    brand_names: list[str] | None = None,
    aliases: list[str] | None = None,
) -> str:
    if query_style == "template":
        return curated_query_for_section(section, category)
    if category == "brand_lookup" and not brand_names:
        return ""
    if query_style == "paraphrase":
        templates = PARAPHRASE_TEMPLATES
    elif query_style == "clinical":
        templates = CLINICAL_TEMPLATES
    else:
        templates = NATURAL_TEMPLATES
    options = templates.get(category) or templates["drug_fact"]

    title = normalize_spaces(section.get("title", ""))
    if query_style in ("natural", "clinical", "noisy", "typo") and aliases:
        title = aliases[variant_index % len(aliases)]
    brand = brand_names[variant_index % len(brand_names)] if brand_names else title

    label = section_label(section)
    query = options[variant_index % len(options)].format(
        title=title, label=label, brand=brand
    )
    if query_style == "noisy":
        return noisy_query(query)
    if query_style == "typo":
        return typo_query(query, seed=variant_index)
    return query


def strip_vietnamese_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    without_marks = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    return without_marks.replace("đ", "d").replace("Đ", "D")


def noisy_query(query: str) -> str:
    noisy = strip_vietnamese_accents(query).lower()
    replacements = {
        " nhu the nao": " ntn",
        " nhu nao": " ntn",
        " tac dung phu": " tdp",
        " chong chi dinh": " ccd",
        " mang thai": " bau",
        " lieu luong": " lieu",
        " tuong tac": " tt",
    }
    for source, target in replacements.items():
        noisy = noisy.replace(source, target)
    return normalize_spaces(noisy)


_TYPO_PROTECTED = re.compile(r"\d|mg|ml|mcg|iu|%")


def typo_query(query: str, seed: int) -> str:
    """One or two typing slips (swap, drop, double a letter) on long words; numbers and units stay."""
    rng = random.Random(seed)
    words = query.split()
    candidates = [
        index
        for index, word in enumerate(words)
        if len(word) >= 5 and not _TYPO_PROTECTED.search(word.lower())
    ]
    if not candidates:
        return query
    for index in rng.sample(candidates, k=min(2, len(candidates))):
        word = words[index]
        position = rng.randrange(1, len(word) - 1)
        kind = rng.choice(("swap", "drop", "double"))
        if kind == "swap":
            word = (
                word[: position - 1]
                + word[position]
                + word[position - 1]
                + word[position + 1 :]
            )
        elif kind == "drop":
            word = word[:position] + word[position + 1 :]
        else:
            word = word[: position + 1] + word[position] + word[position + 1 :]
        words[index] = word
    return " ".join(words)


def widen_duplicate_text_rows(rows: list[dict], chunks: list[dict]) -> list[dict]:
    """A gold chunk whose text also exists in another section (same drug, other strength)
    makes that section acceptable too."""
    owners: dict[str, set[str]] = defaultdict(set)
    text_by_chunk: dict[str, str] = {}
    for chunk in chunks:
        key = normalize_spaces(chunk_body_text(chunk)).lower()
        if not key:
            continue
        owners[key].add(str(chunk.get("section_id")))
        text_by_chunk[chunk_identifier(chunk)] = key
    for row in rows:
        chunk_id = row.get("expected_chunk_id") or ""
        if not chunk_id or row.get("answer_mode") != "single":
            continue
        primary = row["expected_section_id"]
        others = sorted(owners.get(text_by_chunk.get(chunk_id, ""), set()) - {primary})
        if not others:
            continue
        row["expected_section_ids"] = [primary, *others]
        row["query_intent_count"] = len(row["expected_section_ids"])
        row["answer_mode"] = "any_acceptable"
        row["eval_tags"] = [*row.get("eval_tags", []), "duplicate_text"]
    return rows


def leaflet_intent(section: dict) -> str:
    categories = [
        category
        for category in leaflet_categories_for_text(section.get("text", ""))
        if category != "brand_product"
    ]
    return categories[0] if categories else ""


def widen_leaflet_intent_siblings(
    rows: list[dict], sections_by_id: dict[str, dict]
) -> list[dict]:
    """A generic leaflet question ("X dùng liều thế nào?") is answered by every section
    of that page with the same intent (Cách dùng and Liều dùng), so all are accepted."""
    siblings: dict[tuple[str, str], list[str]] = defaultdict(list)
    for section_id, section in sorted(sections_by_id.items()):
        intent = leaflet_intent(section) if is_leaflet_section(section) else ""
        if intent:
            siblings[(leaflet_page_id(section), intent)].append(section_id)
    for row in rows:
        primary = sections_by_id.get(row["expected_section_id"])
        if (
            primary is None
            or not is_leaflet_section(primary)
            or row.get("answer_mode") != "single"
        ):
            continue
        group = siblings.get((leaflet_page_id(primary), leaflet_intent(primary)), [])
        others = [section_id for section_id in group if section_id != primary["id"]]
        if not others:
            continue
        row["expected_section_ids"] = [primary["id"], *others]
        row["query_intent_count"] = len(row["expected_section_ids"])
        row["answer_mode"] = "any_acceptable"
        row["eval_tags"] = [*row.get("eval_tags", []), "same_intent_sections"]
    return rows


def clean_markdown_preview(value: str) -> str:
    cleaned = re.sub(r"(?m)^#{1,6}\s*", "", value or "")
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"[*_`>]+", " ", cleaned)
    return normalize_spaces(cleaned)


def chunk_context_label(chunk: dict) -> str:
    text = chunk_body_text(chunk)
    headings = markdown_headings(text)
    if headings:
        return clean_query_label(headings[0])
    cleaned = clean_markdown_preview(text)
    first_sentence = cleaned.split(". ")[0]
    return clean_query_label(first_sentence)


def auto_query_for_chunk(chunk: dict, section: dict, category: str) -> str:
    title = normalize_spaces(section.get("title", ""))
    body_text = chunk_body_text(chunk)
    text = clean_markdown_preview(body_text)
    first_sentence = text.split(". ")[0][:140].strip(" -")
    if chunk.get("chunk_role") == "index_entry":
        brand_match = re.search(r"\*\*([^*]+)\*\*", body_text)
        if brand_match:
            return f"{brand_match.group(1)} là biệt dược của hoạt chất nào?"
        return "Tra cứu biệt dược trong mục lục hoạt chất"
    if is_leaflet_section(section) or category.startswith("brand_"):
        if is_leaflet_section(section) and not category.startswith("brand_"):
            category = leaflet_intent(section)
            if not category:
                # "Đặc điểm", "Mã ATC": no lookup intent, so no generic question.
                return ""
        query, _style = leaflet_query_for_category(section, category)
        return query
    if chunk.get("chunk_content_type") == "table" or chunk.get("chunk_role") == "table":
        return f"Bảng trong mục {section_label(section)} nói về thông tin gì?"
    if category == "indication":
        return f"Tìm thông tin chỉ định của {title}"
    if category == "contraindication":
        return f"Tìm thông tin chống chỉ định của {title}"
    if category == "dosage":
        return f"Tìm liều dùng của {title}"
    if category == "general_guidance":
        return f"Tìm hướng dẫn về {section_label(section)}"
    if category == "drug_fact" and title:
        return f"Tìm thông tin về {title}"
    if first_sentence:
        return first_sentence
    return f"Tìm thông tin về {section_label(section)}"


def build_chunks_by_section(chunks: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for chunk in chunks:
        section_id = chunk.get("section_id")
        if section_id:
            grouped[section_id].append(chunk)
    return grouped


def chunk_identifier(chunk: dict) -> str:
    return str(chunk.get("chunk_id") or "")


def chunk_body_text(chunk: dict) -> str:
    body = str(chunk.get("chunk_text") or "").strip()
    return body


def build_chunks_by_id(chunks: list[dict]) -> dict[str, dict]:
    indexed = {}
    for chunk in chunks:
        identifier = chunk_identifier(chunk)
        if identifier:
            indexed[identifier] = chunk
    return indexed


def spread_items[T](items: list[T], slots: int) -> list[T]:
    if not items or slots <= 0:
        return []
    if len(items) <= slots:
        return items
    selected: list[T] = []
    seen_indexes: set[int] = set()
    for offset in range(slots):
        index = min(len(items) - 1, (offset * len(items)) // slots)
        if index not in seen_indexes:
            selected.append(items[index])
            seen_indexes.add(index)
    return selected


def allocate_quotas(
    target_rows: int = DEFAULT_TARGET_ROWS, patient_count: int = 0
) -> dict[str, int]:
    if target_rows <= 0:
        raise ValueError("target_rows must be positive")

    patient_quota = min(patient_count, target_rows)
    remaining_target = target_rows - patient_quota
    scalable_keys = [key for key in DEFAULT_EVAL_GROUP_QUOTAS if key != "leaflet_short"]
    scalable_base_total = sum(DEFAULT_EVAL_GROUP_QUOTAS[key] for key in scalable_keys)

    quotas = {"leaflet_short": patient_quota}
    raw = {
        key: (DEFAULT_EVAL_GROUP_QUOTAS[key] / scalable_base_total) * remaining_target
        for key in scalable_keys
    }
    for key in scalable_keys:
        quotas[key] = int(raw[key])

    remainder = target_rows - sum(quotas.values())
    by_fraction = sorted(
        scalable_keys,
        key=lambda key: (raw[key] - quotas[key], DEFAULT_EVAL_GROUP_QUOTAS[key]),
        reverse=True,
    )
    for key in by_fraction[:remainder]:
        quotas[key] += 1

    if target_rows >= len(DEFAULT_EVAL_GROUP_QUOTAS):
        for key in DEFAULT_EVAL_GROUP_QUOTAS:
            if quotas[key] == 0:
                donor = max(
                    (candidate for candidate in quotas if quotas[candidate] > 1),
                    key=lambda item: quotas[item],
                )
                quotas[donor] -= 1
                quotas[key] = 1

    if sum(quotas.values()) != target_rows:
        raise ValueError(
            f"quota allocation mismatch: {sum(quotas.values())} != {target_rows}"
        )
    return quotas


class EvalRowAccumulator:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.seen_pairs: set[tuple[str, tuple[str, ...] | str]] = set()
        self.seen_queries: set[str] = set()

    def add(self, row: dict, prefer_existing: bool = False) -> bool:
        query_key = row["query"].lower()
        exp_ids = row["expected_section_ids"]
        section_key = tuple(exp_ids) if isinstance(exp_ids, list) else str(exp_ids)
        pair = (query_key, section_key)
        if pair in self.seen_pairs:
            return False
        if query_key in self.seen_queries and prefer_existing:
            return False
        self.rows.append(row)
        self.seen_pairs.add(pair)
        self.seen_queries.add(query_key)
        return True

    def remaining(self, target: int) -> int:
        return max(0, target - len(self.rows))


def auto_candidate_chunks(
    chunks: list[dict],
    sections_by_id: dict[str, dict],
    chunks_by_section: dict[str, list[dict]],
    candidate_target: int,
) -> list[tuple[dict, dict, str, str, str]]:
    by_category: dict[str, list[tuple[dict, dict, str, str, str]]] = defaultdict(list)
    for chunk in sorted(
        chunks, key=lambda item: (item.get("chunk_key", 0), item.get("section_id", ""))
    ):
        section_id = chunk.get("section_id")
        if not isinstance(section_id, str):
            continue
        section = sections_by_id.get(section_id)
        if not section:
            continue
        category, difficulty, expected_role = category_for_section(
            section, chunks_by_section.get(section_id, [])
        )
        by_category[category].append(
            (chunk, section, category, difficulty, expected_role)
        )

    category_order = [
        "brand_lookup",
        "table_lookup",
        "atc_appendix",
        "general_guidance",
        "indication",
        "contraindication",
        "dosage",
        "adr",
        "interaction",
        "pregnancy",
        "drug_fact",
    ]
    slots_per_category = max(8, (candidate_target // max(1, len(category_order))) + 8)
    spread_by_category = {
        category: spread_items(by_category.get(category, []), slots_per_category)
        for category in category_order
    }

    candidates = []
    cursor_by_category = dict.fromkeys(category_order, 0)
    while len(candidates) < candidate_target * 2:
        progressed = False
        for category in category_order:
            cursor = cursor_by_category[category]
            category_items = spread_by_category.get(category, [])
            if cursor >= len(category_items):
                continue
            candidates.append(category_items[cursor])
            cursor_by_category[category] = cursor + 1
            progressed = True
        if not progressed:
            break

    if len(candidates) < candidate_target:
        for category in sorted(by_category):
            for item in spread_items(by_category[category], candidate_target):
                candidates.append(item)
                if len(candidates) >= candidate_target * 3:
                    return candidates
    return candidates


def weighted_targets(weights: dict[str, int], total: int) -> dict[str, int]:
    if total <= 0:
        return dict.fromkeys(weights, 0)
    weight_total = sum(weights.values())
    if weight_total <= 0:
        raise ValueError("weights must have a positive total")

    raw_targets = {
        key: (weight / weight_total) * total for key, weight in weights.items()
    }
    targets = {key: int(value) for key, value in raw_targets.items()}
    remainder = total - sum(targets.values())
    by_fraction = sorted(
        weights,
        key=lambda key: (raw_targets[key] - targets[key], weights[key]),
        reverse=True,
    )
    for key in by_fraction[:remainder]:
        targets[key] += 1
    return targets


def section_candidates(
    sections_by_id: dict[str, dict],
    chunks_by_section: dict[str, list[dict]],
) -> list[tuple[dict, str, str, str]]:
    candidates = []
    for section in sorted(sections_by_id.values(), key=lambda item: item["id"]):
        section_chunks = chunks_by_section.get(section["id"], [])
        category, difficulty, expected_role = category_for_section(
            section, section_chunks
        )
        candidates.append((section, category, difficulty, expected_role))
    return candidates


def sections_by_title_and_category(
    section_items: list[tuple[dict, str, str, str]],
) -> dict[str, dict[str, tuple[dict, str, str, str]]]:
    grouped: dict[str, dict[str, tuple[dict, str, str, str]]] = defaultdict(dict)
    for item in section_items:
        section, category, _difficulty, _expected_role = item
        if is_leaflet_section(section):
            continue
        title = normalize_spaces(section.get("title", ""))
        if title:
            grouped[title][category] = item
    return grouped


def multi_section_candidates(
    section_items: list[tuple[dict, str, str, str]],
) -> list[tuple[tuple[dict, str, str, str], tuple[dict, str, str, str], str]]:
    category_pairs = [
        (
            "indication",
            "dosage",
            "{title} chỉ định cho bệnh gì và dùng liều bao nhiêu?",
        ),
        (
            "dosage",
            "indication",
            "{title} dùng liều thế nào và chỉ định cho bệnh gì?",
        ),
        ("dosage", "adr", "{title} dùng liều thế nào và có tác dụng phụ gì?"),
        (
            "indication",
            "contraindication",
            "{title} dùng cho trường hợp nào và ai không nên dùng?",
        ),
        (
            "pregnancy",
            "contraindication",
            "Người có thai hoặc có chống chỉ định thì dùng {title} thế nào?",
        ),
        (
            "interaction",
            "adr",
            "{title} có tương tác thuốc gì và cần theo dõi tác dụng phụ nào?",
        ),
        (
            "dosage",
            "contraindication",
            "{title} uống bao nhiêu và trường hợp nào cần tránh?",
        ),
        (
            "indication",
            "adr",
            "{title} chỉ định điều trị gì và có tác dụng phụ nào?",
        ),
        (
            "dosage",
            "interaction",
            "{title} dùng liều bao nhiêu và có tương tác với thuốc gì?",
        ),
    ]
    grouped = sections_by_title_and_category(section_items)
    candidates = []
    for title in sorted(grouped):
        category_map = grouped[title]
        for first_category, second_category, template in category_pairs:
            if first_category in category_map and second_category in category_map:
                candidates.append(
                    (
                        category_map[first_category],
                        category_map[second_category],
                        template,
                    )
                )
    return candidates


def build_multi_intent_eval_rows(
    sections: list[dict] | list[tuple[dict, str, str, str]],
    chunks_by_section: dict[str, list[dict]] | None = None,
    target_count: int = 0,
) -> list[dict]:
    chunks_by_section = chunks_by_section or {}
    section_items: list[tuple[dict, str, str, str]] = []

    for item in sections:
        if isinstance(item, tuple) and len(item) == 4:
            section_items.append(item)
        elif isinstance(item, dict):
            sec_id = str(item.get("id") or "")
            sec_chunks = chunks_by_section.get(sec_id, [])
            cat, diff, role = category_for_section(item, sec_chunks)
            section_items.append((item, cat, diff, role))

    candidates = multi_section_candidates(section_items)

    if not candidates:
        grouped: dict[str, list[tuple[dict, str, str, str]]] = defaultdict(list)
        for item in section_items:
            sec = item[0]
            if is_leaflet_section(sec):
                continue
            title = normalize_spaces(sec.get("title", ""))
            if title:
                grouped[title].append(item)
        for _title, items in grouped.items():
            if len(items) >= 2:
                for i in range(len(items) - 1):
                    sec_a = items[i][0]
                    sec_b = items[i + 1][0]
                    label_a = sec_a.get("section", items[i][1])
                    label_b = sec_b.get("section", items[i + 1][1])
                    template = (
                        f"{{title}}: thông tin {label_a} và {label_b} như thế nào?"
                    )
                    candidates.append((items[i], items[i + 1], template))

    if not candidates:
        return []

    rows = []
    seen_queries = set()
    limit = target_count if target_count > 0 else len(candidates)

    candidate_idx = 0
    while len(rows) < limit and candidate_idx < max(10, len(candidates) * 4):
        primary_item, secondary_item, template = candidates[
            candidate_idx % len(candidates)
        ]
        primary_section, _p_cat, _p_diff, primary_role = primary_item
        secondary_section, _s_cat, _s_diff, _s_role = secondary_item

        primary_id = str(primary_section.get("id") or "")
        chunks = chunks_by_section.get(primary_id, [])
        anchors = extract_section_entity_anchors(primary_section, chunks)
        drug_anchor = (
            anchors[0]
            if anchors
            else normalize_spaces(primary_section.get("title", ""))
        )

        query_text = template.format(title=drug_anchor)
        if drug_anchor.lower() not in query_text.lower():
            query_text = f"{drug_anchor}: {query_text}"

        query = unique_query(query_text, seen_queries)
        if query is None:
            continue

        row = make_row(
            f"multi-intent-{len(rows) + 1:04d}",
            query,
            "multi_intent",
            source_family_for_section(primary_section),
            "multi_intent",
            "multi_intent",
            "formulary_multi_intent",
            primary_section,
            primary_role,
            "multi-section query generated from paired final RAG sections",
            expected_section_ids=[primary_section["id"], secondary_section["id"]],
            answer_mode="multi_required",
            retrieval_granularity="multi_section",
            eval_tags=["multi_intent", "formulary"],
        )
        if query.lower() not in seen_queries:
            rows.append(row)
            seen_queries.add(query.lower())
        candidate_idx += 1

    return rows


def is_leaflet_section(section: dict) -> bool:
    return section.get("content_type") == "brand_page" and str(
        section.get("id", "")
    ).startswith("leaflet:")


def is_chunk_risk(chunk: dict) -> bool:
    return (
        chunk.get("hydrate_strategy") in {"chunk_window", "search_only"}
        or chunk.get("chunk_content_type") == "table"
        or chunk.get("chunk_role") in {"table", "index_entry", "appendix_list"}
    )


def leaflet_page_id(section: dict) -> str:
    return str(section.get("page_id") or section.get("id") or "")


def leaflet_representative_sections(sections: Iterable[dict]) -> dict[str, str]:
    """Page id -> the section that answers "what is this product": the indication
    section when the page has one, else its first section."""
    by_page: dict[str, list[dict]] = defaultdict(list)
    for section in sections:
        if is_leaflet_section(section):
            by_page[leaflet_page_id(section)].append(section)
    representatives = {}
    for page, items in by_page.items():
        ordered = sorted(items, key=lambda item: str(item["id"]))
        indication = [
            item
            for item in ordered
            if "brand_indication" in leaflet_categories_for_text(item.get("text", ""))
        ]
        representatives[page] = str((indication or ordered)[0]["id"])
    return representatives


def leaflet_candidates(
    sections_by_id: dict[str, dict],
    chunks_by_section: dict[str, list[dict]],
) -> list[tuple[dict, dict | None, str]]:
    candidates = []
    seen: set[tuple[str, str, str]] = set()
    representatives = set(
        leaflet_representative_sections(sections_by_id.values()).values()
    )
    for section in sorted(sections_by_id.values(), key=lambda item: item["id"]):
        if not is_leaflet_section(section):
            continue
        chunks = sorted(
            chunks_by_section.get(section["id"], []),
            key=lambda item: (item.get("chunk_index", 0), chunk_identifier(item)),
        )
        section_categories = [
            category
            for category in leaflet_categories_for_text(section.get("text", ""))
            if category != "brand_product"
        ]
        if section["id"] in representatives:
            section_categories.append("brand_product")

        for category in section_categories:
            chunk = first_chunk_for_leaflet_category(chunks, category)
            chunk_key = chunk_identifier(chunk) if chunk else ""
            candidate_key = (section["id"], chunk_key, category)
            if candidate_key in seen:
                continue
            seen.add(candidate_key)
            candidates.append((section, chunk, category))

    priority = {
        category: index for index, category in enumerate(LEAFLET_CATEGORY_PRIORITY)
    }
    return sorted(
        candidates,
        key=lambda item: (
            priority.get(item[2], len(priority)),
            item[0]["id"],
            -1 if item[1] is None else int(item[1].get("chunk_index", 0)),
        ),
    )


def display_product_name(section: dict) -> str:
    """Shortest product name of a leaflet (brand, strength, form), not the shop title."""
    names = [
        normalize_spaces(str(name))
        for name in (section.get("colloquial_mapping") or {}).get("product_names", [])
        if str(name).strip()
    ]
    if names:
        return min(names, key=len)
    return normalize_spaces(section.get("title", ""))


def leaflet_query_for_category(section: dict, category: str) -> tuple[str, str]:
    template, style = LEAFLET_QUERY_TEMPLATES.get(
        category, LEAFLET_QUERY_TEMPLATES["brand_product"]
    )
    return template.format(title=display_product_name(section)), style


def first_chunk_for_leaflet_category(chunks: list[dict], category: str) -> dict | None:
    for chunk in chunks:
        if category in leaflet_categories_for_text(chunk_body_text(chunk)):
            return chunk
    return chunks[0] if chunks else None


def taxonomy_for_section_category(section: dict, category: str) -> tuple[str, str]:
    return taxonomy_for_source_category(
        category, is_leaflet=is_leaflet_section(section)
    )


def query_form_for_style(query_style: str) -> str:
    if query_style in {"coverage_chunk", "coverage_fill"}:
        return "chunk_coverage"
    if query_style in {
        "brand_product",
        "brand_ingredient",
        "brand_indication",
        "brand_dosage",
        "brand_safety",
        "brand_storage",
    }:
        return "brand_template"
    if query_style == "leaflet_short":
        return "leaflet_short"
    if query_style == "colloquial_alias":
        return "colloquial_alias"
    return query_style


def eval_group_for_row(query_form: str, section: dict, source_hint: str = "") -> str:
    if query_form == "leaflet_short":
        return "leaflet_short"
    if query_form == "multi_intent":
        return "multi_intent"
    if query_form in {"noisy", "typo"}:
        return "noisy"
    if query_form == "chunk_coverage" or source_hint == "coverage":
        return "chunk_risk"
    if query_form in {"brand_template", "colloquial_alias"} or is_leaflet_section(
        section
    ):
        return "leaflet"
    return "formulary"


def retrieval_granularity_for_row(
    section: dict, chunk: dict | None = None, role: str = ""
) -> str:
    strategy = section.get("hydrate_strategy", "full_section")
    if chunk:
        strategy = chunk.get("hydrate_strategy", strategy)
        role = role or chunk.get("chunk_role", "")
    return retrieval_granularity_from_hydrate_strategy(strategy, role)


def make_leaflet_row(
    query_id: str,
    section: dict,
    chunk: dict | None,
    category: str,
) -> dict:
    query, style = leaflet_query_for_category(section, category)
    expected_chunk_id = chunk_identifier(chunk) if chunk else ""
    expected_chunk_index = chunk.get("chunk_index", -1) if chunk else -1
    role = chunk.get("chunk_role", "prose") if chunk else "prose"
    intent_category, source_subcategory = taxonomy_for_section_category(
        section, category
    )
    query_form = query_form_for_style(style)
    granularity = retrieval_granularity_for_row(section, chunk, role)
    return make_row(
        query_id=query_id,
        query=query,
        eval_group="leaflet",
        source_family=source_family_for_section(section),
        query_form=query_form,
        intent_category=intent_category,
        source_subcategory=source_subcategory,
        section=section,
        expected_chunk_role=role,
        notes=f"coverage leaflet subsection {category}",
        expected_chunk_id=expected_chunk_id,
        expected_chunk_index=expected_chunk_index,
        retrieval_granularity=granularity,
        eval_tags=["leaflet", category],
    )


def colloquial_mapping_for_record(record: dict) -> dict:
    return compact_colloquial_mapping(record)


def product_aliases_for_section(section: dict) -> list[str]:
    mapping = colloquial_mapping_for_record(section)
    aliases = mapping.get("aliases") or []
    if not isinstance(aliases, list):
        return []

    title = normalize_spaces(section.get("title", "")).casefold()
    deduped = []
    seen = set()
    for alias in aliases:
        cleaned = normalize_spaces(str(alias))
        key = cleaned.casefold()
        if not cleaned or key in seen or key == title:
            continue
        deduped.append(cleaned)
        seen.add(key)
    return deduped


def normalize_alias_key(alias: str) -> str:
    return normalize_spaces(alias).casefold()


def build_colloquial_alias_overlap_index(sections: list[dict]) -> dict[str, dict]:
    """Aliases shared by several leaflet pages; each page is listed by its
    representative section (see leaflet_representative_sections)."""
    representatives = leaflet_representative_sections(sections)
    grouped: dict[str, dict] = {}
    for section in sorted(sections, key=lambda item: str(item.get("id") or "")):
        if not is_leaflet_section(section):
            continue
        page = leaflet_page_id(section)
        if not page:
            continue
        for alias in product_aliases_for_section(section):
            alias_key = normalize_alias_key(alias)
            if not alias_key:
                continue
            entry = grouped.setdefault(
                alias_key, {"alias": alias, "section_ids": set()}
            )
            entry["section_ids"].add(representatives[page])

    overlap = {}
    for alias_key, entry in sorted(grouped.items()):
        section_ids = sorted(entry["section_ids"])
        if len(section_ids) > 1:
            overlap[alias_key] = {
                "alias": str(entry["alias"]),
                "section_ids": section_ids,
            }
    return overlap


def make_colloquial_alias_row(
    query_id: str,
    section: dict,
    chunk: dict | None,
    category: str,
    alias: str,
) -> dict:
    template = COLLOQUIAL_ALIAS_QUERY_TEMPLATES.get(
        category, COLLOQUIAL_ALIAS_QUERY_TEMPLATES["brand_product"]
    )
    query = template.format(alias=alias)
    expected_chunk_id = chunk_identifier(chunk) if chunk else ""
    expected_chunk_index = chunk.get("chunk_index", -1) if chunk else -1
    role = chunk.get("chunk_role", "prose") if chunk else "prose"
    intent_category, source_subcategory = taxonomy_for_section_category(
        section, category
    )
    granularity = retrieval_granularity_for_row(section, chunk, role)
    return make_row(
        query_id=query_id,
        query=query,
        eval_group="leaflet",
        source_family=source_family_for_section(section),
        query_form="colloquial_alias",
        intent_category=intent_category,
        source_subcategory=source_subcategory,
        section=section,
        expected_chunk_role=role,
        notes=f"colloquial alias query generated from product_aliases for {category}",
        expected_chunk_id=expected_chunk_id,
        expected_chunk_index=expected_chunk_index,
        retrieval_granularity=granularity,
        eval_tags=["leaflet", category, "colloquial_alias"],
    )


def make_colloquial_alias_any_acceptable_row(
    query_id: str,
    section: dict,
    alias: str,
    expected_section_ids: list[str],
) -> dict:
    query = COLLOQUIAL_ALIAS_QUERY_TEMPLATES["brand_product"].format(alias=alias)
    intent_category, source_subcategory = taxonomy_for_section_category(
        section, "brand_product"
    )
    return make_row(
        query_id=query_id,
        query=query,
        eval_group="leaflet",
        source_family=source_family_for_section(section),
        query_form="colloquial_alias",
        intent_category=intent_category,
        source_subcategory=source_subcategory,
        section=section,
        expected_chunk_role="prose",
        notes="ambiguous colloquial alias query generated from product_aliases",
        expected_section_ids=expected_section_ids,
        answer_mode=answer_mode_for_expected_ids(expected_section_ids),
        expected_chunk_id="",
        expected_chunk_index=-1,
        retrieval_granularity="section",
        eval_tags=[
            "leaflet",
            "brand_product",
            "colloquial_alias",
            "ambiguous_alias",
            "any_acceptable",
        ],
    )


def chunk_risk_candidates(
    chunks: list[dict],
    sections_by_id: dict[str, dict],
) -> list[tuple[dict, dict]]:
    candidates = []
    for chunk in sorted(
        chunks, key=lambda item: (item.get("chunk_key", 0), chunk_identifier(item))
    ):
        if not is_chunk_risk(chunk):
            continue
        section = sections_by_id.get(chunk.get("section_id", ""))
        if not section:
            continue
        candidates.append((chunk, section))
    return candidates


def generate_rows(
    sections: list[dict],
    chunks: list[dict],
    target_rows: int | None = DEFAULT_TARGET_ROWS,
    patient_rows: list[dict] | None = None,
) -> list[dict]:
    effective_target = target_rows if target_rows is not None else DEFAULT_TARGET_ROWS
    patient_rows = patient_rows or []
    quotas = allocate_quotas(effective_target, patient_count=len(patient_rows))
    sections_by_id = {
        section["id"]: section for section in sections if section.get("id")
    }
    chunks_by_section = build_chunks_by_section(chunks)
    brand_names_by_title = extract_brand_names(sections)
    accumulator = EvalRowAccumulator()
    section_items = section_candidates(sections_by_id, chunks_by_section)
    formulary_section_items = [
        item for item in section_items if not is_leaflet_section(item[0])
    ]
    if not formulary_section_items:
        formulary_section_items = section_items

    patient_count = 0
    for row in patient_rows:
        if accumulator.add(row):
            patient_count += 1
        if patient_count >= quotas["leaflet_short"]:
            break

    def append_section_row(
        section: dict,
        category: str,
        difficulty: str,
        expected_role: str,
        query_style: str,
        style_count: int,
    ) -> bool:
        title = section.get("title", "")
        section_brands = brand_names_by_title.get(title)
        section_aliases = FRIENDLY_ALIASES.get(title)
        section_chunks = chunks_by_section.get(section["id"], [])
        if query_style == "hybrid_entity_intent":
            anchors = extract_section_entity_anchors(section, section_chunks)
            query_text = build_hybrid_entity_intent_query(section, category, anchors)
        else:
            query_text = styled_query_for_section(
                section,
                category,
                query_style,
                style_count - 1,
                brand_names=section_brands,
                aliases=section_aliases,
            )

        query = unique_query(query_text, accumulator.seen_queries)
        if query is None:
            return False

        section_chunks = chunks_by_section.get(section["id"], [])
        if section_chunks:
            first_chunk = section_chunks[0]
            expected_chunk_id = chunk_identifier(first_chunk)
            expected_chunk_index = first_chunk.get("chunk_index", 0)
        else:
            first_chunk = None
            expected_chunk_id = ""
            expected_chunk_index = -1

        query_form = query_form_for_style(query_style)
        intent_category, source_subcategory = taxonomy_for_section_category(
            section, category
        )
        granularity = retrieval_granularity_for_row(section, first_chunk, expected_role)
        tags = ["curated", category]
        if expected_role == "table":
            tags.append("table")
        if granularity == "chunk_exact":
            tags.append("search_index")
        if granularity == "chunk_window":
            tags.append("chunk_window")
        row = make_row(
            f"{query_form}-{style_count:04d}",
            query,
            eval_group_for_row(query_form, section),
            source_family_for_section(section),
            query_form,
            intent_category,
            source_subcategory,
            section,
            expected_role,
            f"{query_style} query generated from final RAG section metadata",
            expected_chunk_id=expected_chunk_id,
            expected_chunk_index=expected_chunk_index,
            retrieval_granularity=granularity,
            eval_tags=tags,
        )
        return accumulator.add(row)

    def append_auto_row(
        chunk: dict,
        section: dict,
        category: str,
        difficulty: str,
        expected_role: str,
        auto_count: int,
        query_style: str,
        source_type: str = "auto",
        notes: str | None = None,
    ) -> bool:
        role = chunk.get("chunk_role") or expected_role
        if is_leaflet_section(section) and not category.startswith("brand_"):
            category = leaflet_intent(section)
        query = unique_query(
            auto_query_for_chunk(chunk, section, category),
            accumulator.seen_queries,
        )
        if query is None:
            return False

        expected_chunk_id = chunk_identifier(chunk)
        expected_chunk_index = chunk.get("chunk_index", 0)

        query_form = query_form_for_style(query_style)
        intent_category, source_subcategory = taxonomy_for_section_category(
            section, category
        )
        granularity = retrieval_granularity_for_row(section, chunk, role)
        tags = ["auto", category]
        if source_type == "coverage":
            tags.append("coverage")
        if role == "table":
            tags.append("table")
        if granularity == "chunk_exact":
            tags.append("search_index")
        if granularity == "chunk_window":
            tags.append("chunk_window")
        row = make_row(
            f"{query_style.replace('_', '-')}-{auto_count:04d}",
            query,
            eval_group_for_row(query_form, section, source_hint=source_type),
            source_family_for_section(section),
            query_form,
            intent_category,
            source_subcategory,
            section,
            role,
            notes or f"generated from chunk {chunk_identifier(chunk)}",
            expected_chunk_id=expected_chunk_id,
            expected_chunk_index=expected_chunk_index,
            retrieval_granularity=granularity,
            eval_tags=tags,
        )
        return accumulator.add(row)

    leaflet_count = 0
    leaflet_targets = weighted_targets(LEAFLET_QUERY_FORM_TARGETS, quotas["leaflet"])
    leaflet_alias_target = leaflet_targets.get("colloquial_alias", 0)
    leaflet_hybrid_target = leaflet_targets.get("hybrid_entity_intent", 0)
    leaflet_template_target = (
        quotas["leaflet"] - leaflet_alias_target - leaflet_hybrid_target
    )
    all_leaflet_items = leaflet_candidates(sections_by_id, chunks_by_section)
    alias_answer_targets = weighted_targets(
        LEAFLET_ALIAS_ANSWER_MODE_TARGETS, leaflet_alias_target
    )
    alias_single_target = alias_answer_targets.get("single", 0)
    alias_any_target = alias_answer_targets.get("any_acceptable", 0)
    ambiguous_alias_index = build_colloquial_alias_overlap_index(
        list(sections_by_id.values())
    )
    ambiguous_alias_keys = set(ambiguous_alias_index)
    strict_alias_targets = effective_target >= DEFAULT_TARGET_ROWS
    # Each shared alias gives one question, so there are at most that many
    # any_acceptable rows; the remainder goes to single-answer alias rows.
    shortfall = max(0, alias_any_target - len(ambiguous_alias_index))
    alias_any_target -= shortfall
    alias_single_target += shortfall

    single_alias_items = [
        item
        for item in all_leaflet_items
        if any(
            normalize_alias_key(alias) not in ambiguous_alias_keys
            for alias in product_aliases_for_section(item[0])
        )
    ]
    single_alias_items = spread_items(single_alias_items, alias_single_target)
    alias_single_count = 0
    alias_index = 0
    alias_attempts = 0
    while (
        alias_single_count < alias_single_target
        and single_alias_items
        and alias_attempts < max(1, len(single_alias_items) * 12)
    ):
        section, chunk, category = single_alias_items[
            alias_index % len(single_alias_items)
        ]
        aliases = [
            alias
            for alias in product_aliases_for_section(section)
            if normalize_alias_key(alias) not in ambiguous_alias_keys
        ]
        if aliases:
            alias = aliases[(alias_index // len(single_alias_items)) % len(aliases)]
            row = make_colloquial_alias_row(
                f"leaflet-alias-{alias_single_count + 1:04d}",
                section,
                chunk,
                category,
                alias,
            )
            query = unique_query(row["query"], accumulator.seen_queries)
            if query is not None:
                row["query"] = query
                if accumulator.add(row):
                    alias_single_count += 1
                    leaflet_count += 1
        alias_index += 1
        alias_attempts += 1

    if strict_alias_targets and alias_single_count != alias_single_target:
        raise ValueError(
            f"could only generate {alias_single_count} single colloquial alias rows"
        )

    ambiguous_alias_groups = sorted(
        ambiguous_alias_index.values(),
        key=lambda group: (str(group["alias"]).casefold(), group["section_ids"]),
    )
    if alias_any_target and not ambiguous_alias_groups:
        if strict_alias_targets:
            raise ValueError(
                "could not generate any_acceptable alias rows: no ambiguous colloquial aliases found"
            )
        alias_any_target = 0

    alias_any_count = 0
    alias_any_index = 0
    while alias_any_count < alias_any_target and alias_any_index < len(
        ambiguous_alias_groups
    ):
        group = ambiguous_alias_groups[alias_any_index % len(ambiguous_alias_groups)]
        expected_ids = list(group["section_ids"])
        section = sections_by_id[expected_ids[0]]
        row = make_colloquial_alias_any_acceptable_row(
            f"leaflet-alias-any-{alias_any_count + 1:04d}",
            section,
            str(group["alias"]),
            expected_ids,
        )
        query = unique_query(row["query"], accumulator.seen_queries)
        if query is not None:
            row["query"] = query
            if accumulator.add(row):
                alias_any_count += 1
                leaflet_count += 1
        alias_any_index += 1

    if strict_alias_targets and alias_any_count != alias_any_target:
        raise ValueError(
            f"could only generate {alias_any_count} any_acceptable colloquial alias rows"
        )

    # Spread picks are tried first; the rest of the pool backs up picks whose
    # question was already used, so the group still reaches its quota.
    spread = spread_items(all_leaflet_items, leaflet_template_target)
    spread_ids = {id(item) for item in spread}
    leaflet_items = spread + [
        item for item in all_leaflet_items if id(item) not in spread_ids
    ]
    leaflet_index = 0
    # Each candidate has one fixed question, so one pass over the list is enough.
    while (
        leaflet_count < quotas["leaflet"]
        and leaflet_items
        and leaflet_index < len(leaflet_items)
    ):
        section, chunk, category = leaflet_items[leaflet_index]
        row = make_leaflet_row(
            f"leaflet-{leaflet_count + 1:04d}", section, chunk, category
        )
        query = unique_query(row["query"], accumulator.seen_queries)
        if query is not None:
            row["query"] = query
            if accumulator.add(row):
                leaflet_count += 1
        leaflet_index += 1

    chunk_risk_count = 0
    chunk_risk_items = spread_items(
        chunk_risk_candidates(chunks, sections_by_id), quotas["chunk_risk"]
    )
    chunk_risk_index = 0
    while chunk_risk_count < quotas["chunk_risk"] and chunk_risk_index < len(
        chunk_risk_items
    ):
        chunk, section = chunk_risk_items[chunk_risk_index]
        category, difficulty, expected_role = category_for_section(
            section, chunks_by_section.get(section["id"], [])
        )
        if is_leaflet_section(section):
            category = leaflet_intent(section)
            difficulty = "medium"
            expected_role = chunk.get("chunk_role") or "prose"
        if append_auto_row(
            chunk,
            section,
            category,
            difficulty,
            expected_role,
            chunk_risk_count + 1,
            "coverage_chunk",
            source_type="coverage",
            notes=f"coverage chunk-risk {chunk_identifier(chunk)}",
        ):
            chunk_risk_count += 1
        chunk_risk_index += 1

    style_targets = weighted_targets(FORMULARY_QUERY_FORM_TARGETS, quotas["formulary"])
    style_targets.update(weighted_targets(NOISY_QUERY_FORM_TARGETS, quotas["noisy"]))
    style_counts = dict.fromkeys(style_targets, 0)

    lexical_target = style_targets.get("lexical", 0)
    auto_candidates = [
        item
        for item in auto_candidate_chunks(
            chunks,
            sections_by_id,
            chunks_by_section,
            max(effective_target, lexical_target),
        )
        if not is_leaflet_section(item[1])
    ]
    if not auto_candidates:
        auto_candidates = auto_candidate_chunks(
            chunks,
            sections_by_id,
            chunks_by_section,
            max(effective_target, lexical_target),
        )
    seen_auto_sections: set[str] = set()

    for chunk, section, category, difficulty, expected_role in auto_candidates:
        if style_counts["lexical"] >= lexical_target:
            break
        if section["id"] in seen_auto_sections:
            continue
        if append_auto_row(
            chunk,
            section,
            category,
            difficulty,
            expected_role,
            style_counts["lexical"] + 1,
            "lexical",
        ):
            style_counts["lexical"] += 1
            seen_auto_sections.add(section["id"])

    lexical_index = 0
    while style_counts["lexical"] < lexical_target and lexical_index < len(
        auto_candidates
    ):
        chunk, section, category, difficulty, expected_role = auto_candidates[
            lexical_index
        ]
        if append_auto_row(
            chunk,
            section,
            category,
            difficulty,
            expected_role,
            style_counts["lexical"] + 1,
            "lexical",
        ):
            style_counts["lexical"] += 1
        lexical_index += 1

    for query_style in (
        "template",
        "paraphrase",
        "natural",
        "clinical",
        "noisy",
        "typo",
    ):
        target = style_targets.get(query_style, 0)
        variant_round = 0
        style_section_items = spread_items(formulary_section_items, target)
        while style_counts[query_style] < target:
            progressed = False
            for section, category, difficulty, expected_role in style_section_items:
                if append_section_row(
                    section,
                    category,
                    difficulty,
                    expected_role,
                    query_style,
                    style_counts[query_style] + 1 + variant_round,
                ):
                    style_counts[query_style] += 1
                    progressed = True
                if style_counts[query_style] >= target:
                    break
            if not progressed:
                break
            variant_round += 1

    multi_target = quotas["multi_intent"]
    multi_rows = build_multi_intent_eval_rows(
        formulary_section_items, chunks_by_section, target_count=multi_target
    )
    for row in multi_rows:
        query = unique_query(row["query"], accumulator.seen_queries)
        if query is not None:
            row["query"] = query
            accumulator.add(row)

    fill_count = 0
    fill_candidates = auto_candidate_chunks(
        chunks, sections_by_id, chunks_by_section, effective_target
    )
    fill_index = 0
    while accumulator.remaining(effective_target) and fill_index < len(fill_candidates):
        chunk, section, category, difficulty, expected_role = fill_candidates[
            fill_index
        ]
        if append_auto_row(
            chunk,
            section,
            category,
            difficulty,
            expected_role,
            fill_count + 1,
            "coverage_fill",
            source_type="coverage",
            notes=f"deterministic fill from chunk {chunk_identifier(chunk)}",
        ):
            fill_count += 1
        fill_index += 1

    if len(accumulator.rows) != effective_target:
        raise ValueError(
            f"could only generate {len(accumulator.rows)} rows for target {effective_target}"
        )
    return accumulator.rows


def row_eval_groups(row: dict) -> set[str]:
    groups = {
        value
        for value in (
            row.get("eval_group", ""),
            row.get("source_family", ""),
            row.get("query_form", ""),
            row.get("intent_category", ""),
            row.get("source_subcategory", ""),
        )
        if value
    }
    tags = row.get("eval_tags", [])
    if isinstance(tags, list):
        groups.update(tag for tag in tags if tag)
    else:
        groups.update(tag for tag in str(tags).split("|") if tag)
    role = row.get("expected_chunk_role", "")
    granularity = row.get("retrieval_granularity", "")

    if row.get("source_family") == "drug_formulary":
        groups.add("drug_formulary")
    if row.get("source_family") == "leaflet_brand":
        groups.add("leaflet")
    if row.get("intent_category") == "table_lookup" or role == "table":
        groups.add("table")
    if role in {"index_entry", "appendix_list"} or granularity == "chunk_exact":
        groups.add("search_index")
    if granularity == "chunk_window":
        groups.add("chunk_window")
    return groups


def validate_required_eval_groups(
    rows: list[dict], required_groups: set[str] | None = None
) -> None:
    if len(rows) < 100:
        return
    observed = set()
    for row in rows:
        observed.update(row_eval_groups(row))
    required = required_groups or {
        "formulary",
        "leaflet",
        "chunk_risk",
        "table",
        "search_index",
        "chunk_window",
        "multi_intent",
        "noisy",
    }
    missing = sorted(required - observed)
    if missing:
        raise ValueError(f"expected required eval group(s), missing: {missing}")


def validate_leaflet_category_coverage(rows: list[dict]) -> None:
    if len(rows) < 1000:
        return

    leaflet_rows = [row for row in rows if row.get("source_family") == "leaflet_brand"]
    if not leaflet_rows:
        return

    category_counts: dict[str, int] = defaultdict(int)
    for row in leaflet_rows:
        category_counts[row.get("source_subcategory", "")] += 1

    observed_categories = {
        category for category, count in category_counts.items() if count > 0
    }
    if observed_categories <= {"leaflet_product", "leaflet_ingredient"}:
        raise ValueError(
            "Leaflet eval coverage collapsed: only leaflet_product/leaflet_ingredient categories are present"
        )

    safety_total = sum(
        category_counts[category]
        for category in (
            "leaflet_contraindication",
            "leaflet_adr",
            "leaflet_precaution",
            "leaflet_interaction",
        )
    )
    missing_thresholds = []
    if category_counts["leaflet_dosage"] < 20:
        missing_thresholds.append(
            f"leaflet_dosage={category_counts['leaflet_dosage']} < 20"
        )
    if category_counts["leaflet_indication"] < 20:
        missing_thresholds.append(
            f"leaflet_indication={category_counts['leaflet_indication']} < 20"
        )
    if safety_total < 20:
        missing_thresholds.append(f"brand_safety_total={safety_total} < 20")
    if missing_thresholds:
        raise ValueError(
            f"Leaflet eval coverage below threshold: {', '.join(missing_thresholds)}"
        )


def validate_rows(
    rows: list[dict],
    sections: list[dict],
    chunks: list[dict] | None = None,
    min_rows: int = DEFAULT_MIN_ROWS,
    max_rows: int = DEFAULT_MAX_ROWS,
    required_groups: set[str] | None = None,
) -> None:
    section_ids = {section["id"] for section in sections if section.get("id")}
    chunks_by_id = build_chunks_by_id(chunks or [])
    query_ids: set[str] = set()
    query_pairs: set[tuple[str, tuple[str, ...] | str]] = set()
    eval_groups: set[str] = set()
    source_families: set[str] = set()
    intent_categories: set[str] = set()
    query_forms: set[str] = set()

    if not (min_rows <= len(rows) <= max_rows):
        raise ValueError(f"expected {min_rows}-{max_rows} rows, got {len(rows)}")

    for index, row in enumerate(rows, start=1):
        missing_columns = [column for column in EVAL_HEADER if column not in row]
        if missing_columns:
            raise ValueError(f"row {index} is missing columns: {missing_columns}")
        if not row["query_id"]:
            raise ValueError(f"row {index} has empty query_id")
        if row["query_id"] in query_ids:
            raise ValueError(f"duplicate query_id: {row['query_id']}")
        query_ids.add(row["query_id"])
        exp_ids = row["expected_section_ids"]
        section_key = tuple(exp_ids) if isinstance(exp_ids, list) else str(exp_ids)
        query_pair = (row["query"].lower(), section_key)
        if query_pair in query_pairs:
            raise ValueError(
                f"duplicate query and expected sections: {row['query']} -> {row['expected_section_ids']}"
            )
        query_pairs.add(query_pair)
        if row["expected_section_id"] not in section_ids:
            raise ValueError(
                f"row {index} has unknown expected_section_id: {row['expected_section_id']}"
            )
        expected_ids = exp_ids if isinstance(exp_ids, list) else str(exp_ids).split("|")
        if any(expected_id not in section_ids for expected_id in expected_ids):
            raise ValueError(
                f"row {index} has unknown expected_section_ids: {row['expected_section_ids']}"
            )
        for field, allowed in (
            ("eval_group", ALLOWED_EVAL_GROUPS),
            ("source_family", ALLOWED_SOURCE_FAMILIES),
            ("query_form", ALLOWED_QUERY_FORMS),
            ("intent_category", ALLOWED_INTENT_CATEGORIES),
            ("answer_mode", ALLOWED_ANSWER_MODES),
            ("retrieval_granularity", ALLOWED_RETRIEVAL_GRANULARITIES),
        ):
            if row[field] not in allowed:
                raise ValueError(f"row {index} has unknown {field}: {row[field]}")
        if not row["source_subcategory"]:
            raise ValueError(f"row {index} has empty source_subcategory")
        expected_chunk_id = row.get("expected_chunk_id", "")
        if expected_chunk_id:
            chunk = chunks_by_id.get(expected_chunk_id)
            if not chunk:
                raise ValueError(
                    f"row {index} has unknown expected_chunk_id: {expected_chunk_id}"
                )
            if chunk.get("section_id") not in expected_ids:
                raise ValueError(
                    f"row {index} has expected_chunk_id outside expected sections: {expected_chunk_id}"
                )
            try:
                row_chunk_index = int(row.get("expected_chunk_index", -1))
                actual_chunk_index = int(chunk.get("chunk_index", 0))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"row {index} has non-integer expected_chunk_index"
                ) from exc
            if row_chunk_index != actual_chunk_index:
                raise ValueError(
                    f"row {index} has mismatched expected_chunk_index for {expected_chunk_id}: "
                    f"{row_chunk_index} != {actual_chunk_index}"
                )
        try:
            query_intent_count = int(row["query_intent_count"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"row {index} has non-integer query_intent_count") from exc
        if query_intent_count != len(expected_ids):
            raise ValueError(f"row {index} has mismatched query_intent_count")
        if row["answer_mode"] == "multi_required" and len(expected_ids) < 2:
            raise ValueError(
                f"row {index} is multi_required without multiple expected sections"
            )
        if row["answer_mode"] == "any_acceptable" and len(expected_ids) < 2:
            raise ValueError(
                f"row {index} is any_acceptable without multiple expected sections"
            )
        if row["answer_mode"] == "single" and len(expected_ids) != 1:
            raise ValueError(
                f"row {index} is single answer with multiple expected sections"
            )
        if (
            row["retrieval_granularity"] == "multi_section"
            and row["answer_mode"] != "multi_required"
        ):
            raise ValueError(
                f"row {index} is multi_section retrieval without multi_required answer_mode"
            )
        if (
            row["answer_mode"] == "multi_required"
            and row["retrieval_granularity"] != "multi_section"
        ):
            raise ValueError(
                f"row {index} is multi_required without multi_section retrieval"
            )
        eval_groups.add(row["eval_group"])
        source_families.add(row["source_family"])
        intent_categories.add(row["intent_category"])
        query_forms.add(row["query_form"])

    if len(rows) > 1 and len(intent_categories) < 2:
        raise ValueError("expected more than one intent_category")
    validate_required_eval_groups(rows, required_groups)
    if len(rows) >= 100:
        required_query_forms = (
            set(FORMULARY_QUERY_FORM_TARGETS)
            | set(NOISY_QUERY_FORM_TARGETS)
            | set(LEAFLET_QUERY_FORM_TARGETS)
            | {"brand_template", "chunk_coverage", "multi_intent"}
        )
        if "leaflet_short" in eval_groups:
            required_query_forms.add("leaflet_short")
        missing_query_forms = sorted(required_query_forms - query_forms)
        if missing_query_forms:
            raise ValueError(
                f"expected all query forms, missing: {missing_query_forms}"
            )
    validate_leaflet_category_coverage(rows)


def save_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def distribution_summary(
    rows: list[dict], sections: list[dict], chunks: list[dict]
) -> str:
    section_type_by_id = {
        section["id"]: section.get("content_type", "")
        for section in sections
        if section.get("id")
    }
    lines = ["Evaluation distribution summary:"]
    lines.append(f"  corpus sections: {len(sections)}")
    lines.append(f"  corpus chunks: {len(chunks)}")
    lines.append(f"  rows: {len(rows)}")

    def counts_for(field: str) -> list[tuple[str, int]]:
        counter: dict[str, int] = defaultdict(int)
        for row in rows:
            val = row.get(field, "")
            if isinstance(val, list):
                val = ",".join(str(v) for v in val)
            counter[str(val)] += 1
        return sorted(counter.items(), key=lambda item: (-item[1], item[0]))

    for label, field in (
        ("eval_group", "eval_group"),
        ("source_family", "source_family"),
        ("query_form", "query_form"),
        ("intent_category", "intent_category"),
        ("source_subcategory", "source_subcategory"),
        ("answer_mode", "answer_mode"),
        ("retrieval_granularity", "retrieval_granularity"),
    ):
        values = ", ".join(f"{key}={value}" for key, value in counts_for(field)[:12])
        lines.append(f"  {label}: {values}")

    content_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        content_counts[
            section_type_by_id.get(row["expected_section_id"], "unknown")
        ] += 1
    content_values = ", ".join(
        f"{key}={value}"
        for key, value in sorted(
            content_counts.items(), key=lambda item: (-item[1], item[0])
        )
    )
    lines.append(f"  expected content_type: {content_values}")
    return "\n".join(lines)


def load_patient_queries(
    json_path: Path,
    sections_by_id: dict[str, dict],
    chunks_by_section: dict[str, list[dict]],
) -> list[dict]:
    if not json_path.exists():
        return []
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    rows = []
    for idx, item in enumerate(data, start=1):
        query = item["query"]
        category = item["category"]
        section_id = item["expected_section_id"]
        notes = item["notes"]
        if section_id not in sections_by_id:
            raise ValueError(
                f"Invalid expected_section_id '{section_id}' in patient query: '{query}'"
            )
        section = sections_by_id[section_id]
        if not is_leaflet_section(section):
            raise ValueError(
                "Patient query expected_section_id must be a leaflet section "
                f"(leaflet:*), got '{section_id}' for query: '{query}'"
            )
        chunks = chunks_by_section.get(section_id, [])
        expected_chunk_role = (
            chunk_role_for_section(section_id, chunks_by_section) or "prose"
        )
        first_chunk = chunks[0] if chunks else {}
        expected_chunk_id = chunk_identifier(first_chunk) if first_chunk else ""
        expected_chunk_index = first_chunk.get("chunk_index", 0) if first_chunk else -1
        query_id = f"patient-{idx:03d}"
        expected_ids = [section_id]
        answer_mode = answer_mode_for_expected_ids(expected_ids)
        intent_category, source_subcategory = taxonomy_for_section_category(
            section, category
        )
        granularity = retrieval_granularity_for_row(
            section, first_chunk, expected_chunk_role
        )
        tags = ["leaflet_short", category]
        if len(expected_ids) > 1:
            tags.append("brand_overlap")
        if granularity == "chunk_window":
            tags.append("chunk_window")
        if granularity == "chunk_exact":
            tags.append("search_index")
        row = make_row(
            query_id=query_id,
            query=query,
            eval_group="leaflet_short",
            source_family=source_family_for_section(section),
            query_form="leaflet_short",
            intent_category=intent_category,
            source_subcategory=source_subcategory,
            section=section,
            expected_chunk_role=expected_chunk_role,
            notes=notes,
            expected_section_ids=expected_ids,
            answer_mode=answer_mode,
            expected_chunk_id=expected_chunk_id,
            expected_chunk_index=expected_chunk_index,
            retrieval_granularity=granularity,
            eval_tags=tags,
        )
        rows.append(row)
    return rows


def build_jsonl(
    sections_path: Path = DEFAULT_SECTIONS_PATH,
    chunks_path: Path = DEFAULT_CHUNKS_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    min_rows: int = DEFAULT_MIN_ROWS,
    max_rows: int = DEFAULT_MAX_ROWS,
    target_rows: int = DEFAULT_TARGET_ROWS,
    patient_queries_path: Path | None = None,
) -> list[dict]:
    sections = load_jsonl(sections_path)
    chunks = load_jsonl(chunks_path)

    patient_json_path = patient_queries_path or (GOLD_DIR / "patient_queries.json")
    patient_rows = []
    if patient_json_path.exists():
        sections_by_id = {
            section["id"]: section for section in sections if section.get("id")
        }
        chunks_by_section = build_chunks_by_section(chunks)
        patient_rows = load_patient_queries(
            patient_json_path,
            sections_by_id,
            chunks_by_section,
        )

    rows = generate_rows(
        sections,
        chunks,
        target_rows=target_rows,
        patient_rows=patient_rows,
    )
    rows = widen_duplicate_text_rows(rows, chunks)
    rows = widen_leaflet_intent_siblings(
        rows, {section["id"]: section for section in sections if section.get("id")}
    )

    required_groups = {
        "formulary",
        "leaflet",
        "chunk_risk",
        "multi_intent",
        "noisy",
        "table",
        "search_index",
        "chunk_window",
    }
    if patient_rows:
        required_groups.add("leaflet_short")
    validate_rows(
        rows,
        sections,
        chunks,
        min_rows=target_rows,
        max_rows=target_rows,
        required_groups=required_groups,
    )
    save_jsonl(output_path, rows)
    print(distribution_summary(rows, sections, chunks))
    return rows
