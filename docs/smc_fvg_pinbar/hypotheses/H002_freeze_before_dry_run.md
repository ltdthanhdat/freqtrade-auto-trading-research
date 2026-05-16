# H002 - Nên freeze threshold trước khi mở rộng tuning tiếp

## Question

- Có nên dừng tuning và chuyển sang `dry-run` để xác minh execution trước không?

## Why this matters

- Nếu data flow hoặc execution flow chưa ổn định, tuning thêm sẽ khó tin cậy.

## Success criteria

- có một threshold chấp nhận được để freeze
- flow seed và backtest đã chạy ổn
- dry-run trở thành bước verify tiếp theo hợp lý hơn tuning

## Linked experiments

- `E003`

## Status

- `confirmed`

## Final decision

- xem `D002`
