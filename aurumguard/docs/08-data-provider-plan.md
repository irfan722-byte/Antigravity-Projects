# 08 Data-provider plan

Each source is documented with the required fields (see `providers/base.py::ProviderDoc`, surfaced on `/data-health`).

| # | Source (adapter) | Fields | Frequency / latency | History | Revisions | Licence | Rate limit / cost | Failure behaviour | Backup | Scalping-suitable |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | XAU/USD market data — `mock` (implemented), `twelvedata` (implemented; per-timeframe candle cache and quote cache to fit the free tier; verify a key with `python -m app.check_provider`) | OHLC, tick-volume proxy, spread, bid/ask (mock); OHLC + mid price (Twelve Data) | 1-min candles; seconds latency | synthetic from 2024; provider plan-dependent | none / silent corrections | none / commercial API terms | none / credits per minute, paid | ProviderError → DATA UNAVAILABLE | OANDA v20 (true bid/ask), Polygon, broker feed | No (candles, no true bid/ask) |
| 2 | Economic calendar — `mock` | event id, name, importance, scheduled ts, actual, consensus, prior, revised prior, publication ts | scheduled; seconds after release | synthetic | revised prior supported | commercial (e.g. Econoday, TradingEconomics, FMP) | vendor-specific | lockout stays active until verified | second vendor for verification | n/a |
| 3 | Official macro releases (BLS, BEA, Fed) — `mock` | value, release ts, revision | monthly/weekly | decades (FRED) | yes (point-in-time via ALFRED) | public domain (US gov) | FRED free key | stale flag | direct agency APIs | n/a |
| 4 | News — `mock` | headline, source, ts, url | continuous | vendor | — | commercial wire licences | vendor | ignored (informational only) | — | n/a |
| 5 | Treasury yields (2y, 10y, real-yield proxy, breakevens) — `mock` | daily close | daily (H.15 / FRED) | decades | rare | public | free | intermarket evidence marked unavailable | Treasury.gov | n/a |
| 6 | Dollar index proxy — `mock` | daily close | daily | long | none | DXY is licensed (ICE); an equal-weight FX basket proxy from public FX is the free alternative | — | evidence unavailable | FX basket proxy | n/a |
| 7 | Futures positioning (CFTC COT) — `mock` | managed-money long/short, OI, report date, publication ts | weekly (Tue data, Fri 15:30 ET) | 2006+ | none | public | free | evidence unavailable | — | n/a |
| 8 | ETF flows — `mock` | net flow tonnes, date, publication ts | daily with 1-day lag | issuer/WGC | none | public issuer pages / WGC terms | free | evidence unavailable | — | n/a |
| 9 | Trading calendar — `mock` | holidays, early closes | yearly | — | — | exchange notices (CME/LBMA) | free | G19 fails → DATA UNAVAILABLE | manual review | n/a |
| 10 | Push — `mock`, `webpush` (implemented, unverified against a real push service) | subscription, payload | event driven | — | — | browser push services (free), FCM optional | per-service | delivery FAILED recorded, retries ×3 | email (not implemented), Telegram (deferred pending privacy review) | n/a |

**Scalping note.** Candle-only sources cannot model scalp execution. Approving a scalp strategy requires tick-level bid/ask history (e.g. broker tick archives or Dukascopy-style data under licence) and is out of scope.
