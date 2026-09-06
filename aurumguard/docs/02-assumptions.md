# 02 Assumptions

1. The primary user is one individual trader in Asia/Dubai using the system for personal analysis and paper trading; multi-tenant scale is designed for but not load-tested.
2. XAU/USD spot trades Sunday 18:00 to Friday 17:00 New York time with a daily 17:00–18:00 maintenance break; holidays and early closes come from a trading-calendar provider (mock in the MVP).
3. Candle data at M1 resolution (or coarser) is the finest data available. Tick-level bid/ask history is **not** available, which is why no scalping strategy is approved.
4. Mid-price candles plus an observed or modelled spread are an acceptable approximation for intraday and swing fills when labelled conservatively (stop-first same-bar rule, gap-through-stop rule).
5. The generic 100 oz per lot, 0.01 lot minimum contract is illustrative only; real sizing requires a verified venue specification.
6. USD/AED is a fixed peg (3.6725) used for display conversion of AED accounts.
7. The user's device supports Web Push (Android Chrome, desktop browsers, iOS 16.4+ installed PWA). Delivery is best-effort; the in-app notification centre is the system of record.
8. All timestamps are stored in UTC and converted at the presentation layer with IANA zone names.
9. Research weights and the 75-point research threshold are starting assumptions, not validated production values.
10. Demo data is a seeded synthetic random walk; it validates the pipeline, never a strategy.
