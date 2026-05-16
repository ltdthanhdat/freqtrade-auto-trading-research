# Blockers

## Known blockers and caveats

- Pair futures phải đúng format Freqtrade:
  - dùng:
    - `BTC/USDT:USDT`
  - không dùng:
    - `BTC-USDT`

- Timeframe seed nên luôn có:
  - `1m`
  - `1h`

- Futures metadata có thể là blocker ở một số pair:
  - nếu download lỗi metadata:
    - bỏ pair đó khỏi preset
    - không workaround bằng nguồn data ngoài
