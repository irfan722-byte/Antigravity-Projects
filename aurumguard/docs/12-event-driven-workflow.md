# 12 Event-driven workflow

Tick (every `ANALYSIS_INTERVAL_SECONDS`, default 60):
1. `ensure_records` syncs registry versions; `runtime_states` loads status/threshold/validation.
2. `build_snapshot(now)` fetches quote, candles (M5…D1), macro series, positioning, ETF flows, calendar; validates everything; computes news state and evidence.
3. Per user: load paper engine → advance with new closed M1 candles and the quote (fills, stops, targets, time stops) → paper events → notifications.
4. Account state (equity, daily/weekly realised, month peak, open risks, streaks) → `UserContext`.
5. `DecisionEngine.evaluate_all` → four decisions; cross-horizon conflict detection.
6. Persist a decision when status/strategy/stop changed or 15 minutes elapsed (idempotent per as_of); publish SSE; notify on transitions.
7. Optional automatic paper entry for confirmed setups (server-side risk re-check).
8. News-phase transitions → EVENT_APPROACHING / LOCKOUT_STARTED / LOCKOUT_ENDED notifications.
9. Risk locks → RISK_LIMIT_REACHED (deduplicated per day).
10. Friday workflow: review notification one hour before cutoff; automatic paper closure at cutoff unless the user recorded a weekend-risk override; weekend-gap warning otherwise.
11. Outcome recording for expired setups (mid-path evaluation, MFE/MAE).
12. Provider health and analysis-run rows.

Idempotency: (user, horizon, as_of) uniqueness for decisions; unique (user, dedup_key) for notifications; paper engine rejects out-of-order time; scheduler `max_instances=1`.
