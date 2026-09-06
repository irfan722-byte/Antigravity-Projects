# 33 Strategy cards

| | PBC-H1 Pullback Continuation v1.0.0 | BRT-M15 Breakout and Retest v1.0.0 | RRJ-H4 Range Rejection v0.1.0 | PNC-M15 Post-News Confirmation v0.1.0 |
|---|---|---|---|---|
| Horizon | Intraday (H1 anchor, H4/D1 context) | Intraday (M15, H1 levels) | Swing (H4, D1) | Intraday (M15) |
| Status | RESEARCH (seed approves for DEMO paper only) | RESEARCH (same) | RESEARCH | RESEARCH |
| Regimes | STRONG/WEAK_TREND; not RANGE/TRANSITION/NEWS/THIN/MIXED/UNKNOWN | STRONG/WEAK_TREND/RANGE; not NEWS/THIN/MIXED/UNKNOWN | RANGE only | NEWS_DOMINATED + trend/range; not THIN/UNKNOWN |
| Entry | EMA20/50 aligned, pullback to EMA20 zone, trigger bar | displacement break of PDH/PDL/PWH/PWL/session level, held retest, trigger bar | sweep of range extreme with rejection close | verified surprise ≥ 1σ, DXY+gold agree, M15 BOS |
| Stop | pullback extreme ± 0.25 ATR | retest extreme/level ± 0.25 ATR | sweep wick ± 0.3 ATR | post-release extreme ± 0.25 ATR |
| TP1 / TP2 | structural level (≤ 3R) else 2R / next level else 2.5R (always beyond TP1) | measured move floored 2R, capped 3R / next level else 2.5R | range mid / opposite extreme − 0.2 ATR | 2R / next level else 2.5R |
| Expiry / max hold | 180 min / 720 min | 60 min / 480 min | 8 h / 3 days | 90 min / 6 h |
| Known failures | ranges, releases, transitions | thin liquidity, no-displacement ranges | displacement breakouts, news | mixed releases, thin liquidity |
| Suspension | 30-trade rolling expectancy < 0R, DD > 8R or PF < 0.9 | same | 20 trades, DD > 6R | same as RRJ |

Validation on DEMO data is a pipeline test only; real cards will carry OOS statistics from licensed data after review.
