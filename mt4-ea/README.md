# GridRecoveryEA — MT4 grid/martingale EA (educational replica)

This folder contains a from-scratch MetaTrader 4 Expert Advisor that reproduces
the **style** of strategy shown in the uploaded `EA_fast.MP4` clip.

## What the video actually showed

- A phone screen-recording of the **MetaTrader mobile app** (French UI:
  *Fonds disponibles, Marge libre, Niveau de la marge*) mirroring a desktop
  terminal.
- Symbol: **US30** (Dow Jones 30 index CFD).
- The desktop chart carried a `Spread: 5000.0 pips` watermark — that label only
  appears in the **MT4/MT5 Strategy Tester**. Combined with the balance jumping
  ~100,964 → ~108,938 USD in ~12 seconds while the chart clock advanced from
  15:28 to 16:36, this is a **visual-mode backtest**, not a live account.
- The order list was a **ladder of pending + market trades** clustered within a
  few points (39,357–39,393), with positions closing in small chunks
  (96, 146, 296) — the classic footprint of a **grid + martingale** EA.

There is **no EA name visible** in the video, so it cannot be identified as a
specific commercial product. It is the generic template that most "look how much
this US30 robot makes" marketing clips are built from.

## Why these backtests look perfect (and why that's misleading)

A grid keeps adding trades in one direction as price moves against it, lowering
(or raising) the average entry, then closes the **whole basket** the moment a
small bounce pushes floating profit to a target. In any bounded backtest,
price almost always bounces *eventually*, so the equity curve looks like a
near-straight line up. On a **real strong trend** the grid keeps stacking
losing trades — with a martingale multiplier the lot sizes explode — until
margin runs out and the account is wiped in a single move.

**A great backtest here is not evidence of live profitability. Demo only.**

## Files

| File | Purpose |
|------|---------|
| `GridRecoveryEA.mq4` | Baseline grid + optional martingale (closest to the video). |
| `GridRecoverySafeEA.mq4` | **Flat-lot, hard-stop "safe" variant** — no martingale, mandatory per-trade SL and basket money SL, so worst-case loss is bounded and linear. |
| `PendingLadderEA.mq4` | Places an actual ladder of **buy-stop + buy-limit pending orders** around price, exactly like the phone's order list in the clip. |

### `GridRecoverySafeEA.mq4` — the safe variant

Same grid mechanic, but the two things that blow accounts up are removed:

- **No martingale** — every trade is the same `FixedLots`.
- **Mandatory hard stops** — the EA refuses to start unless both `StopLossPoints`
  (per-trade SL) and `BasketSLMoney` (whole-basket loss cut in $) are set > 0.

Worst case is therefore bounded to roughly `BasketSLMoney`, or per-trade
`StopLossPoints × MaxTrades`, whichever triggers first — instead of the
open-ended margin-call risk of the martingale version. A bounded loss is still
a loss, so it's still demo-first.

### `PendingLadderEA.mq4` — the pending-order ladder

While flat, it seeds `LevelsAbove` **buy-stop** orders above price and
`LevelsBelow` **buy-limit** orders below price, spaced by `StepPoints` — the
"US30, buy stop / buy limit" rows you saw on the phone. As price moves, pendings
fill into one buy basket that's closed as a whole at `BasketTPMoney`, then the
ladder is rebuilt (`RebuildAfterClose`). Lots are **flat** by default
(`LotMultiplier = 1.0`); raising it scales the outer levels martingale-style like
the original — which brings the blow-up risk back, so keep it at 1.0 unless you're
deliberately studying that.

Key extras: `PerOrderSLPoints` (optional stop on each filled trade),
`PendingExpiryMin` (auto-expire unfilled pendings), `BasketSLMoney` (money loss
cut for the filled basket).

## How to build / run it

1. Open **MetaEditor** (comes with MT4).
2. Copy `GridRecoveryEA.mq4` into `MQL4/Experts/` of your MT4 data folder
   (*File → Open Data Folder* in the terminal).
3. Press **F7** to compile → produces `GridRecoveryEA.ex4`.
4. In MT4, open a **US30** chart, drag the EA on, and **enable AutoTrading**.
5. To reproduce the video: open the **Strategy Tester** (Ctrl+R), pick
   `GridRecoveryEA`, symbol **US30**, tick **Visual mode**, and press Start.

## Key inputs

| Input | Meaning |
|-------|---------|
| `Direction` | Buy-only grid (buys dips, as in the video) or sell-only. |
| `StartLots` | Size of the first trade. |
| `MaxTrades` | Hard cap on grid depth — the main risk brake. |
| `GridStepPoints` | Distance between grid levels, in points. |
| `LotMultiplier` | Martingale factor. `1.0` = flat lots (far safer). |
| `BasketTPMoney` | Close the entire basket at this floating $ profit. |
| `BasketSLMoney` | Optional hard $ loss cut for the basket (`0` = off). |
| `MaxSpreadPoints` | Skip new entries when the spread is too wide (`0` = off). |

## Safer ways to study it

- Set `LotMultiplier = 1.0` to remove the martingale (linear risk instead of
  exponential).
- Always set a non-zero `BasketSLMoney` so the basket can't run to margin call.
- Keep `MaxTrades` low.
- Forward-test on **demo** across a trending period (e.g. a sustained US30
  sell-off), not just a ranging one — that's where grids fail.

> This code is for education. It is not financial advice and not a
> ready-to-trade product.
