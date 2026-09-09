# 15 Risk-management specification

Defaults (`config/risk_defaults.json`, editable within bounds): equity 10,000; risk/trade 0.5% [0.1–2]; daily loss 1.5% [0.5–5]; weekly 3% [1–10]; monthly drawdown 6% [2–20]; concurrent positions 2 [1–5]; aggregate open risk 1.5% [0.5–5]; trades/day 4 [1–10]; consecutive losses 3 [1–10]; spread 0.60 [0.10–2.00]; slippage 0.30 [0.05–1.00]; min net R:R 1.5 [1–5]; event-risk preference avoid; daily/weekly lockouts on; Friday cutoff 20:00 local; auto-close paper at cutoff on.

Position size: budget = equity_USD × risk%; effective adverse distance = |entry − stop| + spread + slippage_entry + slippage_exit; risk per lot = distance × contract size + commission; lots = floor(budget / risk per lot, lot step), capped at max lot; if lots < min lot → `SKIP: MINIMUM CONTRACT SIZE EXCEEDS RISK LIMIT`. Never rounded up. AED equity converted at the peg for sizing.

Net reward-to-risk per target = ((|target − entry| − spread − slippage) × size − commission − financing) / ((|entry − stop| + spread + slippage) × size + commission).

Slippage model (deterministic, conservative): 0.05 + 0.4 × spread, ×1.8 off-hours, ×1.3 Asia, ×1.5 in volatility expansion; split half entry, half exit. Financing estimate for swing/weekly from the contract specification's annual rate × notional × days/365.

Locks (server-side, every evaluation and every paper order): daily, weekly, aggregate exposure/monthly drawdown, per-trade/count/streak/manual. Not implementable by design: martingale, loss-scaling, grid, revenge prompts, stop widening (positions store `initial_stop`; the only modification path is breakeven-after-TP1 when the strategy card enables it, and it is logged), hidden leverage, limit bypass, stop removal, uncapped exposure.
