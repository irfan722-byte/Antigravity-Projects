# 32 Model cards

## Regime classifier (`regime-v1`)
Inputs: H4 candles (ADX 14, ±DI, realised vol percentile over 100 bars, ATR state), swing structure H4/D1, daily gold/DXY/10y/2y/real-yield/equity/vol series (30-bar correlations, 5-bar moves), news phase, session, spread ratio. Output: primary regime, tags, confidence (share of supporting measurements), supporting/conflicting lists. Limitations: correlation windows short; RISK_ON/OFF heuristics; UNKNOWN below 60 bars. No learned parameters.

## Evidence scorer (`scoring-v0.1-research`)
Weighted average of family nets with correlation collapsing and domination cap. Research weights; not validated. Score is never sufficient alone.

## Calibration (`calibration-wilson-v1`)
Frequency-based interval from labelled OOS/paper samples by score bucket. Requires ≥ 30 trades; buckets ≥ 10. Brier reported. Drift monitoring: live outcome buckets vs validation buckets on `/calibration`. Rollback: versions are strings on every decision.

## Slippage model
Deterministic function of spread, session and volatility state; conservative by construction; to be replaced by measured fills when a bid/ask feed exists.

No machine-learned model and no LLM is in the decision path.
