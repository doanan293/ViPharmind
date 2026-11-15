# Đánh giá: guide theo golden v4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Trạng thái (2026-11-15):** chưa bắt đầu. Các ablation còn dở (D2, D4, D5) phục vụ paper v2, đã bỏ
cùng paper v2; thiết kế của chúng còn ở mục lịch sử của spec.

**Goal:** Hai guide của pharma-lab mô tả đúng golden v4 đang dùng.

**Architecture:** Chỉ sửa tài liệu, không đổi mã.

**Tech Stack:** Markdown.

**Spec:** `docs/superpowers/specs/2026-11-15-evaluation-design.md` (mục 3.6).

## Global Constraints

- Số liệu lấy từ `pharma_lab/e2e/golden.py` và mục 3.6 của spec, không lấy từ guide cũ.
- Commit không thêm dòng ghi công AI.

## Review Focus

- Dòng lịch sử nói về golden v1 (500 câu) vẫn được giữ, chỉ sửa chỗ tả golden hiện hành.

---

### Task 1: Guide khớp golden v4

**Files:**
- Modify: `pharma-lab/docs/guides/e2e-evaluation.md` (câu mở đầu "bộ golden 500 câu"; ví dụ tên run
  `e2e-v2-*` chuyển sang `e2e-v4-*`; đoạn "Cặp model được chọn từ bảng retrieval v2... không cố định
  trước" thay bằng cặp đã chốt)
- Modify: `pharma-lab/docs/guides/e2e-golden-authoring.md` (mục multi_hop còn tả 150 câu và loại
  `retrieval_miss`, `noisy_retry`; mục answerable còn 30 mỗi nhóm, colloquial 20, glossary 10; lát 60;
  multi-turn 50 với quota 7/7/6; đoạn "Golden chỉ dùng cho run e2e khi lệnh trả `complete`")

- [ ] **Step 1:** Sửa mọi con số theo `ANSWERABLE_GROUP_QUOTAS`, `SLICE_QUOTAS`, `MULTI_TURN_QUOTAS`,
  `MULTI_HOP_QUOTAS` trong `pharma_lab/e2e/golden.py` và mục 3.6 của spec. Đoạn dược sĩ: ghi rằng
  golden v4 dùng cho run e2e sau hai vòng duyệt bằng model, lệnh `pharmacist-*` dành cho vòng duyệt
  dược sĩ đầy đủ nếu có (sửa theo câu trả lời của An, xem ghi chú).
- [ ] **Step 2:** `grep -n "500 câu\|150 câu\|retrieval_miss\|noisy_retry\|pronoun 7" pharma-lab/docs/guides/*.md`
  Expected: không còn dòng nào tả golden hiện hành bằng số cũ (dòng lịch sử ghi rõ "golden v1" thì được giữ).
- [ ] **Step 3: Commit** `docs(pharma-lab): guides describe golden v4`
