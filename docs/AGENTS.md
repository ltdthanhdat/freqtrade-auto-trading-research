# AGENTS

Rule ngắn khi cập nhật docs trong `freqtrade-template/docs`.

- Không trộn `plan`, `state`, `notes`, `research`, `reference` vào cùng một file.
- `state/` chỉ giữ kết luận working state hiện tại.
- `research/` giữ số liệu và kết quả compare đủ để kiểm tra lại.
- `notes/` giữ phát hiện kỹ thuật, bug, khác biệt engine.
- Khi một experiment làm đổi hướng làm việc, update cả:
  - `state/`
  - `research/`
- Không sửa lại lịch sử Jesse cũ trong repo root chỉ để “đồng bộ wording”.
