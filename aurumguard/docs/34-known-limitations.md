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
