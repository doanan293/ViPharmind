import re

DEFAULT_TARGET_ROWS = 10000
DEFAULT_MIN_ROWS = DEFAULT_TARGET_ROWS
DEFAULT_MAX_ROWS = DEFAULT_TARGET_ROWS

DEFAULT_EVAL_GROUP_QUOTAS = {
    "formulary": 5000,
    "leaflet": 2500,
    "leaflet_short": 500,
    "chunk_risk": 1000,
    "multi_intent": 500,
    "noisy": 500,
}

FORMULARY_QUERY_FORM_TARGETS = {
    "lexical": 500,
    "template": 500,
    "paraphrase": 1500,
    "natural": 1500,
    "clinical": 1000,
}

NOISY_QUERY_FORM_TARGETS = {
    "noisy": 300,
    "typo": 200,
}

LEAFLET_QUERY_FORM_TARGETS = {
    "brand_template": 2000,
    "colloquial_alias": 500,
}

LEAFLET_ALIAS_ANSWER_MODE_TARGETS = {
    "single": 400,
    "any_acceptable": 100,
}

EVAL_HEADER = [
    "query_id",
    "query",
    "eval_group",
    "source_family",
    "query_form",
    "intent_category",
    "source_subcategory",
    "expected_section_id",
    "expected_section_ids",
    "query_intent_count",
    "answer_mode",
    "expected_title",
    "expected_chunk_id",
    "expected_chunk_index",
    "expected_chunk_role",
    "retrieval_granularity",
    "eval_tags",
    "notes",
]

ALLOWED_EVAL_GROUPS = set(DEFAULT_EVAL_GROUP_QUOTAS)
ALLOWED_SOURCE_FAMILIES = {
    "drug_formulary",
    "leaflet_brand",
    "general_appendix",
    "general_guidance",
}
ALLOWED_QUERY_FORMS = {
    "lexical",
    "template",
    "paraphrase",
    "natural",
    "clinical",
    "noisy",
    "typo",
    "leaflet_short",
    "brand_template",
    "colloquial_alias",
    "chunk_coverage",
    "multi_intent",
}
ALLOWED_INTENT_CATEGORIES = {
    "indication",
    "dosage",
    "contraindication",
    "adr",
    "interaction",
    "pregnancy_lactation",
    "ingredient",
    "precaution",
    "storage",
    "manufacturer",
    "pharmacology",
    "general_info",
    "overdose",
    "brand_lookup",
    "atc_lookup",
    "table_lookup",
    "guidance",
    "multi_intent",
}
ALLOWED_ANSWER_MODES = {"single", "multi_required", "any_acceptable"}
ALLOWED_RETRIEVAL_GRANULARITIES = {
    "section",
    "chunk_window",
    "chunk_exact",
    "multi_section",
}

FORMULARY_CATEGORY_MAP = {
    "indication": ("indication", "formulary_indication"),
    "contraindication": ("contraindication", "formulary_contraindication"),
    "dosage": ("dosage", "formulary_dosage"),
    "adr": ("adr", "formulary_adr"),
    "interaction": ("interaction", "formulary_interaction"),
    "pregnancy": ("pregnancy_lactation", "formulary_pregnancy_lactation"),
    "general_guidance": ("guidance", "formulary_guidance"),
    "atc_appendix": ("atc_lookup", "appendix_atc"),
    "brand_lookup": ("brand_lookup", "appendix_brand_index"),
    "table_lookup": ("table_lookup", "formulary_table"),
    "drug_fact": ("general_info", "formulary_general_info"),
    "overdose": ("overdose", "formulary_overdose"),
    "storage": ("storage", "formulary_storage"),
    "pharmacology": ("pharmacology", "formulary_pharmacology"),
    "precaution": ("precaution", "formulary_precaution"),
    "dosage_form": ("general_info", "formulary_dosage_form"),
}

LEAFLET_CATEGORY_MAP = {
    "brand_ingredient": ("ingredient", "leaflet_ingredient"),
    "brand_indication": ("indication", "leaflet_indication"),
    "brand_dosage": ("dosage", "leaflet_dosage"),
    "brand_contraindication": ("contraindication", "leaflet_contraindication"),
    "brand_adr": ("adr", "leaflet_adr"),
    "brand_precaution": ("precaution", "leaflet_precaution"),
    "brand_interaction": ("interaction", "leaflet_interaction"),
    "brand_pharmacology": ("pharmacology", "leaflet_pharmacology"),
    "brand_storage": ("storage", "leaflet_storage"),
    "brand_manufacturer": ("manufacturer", "leaflet_manufacturer"),
    "brand_product": ("general_info", "leaflet_product"),
}


def taxonomy_for_source_category(category: str, is_leaflet: bool) -> tuple[str, str]:
    mapping = LEAFLET_CATEGORY_MAP if is_leaflet else FORMULARY_CATEGORY_MAP
    return mapping.get(
        category,
        ("general_info", "leaflet_product" if is_leaflet else "formulary_general_info"),
    )


def source_family_for_section(section: dict) -> str:
    section_id = str(section.get("id") or "")
    content_type = str(section.get("content_type") or "")
    title = str(section.get("title") or "").lower()
    if content_type == "brand_page" or section_id.startswith("leaflet:"):
        return "leaflet_brand"
    if section_id.startswith("general:phu-luc") or "phụ lục" in title:
        return "general_appendix"
    if content_type == "general_monograph" or section_id.startswith("general:"):
        return "general_guidance"
    return "drug_formulary"


def retrieval_granularity_from_hydrate_strategy(
    strategy: str, chunk_role: str = ""
) -> str:
    if strategy == "chunk_window":
        return "chunk_window"
    if strategy == "search_only" or chunk_role in {"index_entry", "appendix_list"}:
        return "chunk_exact"
    return "section"


def answer_mode_for_expected_ids(
    expected_ids: list[str], multi_required: bool = False
) -> str:
    if multi_required:
        return "multi_required"
    if len(expected_ids) > 1:
        return "any_acceptable"
    return "single"


def normalize_eval_tags(tags: list[str] | set[str] | tuple[str, ...]) -> list[str]:
    return sorted({tag.strip() for tag in tags if tag.strip()})


def clean_query_label(value: str, max_chars: int = 72) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if text.count("|") >= 2 or re.search(r"\|\s*-{2,}\s*\|", text):
        return ""
    text = re.sub(r"(?m)^#{1,6}\s*", "", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"[*_`>]+", " ", text)
    text = text.replace("|", " ")
    text = re.sub(r"\s+", " ", text).strip(" -:;")
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    truncated = text[: max_chars + 1].rsplit(" ", 1)[0].strip(" -:;")
    if len(truncated) < 24:
        return ""
    return f"{truncated}..."
