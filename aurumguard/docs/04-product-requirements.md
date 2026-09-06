# 04 Product requirements (traceability)

| Requirement | Implementation | Verification |
|---|---|---|
| Continuous XAU/USD analysis | `services/analysis.py` scheduler tick (APScheduler, default 60 s) | `tests/test_api.py::test_analysis_run_decisions_feed_and_evidence` |
| Exactly one of six statuses per horizon | `core/setup.py::DecisionStatus`, `core/decision.py` | `tests/test_decision_engine.py::test_all_horizons_produce_exactly_one_status` |
| Four horizons, separately configurable | `core/decision.py::HORIZON_TIMEFRAMES`, strategy `horizon` field | same |
| Mobile notifications | `notifications/service.py`, `notifications/webpush.py`, `src/sw.ts`, `src/lib/push.ts` | mock push exercised in API tests; real delivery **unverified** |
| Major USD event analysis | `core/news_state.py`, `providers/mock/calendar.py` | `tests/test_news_state.py` |
| Technical, structure, macro, positioning, intermarket, liquidity, volatility, news evidence | `services/snapshot.py`, `core/evidence.py` families | `tests/test_structure_regime_scoring.py` |
| Entry zone, stop, TP1, TP2, expiry, R:R, sizing | `core/strategies/*`, `core/risk.py`, `core/setup.py::TradeSetup` (39 fields) | `tests/test_risk.py`, decision tests |
| Reject weak/stale/conflicting/risky opportunities | `core/gates.py` (G01–G20), `core/integrity.py` | gate tests, integrity tests |
| Capital preservation | `core/risk.py` limits, locks, server-side enforcement in `services/paper_service.py` | `test_risk_lock_blocks_setups_across_days`, API tests |
| Record every decision | `db/models.py::DecisionRecord`, `AuditLog` hash chain | API test verifies chain |
| Configurable defaults, not hard-coded | `config.py` defaults + per-user `UserSettings` | onboarding/settings API tests |
| Demo mode clearly labelled | `X-Demo-Data` header, `demo_data` on every payload, red banner in UI | API tests |

The full page list (26) and dashboard priorities are in `18-product-information-architecture.md`.
