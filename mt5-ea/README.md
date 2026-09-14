# IRONWALL HEDGE v3 — MT5 Expert Advisor

An MT5 Expert Advisor (`IronwallHedge.mq5`) implementing a **moving-grid
martingale** hedge strategy on XAUUSD (Gold).

> **This is a martingale with no per-trade stop. Read the risk section.**

---

## Strategy (as specified)

1. **First trade:** market **BUY** at the base lot (`0.01`). Its price is the
   cycle **anchor**.
2. **The grid follows price.** Each time price extends one more grid step
   (`$2`) beyond the furthest level already traded, a new doubled lot is added
   **in the direction of the move**:
   - a new step **up** → add a **BUY**
   - a new step **down** → add a **SELL**
   Lots: `0.01 → 0.02 → 0.04 → 0.08 → 0.16 …`. It keeps adding as price keeps
   moving — it does **not** freeze — until the basket turns net profit.
3. **Basket exit:** the combined floating P/L of all trades is watched. At the
   **trail-start** target (`$2`) a trailing lock arms; if profit then drops by
   the **trail gap** (`$1`) from its peak, **all trades close**.
4. **MANDATORY account stop:** if the basket's floating loss reaches
   `StopLossPct` of the account balance (**default 50%**), everything closes.
5. **Restart:** on any close (profit or stop), a new cycle starts immediately
   at the current price. **No spread filter.**

---

## Installation

1. Copy `IronwallHedge.mq5` into `MQL5/Experts/` (MetaTrader: *File → Open
   Data Folder*).
2. In **MetaEditor**, press **F7** to compile (standard `Trade` library only).
3. Drag onto an **XAUUSD** chart, enable **Algo Trading**.
4. **Backtest on a demo account first.**

## Inputs

| Input | Default | Meaning |
|-------|---------|---------|
| `InpMagic` | 490051 | Magic number |
| `InpComment` | IronwallHedge | Order comment |
| `InpSlippage` | 50 | Max slippage (points) |
| `InpStartDir` | START_BUY | First trade direction |
| `InpInitialLot` | 0.01 | Base (first) lot |
| `InpLotMultiplier` | 2.0 | Lot multiplier per new entry |
| `InpMaxLot` | 100.0 | Hard cap on any single order lot |
| `InpGridStepPrice` | 2.0 | Grid step, in price ($2) |
| `InpMaxLevels` | 100 | Absolute max entries per cycle |
| `InpTrailStartMoney` | 2.0 | Arm trailing when basket profit ≥ this (money) |
| `InpTrailGapMoney` | 1.0 | Close if profit drops this much from peak |
| `InpStopLossPct` | 50.0 | **Mandatory** — close basket at this % floating loss of balance |
| `InpShowPanel` | true | On-chart status panel |
| `InpDrawLines` | true | Draw next buy/sell trigger lines |

> `InpGridStepPrice` is in **price** ($2), not points — no digit confusion.

---

## Risk — read this

- **The account stop is what happened in your screenshot, done deliberately.**
  A martingale cannot "always turn net profit" on a finite account — to keep
  adding through a $30 trend you'd need lots (0.64, 1.28, 2.56 …) your balance
  can't fund, and margin runs out. The `StopLossPct` floor closes the basket
  at a controlled loss **instead of letting the broker stop you out at zero**.
  Removing it does not make the strategy safe — it just removes the floor.
- **Small target, large risk.** You risk up to ~50% of the account to make
  ~$1–2 per cycle. Many small wins, occasional large loss. That is the
  martingale trade-off, not a defect.
- **Lot sizing is everything.** With a `$2` step and `2.0` multiplier on gold,
  a ~$1,000 account survives very few steps. Either use a much larger step, a
  smaller multiplier, or far more capital per 0.01 base lot.
- **Not compiled here** — MQL5 compiles only in MetaEditor (Windows/Wine).
  Written against the standard `Trade`/`PositionInfo` API and reviewed
  manually; compile with **F7** before use.

Use a **demo account**. This has **no established positive expectancy** — it
reproduces the mechanics you specified so you can test them yourself.

*Provided for educational purposes only. Not financial advice.*
