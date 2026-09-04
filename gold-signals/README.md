# Aurum Desk — XAU/USD Signal Engine

A single-file, zero-dependency web app that generates gold (XAU/USD) trading
signals on **5-minute, 15-minute and 1-hour** timeframes, live during market
hours (Sun 22:00 UTC → Fri 21:00 UTC). The layout follows the standard
technical-summary format used by signal sites: an overall gauge from Strong
Sell to Strong Buy, a moving-averages vote table, an oscillators table, pivot
points, and an actionable signal card with entry, stop loss and three take
profits per timeframe.

## Run it

No build step, no server, no API key.

- **Locally:** open `gold-signals/index.html` in any modern browser. Keep the tab
  open; it refreshes itself every 45 seconds.
- **Hosted:** drop the file on any static host (Firebase Hosting, GitHub Pages,
  Netlify).

> Note: it will not work inside sandboxed preview panes that block outbound
> network requests — open it as a normal browser tab.

## Data feeds (free, no registration)

| Feed | Source | Purpose |
|---|---|---|
| Candles (5m/15m/1h/1d) | Binance `PAXGUSDT` klines | PAXG is tokenized gold (1 token = 1 oz LBMA gold); trades 24/7 and tracks spot closely |
| Live spot | gold-api.com `XAU` | True XAU spot; the app computes the PAXG↔spot offset and calibrates every displayed level to real spot |

If the spot feed is unreachable the app falls back to raw PAXG prices and says so.

## How the verdict is built (per timeframe)

All computations use **closed candles only** — signals do not repaint.

**Moving averages (12 votes):** SMA and EMA of 5, 10, 20, 50, 100 and 200
periods. Price above → Buy, below → Sell.

**Oscillators (10 votes):**

| Indicator | Buy | Sell | Neutral |
|---|---|---|---|
| RSI (14) | < 30 or 55–70 | > 70 or 30–45 | 45–55 |
| Stochastic %K (9,6) | < 20, or rising | > 80, or falling | — |
| Stochastic RSI (14) | < 20 | > 80 | 20–80 |
| MACD (12,26,9) | histogram > 0 | histogram < 0 | — |
| ADX (14) | +DI > −DI (ADX ≥ 20) | −DI > +DI (ADX ≥ 20) | ADX < 20 |
| Williams %R (14) | < −80 or −80…−50 | > −20 or −50…−20 | — |
| CCI (14) | > +100 | < −100 | between |
| Ultimate Oscillator | < 30 or 50–70 | > 70 or 30–50 | — |
| ROC (12) | > 0 | < 0 | — |
| Bull/Bear Power (13) | > 0 | < 0 | — |

Net score = (buys − sells) / votes. Bands: ≥ +0.50 **Strong Buy**, ≥ +0.15
**Buy**, ≤ −0.50 **Strong Sell**, ≤ −0.15 **Sell**, else **Neutral**. The
gauge needle, the tab chips and the signal card all read from this score.

**Signal levels:** entry = last close; stop = k × ATR(14) (5m/15m: 1.2–1.3×,
1h: 1.5×); TP1/TP2/TP3 = 1/2/3 × ATR (1h: 1.5/2.5/4 ×). All levels are
calibrated to live XAU spot.

**Pivot points:** Classic, Fibonacci and Camarilla from the previous daily
candle's high/low/close.

### Built-in accountability

Every fresh **Strong** signal (score ≥ 0.5 with an EMA9/21 cross within the
last 3 bars) is logged in browser localStorage and its outcome resolved
automatically against later candles — TP1/TP2 hit, stopped, or expired. The
performance panel shows win rate, net R and average R. **Trust the stats, not
the feeling.** Same-bar stop/target ambiguity is scored as a loss — the
tracker is deliberately conservative.

### Risk management

The position sizer converts account size + risk % + the live stop distance into
lots (1 standard lot = 100 oz, so a $1/oz move = $100/lot). Suggested defaults:
0.5–1% risk on 5m/15m signals, 1–2% on 1h, and stand aside outside London/NY
hours.

## Honest limitations

- Technical consensus has no knowledge of news. **Do not trade through FOMC,
  CPI or NFP releases** — spreads blow out and stops slip.
- Candle structure comes from PAXG, which can deviate a few dollars from your
  broker's XAU feed; the spot calibration narrows this but execution prices are
  your broker's.
- No signal engine is a guarantee. This is decision support with enforced
  discipline (fixed stops, sized risk, tracked outcomes) — the edge, if any,
  emerges only with consistent execution over many trades.
