# SMC FVG PinBar Tuning Plan

## Goal

- target window:
  - `2026-02-18` -> `2026-05-18`
- target market:
  - current basket `9` pairs
- target trade model:
  - `RR = 1:1`
  - stop theo biên `FVG` hiện tại
  - risk sizing giữ ở config
- success criteria:
  - `win_rate >= 65%`
  - stretch target `70% - 75%`
  - `net_profit_pct > 0`
  - `profit_factor >= 1.2`
  - `max_drawdown_pct <= 12%`
  - `trades_count >= 45`
  - target cadence:
    - khoảng `1` lệnh mỗi `1-2` ngày
    - tương đương khoảng `45-90` lệnh / `90` ngày với `max_open_trades = 1`

## Scope

- chỉ tune logic entry / filter / basket selection
- không đổi execution mode
- không đổi docs flow hiện tại của `docs/smc_fvg_pinbar`
- mỗi vòng chỉ đổi `1` ý

## Current baseline

- current strategy:
  - `SMC_FVG_Confirmation_Freqtrade`
- current assumptions:
  - `RR = 1:1`
  - leverage `5x`
  - risk per trade `5%`
  - capital cap `25%`
  - `max_open_trades = 1`
- latest observed issue:
  - clean baseline full window ngày `2026-05-18`:
    - `trades_count = 89`
    - `win_rate = 62.9%`
    - `net_profit_pct = 164.41%`
    - `profit_factor = 1.97`
    - `max_drawdown_pct = 10.74%`
  - trạng thái:
    - profit, cadence, profit factor đã vượt target
    - drawdown đã vào target
    - win rate còn thiếu khoảng `2.1` điểm

## Tuning loop

1. seed lại đúng data full range `2026-02-18` -> `2026-05-18`
   verify:
   - đủ `1h futures` cho toàn bộ `9` pairs
   - backtest không còn warning data start bị trễ
2. chạy baseline sạch, lưu run gốc
   verify:
   - có `trades_count`, `win_rate`, `net_profit_pct`, `max_drawdown_pct`, `profit_factor`
3. mở `1` hypothesis
   verify:
   - hypothesis chỉ chạm `1` biến
4. viết `1` experiment tương ứng
   verify:
   - có rõ compare case `before/after`
5. backtest
   verify:
   - cùng timerange
   - cùng basket nếu chưa bước sang phase basket pruning
6. quyết định `keep` hoặc `discard`
   keep khi:
   - `win_rate` tăng có ý nghĩa
   - không làm `net_profit_pct` âm
   - không làm `max_drawdown_pct` xấu quá mức
   discard khi:
   - tăng win rate nhưng payoff xấu hơn rõ
   - giảm trade count quá mạnh
   - cải thiện nhỏ nhưng thêm logic phức tạp
7. cập nhật docs flow chuẩn
   - `hypotheses/`
   - `experiments/`
   - `runs/`
   - `decisions.md`
   - `state.md`

## Phase plan

### Phase 0 - Rebuild clean baseline

- goal:
  - có baseline sạch cho 3 tháng gần nhất
- test:
  - seed full range
  - backtest exact basket hiện tại
- keep:
  - khi run lặp lại được
- discard:
  - mọi kết luận từ run thiếu data

### Phase 1 - Remove unnecessary complexity first

- goal:
  - loại bớt phần không giúp win rate / expectancy
  - nhưng không được làm trade frequency tụt dưới target
- test order:
  1. `signal_kind` split:
     - `pin_bar` only
     - `trend_body` only
     - `displacement` only
  2. bỏ các signal yếu:
     - discard signal nào có `win_rate` thấp và kéo profit xuống
  3. compare `long only`, `short only`, `long + short`
- keep:
  - chỉ giữ signal side nào đóng góp rõ cho target
  - không làm cadence rơi dưới khoảng `1` lệnh / `2` ngày
- discard:
  - signal side nào không đóng góp hoặc làm DD xấu
  - signal side nào làm trade count tụt mạnh

### Phase 2 - Tighten entry quality

- goal:
  - tăng win rate bằng cách làm entry khó hơn
- test order:
  1. `PIN_BAR_BODY_RATIO`
  2. `PIN_BAR_WICK_TO_BODY`
  3. `PIN_BAR_CLOSE_EXTREME_RATIO`
  4. `FVG_RETRACE_RATIO`
  5. `FVG_CONFIRM_RATIO`
- rule:
  - mỗi lần chỉ đổi `1` threshold
  - ưu tiên threshold nào giảm stop-hit nhiều nhất
- keep:
  - threshold nào tăng `win_rate` và giữ `trades_count >= 45`
- discard:
  - threshold nào làm trade quá ít hoặc overfit rõ

### Phase 3 - Add simple confirmation filters

- goal:
  - chỉ thêm filter nếu Phase 1 và 2 chưa đạt target
- allowed additions:
  - trend filter đơn giản:
    - EMA bias hoặc market structure bias
  - volatility floor:
    - bỏ kèo range quá hẹp
  - session filter:
    - bỏ giờ chết nếu có evidence
- not allowed:
  - nhiều indicator chồng lớp
  - ML
  - position adjustment
  - trailing phức tạp
- keep:
  - filter nào nâng `win_rate` và không phá `profit_factor`
  - vẫn giữ cadence trong target
- discard:
  - filter thêm code nhiều nhưng edge nhỏ
  - filter làm setup hiếm quá mức

### Phase 4 - Basket pruning

- goal:
  - bỏ pair kém chất lượng
- test order:
  1. xếp hạng pair theo:
     - `net_profit_pct`
     - `win_rate`
     - `profit_factor`
     - stop-loss frequency
  2. loại `1` pair tệ nhất mỗi vòng
  3. re-backtest full basket sau mỗi lần loại
- keep:
  - pair nào đóng góp dương hoặc giúp diversification thật
- discard:
  - pair lỗ đều, stop-hit nhiều, hoặc variance quá xấu

### Phase 5 - Capital tuning last

- goal:
  - chỉ sau khi signal edge đủ tốt mới tune vốn
- test order:
  1. `risk_per_trade`: `2%`, `3%`, `4%`, `5%`
  2. `capital_cap`: `10%`, `15%`, `20%`, `25%`
  3. leverage:
     - `1x`
     - `2x`
     - `3x`
     - `5x`
- keep:
  - preset nào giữ edge và kéo DD về target
- discard:
  - preset nào chỉ làm PnL lớn hơn nhưng DD xấu tương ứng

## Test matrix priority

- priority `A`:
  - seed full 3 months
  - baseline clean run
  - baseline cadence check
  - signal split
  - long vs short split
- priority `B`:
  - entry threshold tuning
  - pair pruning
- priority `C`:
  - simple confirmation filters
  - capital tuning

## Decision rules

- keep nếu đồng thời đạt:
  - `win_rate` tăng ít nhất `+5` điểm hoặc chạm target
  - `profit_factor` không giảm dưới `1.1`
  - `net_profit_pct` vẫn dương
  - `trades_count >= 45`
- discard nếu có một trong các dấu hiệu:
  - `trades_count < 45`
  - `max_drawdown_pct > 15%` mà win rate không tăng rõ
  - chỉ cải thiện trên `1` pair, không cải thiện ở basket level

## Stop conditions

- dừng tuning khi:
  - đạt `win_rate >= 65%`
  - `net_profit_pct > 0`
  - `trades_count >= 45`
  - hoặc sau `10` vòng mà edge không tiến triển, cần đổi thesis

## Current assessment

- chưa đạt target chính thức
- nhưng snapshot hiện tại đã `near target`
- thesis tiếp theo có ưu tiên cao nhất:
  - `basket pruning`
  - lý do:
    - pair âm hiện tại tập trung ở `BTC`, `D`
    - không cần thêm logic entry mới

## Deliverables per round

- `1` hypothesis file
- `1` experiment file
- `1` run file
- update `decisions.md`
- update `state.md` nếu current truth đổi

## First 5 rounds

1. rebuild baseline full range `2026-02-18` -> `2026-05-18`
2. backtest `pin_bar only`
3. backtest `trend_body only`
4. backtest `displacement only`
5. backtest `short only` vs `long only`
