# IRONWALL HEDGE v2 — MT5 Expert Advisor

An MT5 Expert Advisor (`IronwallHedge.mq5`) implementing a **two-level
pendulum martingale** hedge strategy on XAUUSD (Gold).

> **This is a martingale strategy. Read the risk section before using it.**

---

## Strategy (exactly as specified)

A cycle is anchored to **two fixed price gates**, one grid step apart:

- **BUY gate** — the price of the first entry (example: `4310`)
- **SELL gate** — one grid step below it (example: `4308`, step `$2`)

Flow:

1. **First trade:** market **BUY** at the base lot (`0.01`) — this sets the
   BUY gate. The SELL gate is placed one step (`$2`) below.
2. **Alternating entries at the gates:**
   - price falls to the **SELL gate** → open a **SELL**
   - price rises to the **BUY gate** → open a **BUY**
3. **Lot doubles on every entry:** `0.01 → 0.02 → 0.04 → 0.08 → 0.16 …`
   (multiplier `2.0`). Worked example matching the spec:
   `BUY 0.01 @4310 → SELL 0.02 @4308 → BUY 0.04 @4310 → SELL 0.08 @4308 → …`
4. **Basket exit — net profit + trailing:** the whole basket (all buys and
   sells together) is watched as one combined floating P/L. When it reaches
   the **trail-start** target (`$2`), a trailing lock arms. After that, if
   profit falls back by the **trail gap** (`$1`) from its peak, **all trades
   close**, locking the gain. (Each trade does **not** have its own separate
   take-profit — exit is basket-level only.)
5. **Keep doubling until profit,** up to the **MaxLevels** cap (`15`). When
   the basket closes, a new cycle starts **immediately** at the current
   price. **No spread filter.**

Why it can net a profit: the most recent (largest) position is always in the
direction price just moved, so when a move extends, that leg's gain outruns
the smaller opposite legs and the basket reaches +$2.

---

## Files

- `IronwallHedge.mq5` — the Expert Advisor source.

## Installation

1. Copy `IronwallHedge.mq5` into your MT5 data folder under `MQL5/Experts/`
   (MetaTrader: *File → Open Data Folder*).
2. Open **MetaEditor**, open the file, press **F7** to compile (standard
   `Trade` library only — no extra dependencies).
3. Drag it onto an **XAUUSD** chart, enable **Algo Trading**.
4. **Backtest on a demo account first.**

## Inputs

| Input | Default | Meaning |
|-------|---------|---------|
| `InpMagic` | 490050 | Magic number (isolates this EA's orders) |
| `InpComment` | IronwallHedge | Order comment |
| `InpSlippage` | 50 | Max slippage (points) |
| `InpStartDir` | START_BUY | First trade direction (BUY or SELL) |
| `InpInitialLot` | 0.01 | Base (first) lot |
| `InpLotMultiplier` | 2.0 | Lot multiplier per re-entry |
| `InpMaxLot` | 50.0 | Hard cap on any single order lot |
| `InpGridStepPrice` | 2.0 | Distance between the two gates, in price ($2) |
| `InpMaxLevels` | 15 | Max entries per cycle (safety cap) |
| `InpTrailStartMoney` | 2.0 | Arm trailing when basket profit ≥ this (money) |
| `InpTrailGapMoney` | 1.0 | Close if profit drops this much from its peak |
| `InpUseHardStop` | false | Close basket at a max floating loss |
| `InpMaxLossMoney` | 0.0 | Max basket floating loss (money, if hard stop on) |
| `InpShowPanel` | true | Show on-chart status panel |
| `InpDrawGates` | true | Draw the two gate lines on the chart |

> **`InpGridStepPrice` is in price, not points** — set it to `2.0` for a
> `$2` gap (4310 / 4308), `3.0` for `$3`, etc. This avoids the 2-digit vs
> 3-digit gold confusion entirely.

---

## Risk — read this

This is a **martingale**, and the spec deliberately has **no per-trade stop**
— lots double until the basket recovers. Be clear-eyed about what that means:

- **Geometric lot growth.** With multiplier 2.0, level 15 is `0.01 × 2¹⁴ =
  163.84 lots` before the `InpMaxLot` cap. On gold, tens of lots means a `$1`
  move is thousands of dollars. Choppy price that keeps round-tripping the two
  gates is the worst case — it keeps doubling.
- **The cap does not save you, it freezes you.** When `InpMaxLevels` is hit,
  the EA stops adding and just holds. If price has trended away, the basket
  can sit in a very large floating loss indefinitely, because the only exit is
  a `+$2` net that may never come. Turn on `InpUseHardStop` if you want a real
  floor — it's off by default only because you didn't ask for one.
- **Small fixed target, unbounded risk.** You're risking a large, growing
  drawdown to make `~$1–$2` per cycle. Most cycles win; the rare cycle that
  doesn't can erase many winners at once. That is the martingale trade-off,
  not a bug.
- **Not compiled here.** MQL5 compiles only in MetaEditor (Windows/Wine),
  unavailable in this build environment. Written against the standard MT5
  `Trade`/`PositionInfo` API and reviewed manually — compile with F7 before
  use.

Use a **demo account**, size conservatively, and understand this has **no
established positive expectancy** — it reproduces the mechanics you specified,
nothing more.

*Provided for educational purposes only. Not financial advice.*
