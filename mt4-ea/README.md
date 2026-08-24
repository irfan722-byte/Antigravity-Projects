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
| `GridRecoveryEA.mq4` | The Expert Advisor source. |

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
