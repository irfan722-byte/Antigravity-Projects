# Aurum Desk — XAU/USD Signal Engine

A single-file, zero-dependency web app that generates mechanical gold (XAU/USD)
trading signals for **scalping (5-minute)** and **swing trading (1H/4H)**, live
during market hours (Sun 22:00 UTC → Fri 21:00 UTC).

## Run it

No build step, no server, no API key.

- **Locally:** open `gold-signals/index.html` in any modern browser. Keep the tab
  open; it refreshes itself every 45 seconds.
- **Hosted:** drop the file on any static host (Firebase Hosting, GitHub Pages,
  Netlify). Example with this repo's Firebase setup: copy it into a hosting
  public dir and `npx firebase deploy --only hosting`.

> Note: it will not work inside sandboxed preview panes that block outbound
> network requests — open it as a normal browser tab.

## Data feeds (free, no registration)

| Feed | Source | Purpose |
|---|---|---|
| Candles (5m/15m/1h/4h) | Binance `PAXGUSDT` klines | PAXG is tokenized gold (1 token = 1 oz LBMA gold); trades 24/7 and tracks spot closely |
| Live spot | gold-api.com `XAU` | True XAU spot; the app computes the PAXG↔spot offset and calibrates every displayed level to real spot |

If the spot feed is unreachable the app falls back to raw PAXG prices and says so.

## Strategy

Both engines are confluence-scored (0–100). A signal is **ACTIVE only at a
score ≥ 70 while the gold market is open**; below that the card shows WAIT with
the current lean. Signals fire on **closed candles only** — the forming candle
is never used, so signals don't repaint.

### Scalp engine (5M, filtered by 15M)

| Check | Weight |
|---|---|
| EMA9/EMA21 relation (direction) | 25 |
| Price on the right side of EMA50 (5M trend) | 15 |
| 15M timeframe agreement (EMA9 vs EMA21) | 20 |
| RSI(14) supportive but not exhausted (50–72 long / 28–50 short) | 15 |
| MACD(12,26,9) histogram building in the trade direction | 15 |
| London / New York session liquidity | 10 |

Levels: stop = 1.2 × ATR(14), TP1 = 1 × ATR (~0.8R), TP2 = 2 × ATR (~1.7R).
A trigger is "fresh" for 3 bars after the EMA cross; after that the card tells
you it's a late entry.

### Swing engine (1H, biased by 4H)

| Check | Weight |
|---|---|
| 4H structure (EMA21 vs EMA50 + price vs EMA50) | 30 |
| 1H momentum aligned (EMA9 vs EMA21) | 20 |
| Pullback to 1H EMA21 zone or fresh 1H momentum turn | 20 |
| 1H RSI has room to run | 15 |
| 1H MACD histogram turning in favour | 15 |

Levels: stop = 1.8 × ATR(1H), TP1 = 2 × ATR (~1.1R), TP2 = 3.5 × ATR (~1.9R).

### Built-in accountability

Every ACTIVE trigger is logged (browser localStorage) and its outcome is
resolved automatically against subsequent price action — TP1/TP2 hit, stopped,
or expired (scalps after 3h, swings after 5 days). The performance panel shows
win rate, net R and average R per trade. **Trust the stats, not the feeling.**
If the engine's net R goes negative over a meaningful sample, stop trading it
and retune.

Same-bar ambiguity (a candle touching both stop and target) is scored as a
**loss** — the tracker is deliberately conservative.

### Risk management

The position sizer converts account size + risk % + the live stop distance into
lots (1 standard lot = 100 oz, so a $1/oz move = $100/lot). Suggested defaults:
risk 0.5–1% per scalp, 1–2% per swing, and stand aside outside London/NY hours.

## Honest limitations

- Technical confluence has no knowledge of news. **Do not scalp through
  FOMC, CPI or NFP releases** — spreads blow out and stops slip.
- Candle structure comes from PAXG, which can deviate a few dollars from your
  broker's XAU feed; the spot calibration narrows this but execution prices are
  your broker's.
- No signal engine is a guarantee. This is decision support with enforced
  discipline (fixed stops, sized risk, tracked outcomes) — the edge, if any,
  emerges only with consistent execution over many trades.
