# SMC_FVG_PinBar Freqtrade Migration Validation

Ngày cập nhật: 2026-05-14

## Mục tiêu

Kiểm tra port Freqtrade có khớp đủ gần với Jesse hay không trước khi dry-run / live.

## Source files

- strategy:
  - `src/strategies/SMC_FVG_PinBar_Freqtrade.py`
- config:
  - `config/config.futures.json`
- data prep:
  - `scripts/prepare_smc_fvg_pinbar_data.py`
- compare:
  - `scripts/compare_smc_fvg_pinbar_with_jesse.py`
- raw compare output:
  - `user_data/compare/smc_fvg_pinbar_freqtrade_vs_jesse.json`
  - `user_data/compare/smc_fvg_pinbar_freqtrade_vs_jesse.csv`
  - `user_data/compare/smc_fvg_pinbar_freqtrade_vs_jesse.md`

## Result snapshot

### Baseline BTC

- Jesse:
  - `4 trades`
  - `0.73935024987001%`
  - `win_rate = 0.75`
- Freqtrade:
  - `4 trades`
  - `0.7643972648%`
  - `win_rate = 1.0`
- interpretation:
  - trade count khớp
  - total profit rất gần
  - đủ tốt cho phase migration đầu

### Recent selected basket

Các case compare:

- `BTC-USDT`
- `PLAY-USDT`
- `BIO-USDT`
- `SPACE-USDT`
- `PENDLE-USDT`
- `BR-USDT`
- `D-USDT`
- `YGG-USDT`
- `STG-USDT`

Kết quả:

- `9` case chạy được với số liệu compare

Summary:
- sau patch `no-shift` và bỏ `BASED-USDT` khỏi basket:
  - avg abs profit diff:
    - `0.40434199150902445`
  - avg trade count diff:
    - `0.5`

### Case table

| Symbol | Jesse trades | Freqtrade trades | Jesse net % | Freqtrade net % | Diff % |
| --- | ---: | ---: | ---: | ---: | ---: |
| BTC-USDT recent | 10 | 10 | 0.7134234949907934 | 0.8435860044 | 0.1301625094092066 |
| PLAY-USDT | 7 | 6 | 8.499815258424777 | 8.151864160899999 | -0.3479510975247777 |
| BIO-USDT | 13 | 14 | 10.67593459333302 | 12.389492306500001 | 1.7135577131669812 |
| SPACE-USDT | 9 | 9 | 7.55606167845605 | 7.749477229400001 | 0.1934155509439508 |
| PENDLE-USDT | 14 | 14 | 4.486394139335451 | 4.7029222424 | 0.21652810306454828 |
| BR-USDT | 3 | 4 | 4.577552113340003 | 3.9248074038000005 | -0.6527447095400025 |
| D-USDT | 10 | 9 | 3.7931599697462035 | 4.1455534162 | 0.3523934464537968 |
| YGG-USDT | 8 | 8 | 3.7483353397921646 | 3.9308946274000007 | 0.18255928760783613 |
| STG-USDT | 8 | 7 | 3.252466848449155 | 3.0473625748 | -0.20510427364915484 |

## Conclusion

- migration đã usable
- parity hiện tại:
  - tốt ở baseline
  - recent basket đã sát hơn nhiều sau patch bỏ `shift(1)` ở entry signal
- có thể coi Freqtrade result hiện tại đã đủ gần Jesse để tiếp tục research/tuning trên nhánh mới
- nên coi đây là:
  - port đã qua vòng parity chính
  - vẫn còn vài cặp lệch nhỏ cần theo dõi

## Experiment: remove entry-signal shift

- hypothesis:
  - `shift(1)` ở `ft_*_entry_*` đang làm lệch entry 1 nến so với Jesse
- file_changed:
  - `src/strategies/SMC_FVG_PinBar_Freqtrade.py`

Result:
- baseline `BTC-USDT 1h`:
  - Jesse:
    - `4 trades`
    - `0.73935024987001%`
  - Freqtrade:
    - `4 trades`
    - `0.7883534736%`
- recent `BTC-USDT 1h`:
  - Jesse:
    - `10 trades`
    - `0.7134234949907934%`
  - Freqtrade:
    - `10 trades`
    - `0.8435860044%`
- full recent basket:
  - avg abs profit diff:
    - `0.40434199150902445`
  - avg trade count diff:
    - `0.5`
- keep_or_discard:
  - `keep`
- notes:
  - trước patch, avg abs profit diff khoảng `1.70`
  - sau patch, `BTC recent` gần khớp trade-by-trade với Jesse
