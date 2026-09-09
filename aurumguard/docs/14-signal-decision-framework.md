# 14 Signal-decision framework

## Evidence families and scoring (`core/evidence.py`, `config/scoring_config.json`)
Ten families: technical, structure, liquidity/volatility/execution, volatility, intermarket/flow, macro, positioning, news/event, strategy history, risk/cost. Research weights (version `scoring-v0.1-research`): technical 20%, structure 20%, intermarket/flow 15%, macro 15%, news 10%, liquidity/volatility/execution 10%, strategy reliability 10%. Weights are configuration, not code.

Correlation handling: items in a configured correlated group (`rsi|stochastic`, moving-average family, dollar proxies, yield proxies) collapse to the strongest single item; the collapsed items are listed in the breakdown. A single family that supplies more than 35% of the positive score while fewer than three independent families support the direction is capped and the note is recorded.

Score = 50 + 50 · Σ(weight · net_family_direction) / Σ weights, in favour of the proposed direction. `independent_families_supporting` counts families with net ≥ 0.2 in the proposed direction; the minimum is 3.

## Thresholds
The research threshold (75) is never used as a production threshold. A production threshold exists only when the validation pipeline proposes one from **out-of-sample** windows (highest OOS expectancy net of 0.02R per R of drawdown, ≥ 20 OOS trades, positive expectancy) **and** an admin approves it with a note. Threshold sensitivity tables (full and OOS) are stored with every validation run.

## Hard gates (`core/gates.py`)
G01 data fresh/present · G02 event timestamps verified · G03 spread · G04 slippage · G05 session and market open · G06 no lockout · G07 strategy approved · G08 regime approved/not prohibited/not UNKNOWN · G09 per-trade risk, concurrency, trade count, loss streak, manual lock · G10 daily loss · G11 weekly loss · G12 aggregate exposure and monthly drawdown · G13 min cost-adjusted R:R to TP1 · G14 position size compliant (SKIP on minimum contract) · G15 no unresolved data conflict · G16 provider health · G17 probability model in validated range · G18 not suspended · G19 calendar/timezone verified · G20 price confirmation occurred. Any applicable failure blocks a setup and is listed in the Evidence Inspector.

## Decision order
DATA UNAVAILABLE (integrity/health/calendar) → NO TRADE (market closed) → EVENT LOCKOUT (news phases) → structure/regime → weekly cutoff rule → strategies (approved only, regime pre-check) → per-proposal evaluation (costs, sizing, R:R, risk checks, scoring, calibration, gates) → best candidate by rank (setup > wait > no trade) then score.

WAIT means a strategy's entry setup exists but its trigger has not closed; NO TRADE means no approved setup exists, a gate failed, or score/independence fell short. Different horizons may disagree; the conflict is appended to each setup's contradictory evidence and the reason text.

## Confidence
`core/calibration.py`: Wilson 95% interval of the strategy's recorded OOS (or paper) win frequency, in the score bucket when that bucket has ≥ 10 observations, otherwise overall; needs ≥ 30 recorded trades or G17 fails. Brier score and reliability diagram are exposed on `/calibration`.
