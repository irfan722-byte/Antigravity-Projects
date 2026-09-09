# 34 Known limitations

1. Demo data is synthetic; no strategy is validated for real markets.
2. Twelve Data adapter is unverified and mid-only (no observed spread); OANDA-style bid/ask feed recommended.
3. No tick data → no scalping strategy; SCALP horizon always returns NO TRADE with the reason.
4. Single-process scheduler; not horizontally scaled; in-memory rate limiter and SSE bus.
5. Tokens in localStorage (documented mitigation path).
6. Push verified only with the mock provider; iOS behaviour untested.
7. Candles are not persisted; the mock regenerates deterministically; production needs the candle/quote tables.
8. Intraday DXY/yield reactions use daily proxies in the mock (labelled).
9. Outcome recording uses the mid path without fill simulation (labelled).
10. i18n/RTL is architecture only; no Arabic strings.
11. Accessibility: semantics, focus styles, reduced motion, keyboard-reachable controls present; no automated axe audit yet.
12. Load tests not run.

## Live-price mode (Twelve Data)

- The adapter has been exercised against an in-process fake of the documented endpoints and against the
  real API only by the repository owner's key check; it is not covered by CI.
- Quote is mid-only. The reported spread is the `TWELVEDATA_ASSUMED_SPREAD_USD` assumption, labelled in the
  quote provenance and provider health; it is a paper-trading cost input, not market data.
- With `CALENDAR_PROVIDER=none` the event gate (G06) cannot protect around real releases; with `mock` it
  reacts to synthetic events instead. Neither is a substitute for a licensed calendar.
- Macro, positioning and ETF-flow inputs remain synthetic in this build even when prices are live, so the
  intermarket evidence family should be read as placeholder in live mode.
- Free-tier budget (about 800 credits/day) requires `ANALYSIS_INTERVAL_SECONDS=300`; the UI shows a quote
  up to `TWELVEDATA_QUOTE_TTL_SECONDS` old on purpose and flags it as such.
- Minute candles are outside the daily estimate: the paper engine fetches them once per run, but only
  while a position is open, an order is resting, or an expired setup is still to be scored. An idle
  account spends nothing on them; an active one adds one credit per run.
- Read-only pages judge quote freshness against the adapter's cache lifetime, so polling them costs no
  API credits; `/api/regime` reads stored decisions. Only the analysis loop and an explicit
  evaluate-now demand a fresh quote. The adapter keeps the combined rate under `TWELVEDATA_CREDITS_PER_MINUTE`
  and collapses concurrent cold-cache fetches, waiting up to 20 s for a slot rather than taking a 429.
- The analysis loop always requests a quote fresher than the integrity staleness limit (20 s), so the quote
  cache never answers it: quote credits scale with `ANALYSIS_INTERVAL_SECONDS`, not with the cache TTL. The
  shortest interval that fits the free tier with the five default timeframes is 225 s.
- Outbound HTTPS is verified against the OS certificate store when `truststore` is installed (`HTTPS_TRUST=auto`,
  the default) and against certifi otherwise. On a machine that inspects TLS, provider calls fail with
  `CERTIFICATE_VERIFY_FAILED` until the inspecting root is trusted; `HTTPS_CA_BUNDLE` accepts an explicit PEM.
  Verification is never disabled, so such a machine cannot use live prices without trusting that root.
