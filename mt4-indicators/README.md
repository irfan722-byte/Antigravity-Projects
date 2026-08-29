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
- Each dot depends only on data **to the left** of the signal bar. No future
  bar is read, so once a dot prints on a closed bar it can never move or
  disappear.
- The trade-off, stated plainly: a dot appears at the **close** of the flip
  bar, not intrabar. That one-bar confirmation is the price of it being real.

### Signal logic — CONFIRMED trend flips (not band-touch)

Earlier drafts fired a dot whenever a wick poked a band and pulled back. That
is a mean-reversion "rejection" and it produces lots of false signals on
random spikes — the noise you saw.

This version instead uses a **SuperTrend-style trend flip**, which is what the
video's *confirmed* dots behave like:

- A hidden ATR trailing band follows price. The trend is **up** while price
  holds above it and **down** while price holds below it.
- A **green buy dot** prints only on the bar where price **closes above** the
  band and the trend flips up (near bottoms).
- A **red sell dot** prints only on the bar where price **closes below** the
  band and the trend flips down (near tops).

Because a flip requires a *close through the band*, signals are naturally
**rare, clean, and strictly alternating** (buy → sell → buy). The close-through
is the confirmation — no separate rejection guesswork.

### Bands (the drawn red/green channel)

- Basis: `EMA(Close, MA_Period)`, optionally smoothed by `Smooth`.
- Inner band: `basis ± Mult_Inner * ATR(ATR_Period)`
- Outer band: `basis ± Mult_Outer * ATR(ATR_Period)`

The drawn channel is cosmetic (matches the video's look); the **signals come
from the separate SuperTrend engine** below, so you tune them independently.

## Inputs

**Drawn channel (visual only):**

| Input          | Default | Meaning                          |
|----------------|---------|----------------------------------|
| `MA_Period`    | 60      | Basis EMA period                 |
| `Smooth`       | 5       | Extra band smoothing (1 = off)   |
| `ATR_Period`   | 30      | ATR period for channel width     |
| `Mult_Inner`   | 1.6     | Inner band ATR multiplier        |
| `Mult_Outer`   | 2.6     | Outer band ATR multiplier        |

**Confirmed signal engine (the dots):**

| Input           | Default | Meaning                                                     |
|-----------------|---------|-------------------------------------------------------------|
| `ST_ATR_Period` | 22      | ATR period for the trend engine                             |
| `ST_Mult`       | 3.5     | Sensitivity — **higher = fewer, later, more-confirmed** dots |
| `DotOffsetPts`  | 25      | Dot distance from the candle                                |

### Tuning the number of signals

`ST_Mult` is the main dial:

- **Too many dots?** raise `ST_Mult` (try 4–6) and/or `ST_ATR_Period`.
- **Too few dots?** lower `ST_Mult` (try 2–3).
- Signal frequency also depends on **symbol and timeframe** — load it on the
  same timeframe as the video (looks like H1/H4) for the closest match.

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
