# Run - Binance Demo Freqtrade Validation

- date:
  - `2026-05-17`
- scope:
  - validate Binance demo futures API key with the `Freqtrade + CCXT` stack

## Hypothesis

- Binance demo futures key can trade through `Freqtrade`
- config must be sufficient to route requests to `demo-fapi.binance.com`

## Setup

- config:
  - `config/config.futures.json`
  - `config/config.binance.demo.json`
- pair:
  - `BTC/USDT:USDT`
- timeframe:
  - `1h`

## Run

1. CCXT script:
   - auth `ok`
   - `balance_usdt_total = 5000.0`
   - created a test limit order
   - cancelled successfully
2. Freqtrade exchange layer:
   - when using only `enableDemoTrading = true`
   - failed at `additional_exchange_init`
   - requests still went to `fapi.binance.com`
3. Freqtrade exchange layer after overriding `urls.api.fapi*`:
   - `balance_usdt_total = 5000.0`
   - created order `13152712933`
   - `cancel_status = canceled`
4. Freqtrade `trade` command:
   - strategy loaded successfully
   - worker reached `RUNNING` state
   - no crash before manual stop

## Result

- hypothesis:
  - `keep`
- notes:
  - with the current stack, `enableDemoTrading` alone is not sufficient for the `Freqtrade` futures path
  - explicit override of `fapi` demo URLs in `ccxt_config` and `ccxt_async_config` is required
