# 13 Strategy format and market-structure glossary

## Registry record (35 fields)
See `backend/app/config/strategy_registry.json` for the four candidate strategies with every field populated: id, name, version, owner, status, horizon, hypothesis, rationale, required_data, instruments, timeframes, sessions, approved_regimes, prohibited_regimes, entry_setup, entry_trigger, confirmation_rules, invalidation_rules, stop_methodology, tp1_methodology, tp2_methodology, sizing_methodology, min_net_rr, spread_limit, slippage_limit, news_restrictions, setup_expiry_minutes, max_holding_minutes, backtest_results, validation_results, paper_results, known_failure_regimes, suspension_rules, retirement_rules, approval_history, change_log (+ partial-close, breakeven and trailing-stop options).

Code lives in `core/strategies/`; state (status, threshold, validation, approvals) lives in the `strategies` table and is only changed through the admin workflow.

## Market-structure definitions (`core/structure.py`)
All parameters have an allowed range enforced in `StructureParams.__post_init__`; violations raise.

| Concept | Definition | Params (default, range) | Confirmation | Invalidation | Known failure |
|---|---|---|---|---|---|
| Swing high/low | high[i] > all highs in [i−L,i) and ≥ all in (i,i+R] (mirror for lows) | L=3 (2–10), R=3 (1–10) | known only R bars later | — | choppy markets produce many minor swings |
| HH/HL, LH/LL, trend | last two swing highs and lows compare | — | needs ≥2 of each | new opposite swing | equal swings → SIDEWAYS |
| Break of structure / MSS | close beyond last confirmed swing by ≥ k·ATR; MSS if against prior trend | k=0.10 (0–0.5), ATR 14 | closed bar | close back inside | news spikes |
| Support/resistance, PDH/PDL, PWH/PWL, PMH/PML | extremes of completed NY-calendar periods | — | period complete | — | holiday sessions |
| Session highs/lows | extremes of completed Asia/London/NY session windows (local exchange time, DST-aware) | session table | window closed | — | early closes |
| Equal highs/lows | consecutive same-kind swings within t·ATR | t=0.10 (0.02–0.3) | — | — | — |
| Consolidation range | (max−min of last N bars) ≤ w·ATR | N=20 (10–100), w=3 (1–6) | — | breakout | slow trends look like ranges |
| Breakout | close beyond level by k·ATR with the bar having touched within 1 ATR | k=0.10 | closed bar | close back inside | thin liquidity |
| Breakout retest | see BRT-M15 rules | tolerance 0.3 ATR, hold 0.1 ATR | trigger bar | any close back across | — |
| Failed breakout / breakdown | close beyond level then close back within M bars | M=3 (1–10) | closed bar | — | — |
| Liquidity sweep | wick beyond level ≥ s·ATR, close back inside same bar | s=0.20 (0.05–1) | closed bar | — | — |
| Displacement | range ≥ d·ATR and body ≥ 60% of range | d=1.5 (1–3) | closed bar | — | news bars |
| Imbalance / FVG | low[i] > high[i−2] (bullish) or high[i] < low[i−2] by ≥ f·ATR | f=0.10 (0–0.5) | — | filled | — |
| Volatility expansion / contraction | ATR now vs ATR n bars ago ≥ 1.5 / ≤ 0.7 | n=10 | — | — | — |
| Gap | open − previous close ≥ f·ATR after a time gap | f=0.10 | — | — | — |
| Rejection | dominant wick ≥ 60% of range | 0.6 (0.4–0.9) | — | — | doji noise |
| Trend continuation / mean reversion | strategy-level compositions (PBC/BRT vs RRJ) | strategy params | strategy rules | strategy rules | strategy cards |

Tests: `tests/test_structure_regime_scoring.py`.

## "Retail trap" patterns → measurable events
Breakout re-entry (FAILED_BREAKOUT/BREAKDOWN), sweep with opposite displacement (SWEEP_* + DISPLACEMENT), failed post-news continuation (news state + BOS against), spread expansion during breakout (spread ratio measurement), low-liquidity sweep (THIN_LIQUIDITY tag + sweep), spot/DXY/yield divergence (intermarket evidence signs), crowded positioning (COT percentile), false opening-range breakout (session level failed breakout), rejection at PDH/PWH/PMH (REJECTION at level), pre-event move into liquidity (PRE_EVENT_WINDOW + sweep), no follow-through (breakout without retest hold). Labels are limited to the four permitted phrases.
