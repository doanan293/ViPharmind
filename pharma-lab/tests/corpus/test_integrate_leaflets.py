from pathlib import Path

from pharma_lab.corpus.crawling.integrate_leaflets import (
    heading_slug,
    integrate_drug_file,
    separate_leaflet_heading_runs,
    split_leaflet_sections,
)

PAGE = (
    "# Abanuti 1 g trị thiếu Carnitine (20 ống x 10 ml)\n\n"
    "### 1. Thành phần\n\nLevocarnitin 1,0 g.\n\n"
    "### 2. Công dụng (Chỉ định)\n\nThiếu hụt carnitine.\n\n"
    "### 3. Cách dùng - Liều dùng\n\nNgười lớn 1 đến 3 g/ngày.\n\n"
    "#### - Quá liều\n\nCó thể gây tiêu chảy.\n\n"
    "### 4. Lưu ý\n\nTheo dõi carnitin huyết tương.\n\n"
    "### 5. Lưu ý\n\nKhông dùng đường tiêm.\n"
)


def test_split_gives_level_four_items_their_own_part() -> None:
    parts = split_leaflet_sections(PAGE)
    assert [part.heading for part in parts] == [
        "Thành phần",
        "Công dụng (Chỉ định)",
        "Cách dùng - Liều dùng",
        "Quá liều",
        "Lưu ý",
        "Lưu ý",
    ]
    assert (
        parts[2].markdown == "### 3. Cách dùng - Liều dùng\n\nNgười lớn 1 đến 3 g/ngày."
    )
    assert parts[3].markdown == "#### - Quá liều\n\nCó thể gây tiêu chảy."


def test_split_without_headings_returns_one_general_part() -> None:
    parts = split_leaflet_sections("# Thuốc X\n\nChỉ một đoạn mô tả.")
    assert len(parts) == 1
    assert parts[0].heading == "Thông tin chi tiết"
    assert parts[0].markdown == "Chỉ một đoạn mô tả."


def test_split_keeps_text_before_first_heading_as_general_part() -> None:
    parts = split_leaflet_sections(
        "# Thuốc X\n\nMô tả chung.\n\n### 1. Thành phần\n\nA 1 mg."
    )
    assert [part.heading for part in parts] == ["Thông tin chi tiết", "Thành phần"]


def test_heading_slug_strips_numbering_and_dashes() -> None:
    assert heading_slug("3. Cách dùng - Liều dùng") == "cach-dung-lieu-dung"
    assert heading_slug("- Bảo quản") == "bao-quan"


def test_integrate_drug_file_emits_one_section_per_heading(tmp_path: Path) -> None:
    root = tmp_path / "md"
    (root / "thuoc-bo").mkdir(parents=True)
    (root / "thuoc-bo" / "abanuti-1g.md").write_text(PAGE, encoding="utf-8")
    sections = integrate_drug_file(
        root / "thuoc-bo" / "abanuti-1g.md", markdown_root=root, mappings={}
    )
    assert [section["id"] for section in sections] == [
        "leaflet:thuoc-bo:abanuti-1g:01-thanh-phan",
        "leaflet:thuoc-bo:abanuti-1g:02-cong-dung-chi-dinh",
        "leaflet:thuoc-bo:abanuti-1g:03-cach-dung-lieu-dung",
        "leaflet:thuoc-bo:abanuti-1g:04-qua-lieu",
        "leaflet:thuoc-bo:abanuti-1g:05-luu-y",
        "leaflet:thuoc-bo:abanuti-1g:06-luu-y",
    ]
    first = sections[0]
    assert first["page_id"] == "leaflet:thuoc-bo:abanuti-1g"
    assert first["section"] == "Thành phần"
    assert first["context_path"] == ["Thành phần"]
    assert first["context_header"] == (
        "Abanuti 1 g trị thiếu Carnitine (20 ống x 10 ml)\n> Thành phần"
    )
    assert first["text"].startswith(
        "# Abanuti 1 g trị thiếu Carnitine (20 ống x 10 ml)\n\n### 1. Thành phần"
    )
    assert first["colloquial_mapping"] == sections[1]["colloquial_mapping"]
    assert "hydrate_strategy" not in first and "section_char_count" not in first


def test_parent_without_own_text_is_dropped(tmp_path: Path) -> None:
    root = tmp_path / "md"
    (root / "thuoc").mkdir(parents=True)
    (root / "thuoc" / "x.md").write_text(
        "# Thuốc X\n\n### 1. Thành phần\n\nA 1 mg.\n\n"
        "### 5. Lưu ý\n\n#### - Tương tác thuốc\n\nTránh rượu.",
        encoding="utf-8",
    )
    sections = integrate_drug_file(
        root / "thuoc" / "x.md", markdown_root=root, mappings={}
    )
    assert [section["section"] for section in sections] == [
        "Thành phần",
        "Tương tác thuốc",
    ]


def test_heading_run_separator_keeps_level_four_headings_whole() -> None:
    text = (
        "### 7. Thông tin thêm\n\n#### - Bảo quản\n\nDưới 30 độ C.- Hạn dùngXem bao bì."
    )
    cleaned = separate_leaflet_heading_runs(text)
    assert "#### - Bảo quản\n" in cleaned
    assert not any(line.strip() == "####" for line in cleaned.splitlines())
    assert "\n- Hạn dùng\nXem bao bì." in cleaned


def test_product_info_items_stay_in_one_section() -> None:
    page = (
        "# Thuốc X\n\n### 6. Tác dụng phụ\n\nBuồn nôn.\n\n"
        "### 7. Thông tin thêm\n\n#### - Đặc điểm\n\nViên nén.\n\n"
        "#### - Bảo quản\n\nDưới 30 độ C.\n\n#### - Hạn dùng\n\n24 tháng.\n\n"
        "#### - Nhà sản xuất\n\nDHG."
    )
    parts = split_leaflet_sections(page)
    assert [part.heading for part in parts] == ["Tác dụng phụ", "Thông tin thêm"]
    assert "#### - Hạn dùng\n\n24 tháng." in parts[1].markdown
    assert parts[1].markdown.endswith("#### - Nhà sản xuất\n\nDHG.")
