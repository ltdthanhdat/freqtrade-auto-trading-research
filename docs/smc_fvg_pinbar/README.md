# SMC_FVG_PinBar Docs

Source of truth cho strategy `SMC_FVG_Confirmation` trên Freqtrade.

## Đọc theo thứ tự

1. `state.md`
2. `decisions.md`
3. `roadmap.md`

Nếu cần truy ngược lý do:

1. `decisions.md`
2. `hypotheses/`
3. `experiments/`
4. `runs/`

## Cấu trúc

- `state.md`
  - current truth của strategy
- `decisions.md`
  - decision log keep/discard
- `roadmap.md`
  - phase hiện tại và next execution step
- `hypotheses/`
  - từng hypothesis riêng
- `experiments/`
  - test design và phạm vi verify
- `runs/`
  - raw run log
- `notes/`
  - debug note và blocker vận hành
- `reference/`
  - setup và runbook

## Trace model

```text
hypothesis -> experiment -> run -> decision -> state
```

## Current entry points

- current state:
  - `state.md`
- current active roadmap:
  - `roadmap.md`
- current accepted decision:
  - `decisions.md`
