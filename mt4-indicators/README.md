# NonRepaintChannel (MT4 / MQL4)

Reproduction of the channel-and-dots indicator shown in the reference video:
an upper (red) and lower (green) ATR channel wrapping price, with **red dots**
near the top band (sell) and **green dots** near the bottom band (buy).

## About the "non-repaint" claim

Sellers of dot/arrow indicators very often claim "100% non-repaint," and the
claim is frequently false. There are two honest categories:

1. **Bands / lines** — the two colored channels recalculate every tick and
   shift with price. This is normal and *not* what "repaint" refers to.
2. **Signals (dots/arrows)** — a dot *repaints* if, after appearing, it can
   later move to a different bar or vanish. That happens when a signal is
   computed using **future bars** (e.g. fractal confirmation needing bars to
   the right, or reading `buffer[0]` on the still-forming bar). Such an
   indicator looks perfect on history because every dot sits on a bar whose
   future was already known.

**You cannot get a signal that is both instantaneous *and* non-repainting.**
Something has to give: either you accept a lag (confirm on bar close), or you
accept repaint. A truthful "non-repaint" indicator therefore always confirms
on the **closed** bar.

## What this implementation does

This version is built to be genuinely non-repainting:

- Every dot is evaluated only on **already-closed bars** (`shift >= 1`); the
  forming bar (`shift 0`) is never signalled.
- Each dot depends only on data **to the left** of the signal bar (that bar's
  own OHLC plus history). No future bar is read, so once a dot prints on a
  closed bar it can never move or disappear.
- The trade-off, stated plainly: a dot appears at the **close** of the
  rejection bar, not intrabar. That one-bar confirmation is the price of it
  being real.

### Signal logic

- **Sell dot** — bar's high pierces the inner upper band but it closes back
  below the band and closes down (upper-band rejection).
- **Buy dot** — bar's low pierces the inner lower band but it closes back
  above the band and closes up (lower-band rejection).

### Bands

- Basis: `EMA(Close, MA_Period)`
- Inner band: `basis ± Mult_Inner * ATR(ATR_Period)`
- Outer band: `basis ± Mult_Outer * ATR(ATR_Period)`

## Inputs

| Input          | Default | Meaning                          |
|----------------|---------|----------------------------------|
| `MA_Period`    | 34      | Basis EMA period                 |
| `ATR_Period`   | 14      | ATR period for channel width     |
| `Mult_Inner`   | 1.5     | Inner band ATR multiplier        |
| `Mult_Outer`   | 2.5     | Outer band ATR multiplier        |
| `DotOffsetPts` | 12      | Dot distance from the candle     |

## Install

1. Copy `NonRepaintChannel.mq4` into
   `<MT4 data folder>/MQL4/Indicators/`.
2. In MetaEditor press **Compile** (F7).
3. In MT4, drag the indicator onto a chart.

## How to verify non-repaint yourself

- Right-click chart → *Refresh*, or reconnect: existing dots must stay put.
- Strategy Tester in **visual mode**, bar by bar: a dot must appear only after
  its bar closes and never jump to another bar afterwards.
- Compare against the video's indicator on live data — if its dots slide to a
  new bar after the fact, that one repaints and this one does not.

> Educational tool, not financial advice. Tune periods/multipliers per
> symbol and timeframe.
