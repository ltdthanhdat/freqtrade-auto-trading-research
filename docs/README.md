# Docs

Tài liệu của repo được tổ chức theo từng project docs thống nhất.

## Project docs

- `smc_fvg_pinbar/`
  - source of truth cho strategy `SMC_FVG_Confirmation`
  - bắt đầu đọc từ:
    - `smc_fvg_pinbar/README.md`
    - `smc_fvg_pinbar/state.md`

## Model tài liệu

- `state`
  - current truth
- `decisions`
  - keep/discard và nguồn gốc
- `roadmap`
  - phase hiện tại và thứ tự việc
- `hypotheses`
  - từng giả thuyết
- `experiments`
  - thiết kế bài test
- `runs`
  - raw result của từng lần chạy
- `notes`
  - debug note, blocker vận hành
- `reference`
  - cách chạy và setup

## Rule ngắn

- Không trộn `plan` và `result` trong cùng file.
- Không ghi raw backtest result vào `state.md`.
- Mỗi kết luận trong `state.md` nên truy ngược được về `decisions.md`.
- Mỗi decision nên truy ngược được về `hypothesis`, `experiment`, và `run`.
