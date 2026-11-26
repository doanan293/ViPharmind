# Viết lại lịch sử theo tính năng

`rewrite.py` dựng một nhánh mới từ lịch sử riêng của một nhánh cũ: mỗi đoạn commit liên tiếp cùng chủ đề thành
một commit, rồi phát lại các commit làm sạch phía sau. Chỉ ghi object và đúng một ref `refs/heads/<branch>`;
không đụng working tree, không đụng nhánh nào khác, không push.

## Cách làm

1. Đi first-parent `fork..old_ref`. Mỗi commit được phân loại: `app` nếu đa số file sửa nằm trong `backend/`,
   `frontend/`, `compose*`, `devops/`, `scripts/`; còn lại là `research`. Phạm vi lấy từ tiêu đề conventional
   commit (`feat(chat): ...` cho `chat`), không có thì lấy thư mục cấp hai bị sửa nhiều nhất (bỏ qua tên chung như
   `src`, `tests`, `docs`, `app` thì lấy thư mục cấp một).
2. Commit liên tiếp cùng loại và phạm vi gộp thành một đoạn. Commit merge không được phân loại hay liệt kê; thay
   đổi của nó (so với cha thứ nhất) gộp vào đoạn đứng trước.
3. `--reorder`: một đoạn được kéo lên sát đoạn cùng loại và phạm vi gần nhất phía trước rồi gộp vào, chỉ khi nó
   không sửa file nào mà các đoạn bị nhảy qua đã sửa. Có xung đột file thì giữ nguyên thứ tự.
4. Mỗi đoạn thành `feat(<phạm vi>): <tóm tắt>` (app) hoặc `docs(<phạm vi>): <tóm tắt>` (research), thân liệt kê
   tiêu đề các commit cũ đã gộp. Tác giả, người commit và ngày lấy từ commit cũ cuối cùng của đoạn.
5. Phát lại từng commit first-parent của `tail_base..tail_ref` với cây của chính nó và message cũ.

Nếu `fork` không nằm trên chuỗi first-parent của `old_ref` (nhánh cũ merge `fork` vào về sau), các commit cũ hơn
được dựng lại trên `fork` bằng merge 3 chiều; file xung đột lấy nguyên bản của nhánh cũ cho tới khi commit merge
cũ áp cách giải xung đột của nó.

## Chạy

```bash
uv run python devops/history/rewrite.py --repo . --fork 3f0a46d --old-ref <ref cũ> \
  --tail-base <ref cũ> --tail-ref clean --branch v2-new [--reorder]
uv run --with pytest pytest devops/history -q
```

In ra bảng: SHA mới, số commit cũ đã gộp, tiêu đề.

## Bảo đảm (công cụ dừng với lỗi nếu sai)

- Cây cuối của nhánh mới giống hệt cây của `tail_ref`; cây sau đoạn cuối giống hệt cây của `old_ref`.
- `fork` giữ nguyên và là cha của commit mới đầu tiên.
- Mỗi đoạn được dựng bằng cách áp diff cũ lên chỉ mục tạm; diff nào không áp đúng trạng thái hiện tại thì dừng.
  Không sắp xếp lại thì cây mỗi đoạn bằng cây của commit cũ cuối đoạn (sau khi dựng lại trên `fork`).
- Chạy lại cho cùng SHA, bất kể tên nhánh.
- Message không có dòng ghi công AI (`Co-Authored-By` của Claude và các công cụ AI khác bị bỏ).
- Không ghi đè nhánh đang được checkout ở worktree nào.
