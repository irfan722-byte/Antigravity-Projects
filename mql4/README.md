# Fair Value Range EA — XAUUSD / M15

`FairValueRange_XAUUSD.mq4` is an MQL4 Expert Advisor implementing Patrick Nil's
**Fair Value Range** strategy, tuned for Gold (XAUUSD) on the 15‑minute chart.

## Installation
1. Copy `FairValueRange_XAUUSD.mq4` into your terminal's `MQL4/Experts/` folder.
2. In MetaEditor, open the file and press **Compile** (F7). It targets MT4 build 600+.
3. Attach the EA to an **XAUUSD, M15** chart and allow live/auto trading.

## Strategy pipeline
1. **Impulse detection** — a "P"/"B" formation is flagged when net displacement over
   1–3 candles exceeds `ImpulseATRmult × ATR(14)`.
2. **Range validation** — the lateral consolidation box is mapped from `High[]`/`Low[]`
   and only enabled once **≥ `FractalTouchesReq` (3)** distinct M15 swing highs and lows
   confirm the upper and lower boundaries.
3. **Range mode** — `OP_BUYLIMIT` at the lower boundary, `OP_SELLLIMIT` at the upper.
4. **Breakout mode** — a state machine that ignores the initial breakout candle, waits for
   a close outside the zone, a retrace back to the boundary exterior, and a fresh fractal,
   then arms `OP_BUYSTOP` / `OP_SELLSTOP` just beyond that fractal.
5. **Targeting** — TP is the nearest historical consolidation zone; at all‑time highs the
   measured impulse distance is projected outward from entry instead.

## Risk & safeguards
- **Position sizing** risks exactly `RiskPercent` (default **5%**) of `AccountEquity()`,
  mapped against Gold's tick value, normalized to `MODE_LOTSTEP`, and validated with
  `AccountFreeMarginCheck()` to avoid margin rejections.
- **R:R enforcer** aborts any trade below a **1:3** reward‑to‑risk ratio.
- **SL lockdown** — `OrderModify()` may only move the stop to break‑even or into profit;
  widening attempts are rejected.
- **Daily circuit breakers** suspend trading until broker midnight after 3 consecutive
  closed losses or a 15% daily equity drawdown, scoped by `MagicNumber`.
- **Volatility filters** — `MaxSpreadPoints` gate and a hardcoded slippage buffer on
  `OrderSend()`. All price math uses `Point`/`Digits` for 2‑ vs 3‑digit Gold feeds.

## Key inputs
| Input | Default | Purpose |
|-------|---------|---------|
| `RiskPercent` | 5.0 | Equity risked per trade |
| `MinRR` | 3.0 | Minimum reward:risk |
| `ATR_Period` / `ImpulseATRmult` | 14 / 1.8 | Impulse sensitivity |
| `FractalTouchesReq` | 3 | Boundary touches required |
| `MaxSpreadPoints` | 30 | Spread gate |
| `SlippagePoints` | 20 | Order slippage buffer |
| `DailyLossPercent` | 15 | Daily drawdown breaker |
| `MaxConsecLosses` | 3 | Consecutive‑loss breaker |

> Backtest and forward‑test on a demo account before any live use. A 5% per‑trade risk
> setting is aggressive by design — size it to your own tolerance.
