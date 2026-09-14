# IRONWALL HEDGE — MT5 Expert Advisor

An MT5 Expert Advisor (`IronwallHedge.mq5`) reconstructed from the strategy
shown in the reference video (`Hedge_EA.MP4`, a screen recording of
"IRONWALL HEDGE V4.9" running on XAUUSD M1).

> **This is a martingale/grid strategy. Read the risk section before using it.**

---

## How the strategy was reconstructed

The source is a promotional short-form video with no source code and no
usable audio narration (the model download needed for speech-to-text was
blocked by network policy in the build environment). The logic below was
read directly from the MT5 mobile order panel across the clip:

| Frame stage | On-screen state (net volume per direction) | Floating P/L |
|-------------|--------------------------------------------|--------------|
| Start       | `BUY 0.01` + `SELL STOP 0.02`              | small        |
| Next        | `BUY STOP 0.04` + `SELL 0.02`              | small        |
| Next        | `BUY 0.04` + `SELL STOP 0.08`              | −5           |
| Escalation  | `BUY 0.08` + `SELL STOP 0.32`             | −2 → **−31** |
| Recovery    | `BUY 0.08` + `SELL STOP 0.32`             | **+5.55**    |
| New cycle   | `BUY STOP 0.04` + `SELL 0.02` (+ SL line) | +1.84        |

Observed facts that drive the design:

- **Instrument / timeframe:** XAUUSD (Gold), M1.
- **Entry:** one market order plus an opposite pending **STOP** order a fixed
  distance away.
- **Lot escalation:** each new level roughly doubles the lot
  (`0.01 → 0.02 → 0.04 → 0.08 …`) — a **martingale multiplier ~2.0**.
- **Two-sided "wall":** as price whipsaws, stop orders on both sides keep
  filling, so the basket is hedged in both directions.
- **Recovery close:** floating P/L swung deep negative (−31) then the basket
  closed in profit (+5.55) and a fresh cycle began — i.e. **close the whole
  basket on a small money target, then restart**.
- **"Strong Defense / Controlled Risk":** a max number of levels plus an
  account-level stop (an `SL` line appears late in the clip).

The video does not expose the exact grid distance, multiplier value, TP
target, or level cap in numbers, so those are **inputs with sensible
defaults** that you must tune to your broker and risk tolerance.

---

## Strategy logic (as implemented)

1. **Start a cycle** — open an initial market order (`BUY` by default) at the
   base lot, and immediately place an opposite **SELL STOP** one grid step
   away with a larger lot (`base × multiplier`).
2. **On each fill** — when a pending stop fills, the net direction flips.
   Place the next opposite stop one grid step further out, lot multiplied
   again. Directions alternate: level 0 = start dir, level 1 = opposite,
   level 2 = start dir, and so on.
3. **Cap the wall** — stop adding levels once `MaxLevels` positions exist
   (controlled risk).
4. **Exit the basket** — close **all** positions and pendings when combined
   floating P/L reaches the take-profit target (money or net points), or when
   it falls to the max-loss stop.
5. **Restart** — begin a fresh cycle (optional).

Only one basket runs at a time.

---

## Files

- `IronwallHedge.mq5` — the Expert Advisor source.

## Installation

1. Copy `IronwallHedge.mq5` into your MT5 data folder under
   `MQL5/Experts/` (in MetaTrader: *File → Open Data Folder*).
2. Open **MetaEditor**, open the file, and press **F7** to compile. It uses
   only the standard `Trade` library, so no extra dependencies.
3. In MT5, drag the EA onto an **XAUUSD M1** chart. Enable **Algo Trading**.
4. **Backtest in the Strategy Tester on a demo account first.**

## Inputs

| Input | Default | Meaning |
|-------|---------|---------|
| `InpMagic` | 490049 | Magic number (isolates this EA's orders) |
| `InpComment` | IronwallHedge | Order comment |
| `InpSlippage` | 30 | Max slippage (points) |
| `InpStartDir` | START_BUY | First order direction (Buy / Sell / Auto=last candle) |
| `InpInitialLot` | 0.01 | Base lot |
| `InpLotMultiplier` | 2.0 | Martingale lot multiplier per level |
| `InpMaxLot` | 5.0 | Hard cap on any single order lot |
| `InpGridStepPoints` | 300 | Grid step / hedge distance (points) |
| `InpMaxLevels` | 6 | Max hedge levels (risk cap) |
| `InpTpMode` | TP_MONEY | Basket TP mode (money or net points) |
| `InpTakeProfitMoney` | 5.0 | Basket TP in account currency |
| `InpTakeProfitPts` | 200 | Basket TP in net points (if TP_POINTS) |
| `InpUseAccountStop` | true | Close basket at a max floating loss |
| `InpMaxLossMoney` | 100.0 | Max basket floating loss (money) |
| `InpRestartAfterTP` | true | Start a new cycle after each close |
| `InpUseSpreadFilter` | true | Skip new cycles when spread too wide |
| `InpMaxSpreadPoints` | 60 | Max allowed spread (points) |
| `InpShowPanel` | true | Show on-chart status panel |

> **Point vs. price on gold:** on most brokers XAUUSD has 2 digits, so
> `1 point = 0.01` and `InpGridStepPoints = 300` ≈ a **$3.00** grid step.
> On 3-digit gold feeds the same 300 points ≈ **$0.30**. Check your symbol's
> digits and set the grid step accordingly.

---

## Risk — read this

This is a **martingale grid**. The math that makes it look like it "always
recovers" in a short clip is the same math that blows accounts:

- **Lots grow geometrically.** With multiplier 2.0, level 10 is `base × 1024`.
  A base of 0.01 becomes 10.24 lots; six levels already reach ~0.64 lots.
  A sustained one-directional trend that never retraces keeps filling the
  losing side faster than the winning side recovers.
- **The account stop is the only hard floor.** `InpMaxLevels` and
  `InpMaxLossMoney` cap the damage; without them a single strong trend can
  hit a margin call. Do **not** disable them.
- **Backtest quality matters.** M1 gold with tight grids needs real tick data
  and realistic spread/commission, or the tester will flatter the strategy.
- **A profitable-looking short video is not evidence.** It shows one favorable
  window. It does not show the run where the wall breaks.

Use a **demo account**, size conservatively, and understand that positive
expectancy here is not established — the reconstruction reproduces the
*mechanics* shown, not a proven edge.

*Provided for educational purposes only. Not financial advice.*
