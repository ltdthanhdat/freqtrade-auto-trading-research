# AGENTS

Rule ngắn cho `docs/`.

- Không trộn `roadmap`, `decision`, `state`, `run`, `note`, `reference` vào cùng một file.
- Mỗi project docs nên nằm trong `docs/<project_slug>/`.
- Mỗi project docs phải có `README.md`.
- Luồng chuẩn:
  - `hypothesis` -> `experiment` -> `run` -> `decision` -> `state`
- Vai trò:
  - `state.md`
    - current truth
  - `decisions.md`
    - keep/discard, source links
  - `roadmap.md`
    - phase hiện tại, open hypotheses, next step
  - `hypotheses/`
    - từng giả thuyết một file
  - `experiments/`
    - thiết kế verify cho một hypothesis hoặc một case
  - `runs/`
    - raw output và metrics
  - `notes/`
    - debug / blocker
  - `reference/`
    - setup / runbook
- Khi có kết quả mới:
  - append vào `runs/`
  - update `decisions.md` nếu có keep/discard
  - update `state.md` nếu current truth đổi
