# Run - Binance Demo Freqtrade Validation

- ngày:
  - `2026-05-17`
- scope:
  - validate API key Binance demo futures với stack `Freqtrade + CCXT`

## Hypothesis

- key Binance demo futures trade được qua `Freqtrade`
- config cần đủ để đi đúng `demo-fapi.binance.com`

## Setup

- config:
  - `config/config.futures.demo.local.json`
- pair:
  - `BTC/USDT:USDT`
- timeframe:
  - `1h`

## Run

1. CCXT script:
   - auth `ok`
   - `balance_usdt_total = 5000.0`
   - tạo limit order test
   - cancel thành công
2. Freqtrade exchange layer:
   - khi chỉ dùng `enableDemoTrading = true`
   - fail ở `additional_exchange_init`
   - request vẫn đi `fapi.binance.com`
3. Freqtrade exchange layer sau khi override `urls.api.fapi*`:
   - `balance_usdt_total = 5000.0`
   - tạo order `13152712933`
   - `cancel_status = canceled`
4. Freqtrade `trade` command:
   - strategy load được
   - worker lên trạng thái `RUNNING`
   - không crash trước khi dừng tay

## Result

- hypothesis:
  - `keep`
- ghi chú:
  - với stack hiện tại, `enableDemoTrading` một mình chưa đủ cho path futures của `Freqtrade`
  - cần override explicit `fapi` demo URLs trong `ccxt_config` và `ccxt_async_config`
