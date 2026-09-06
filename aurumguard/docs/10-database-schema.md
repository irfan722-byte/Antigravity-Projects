# 10 Database schema

Authoritative definition: `backend/app/db/models.py`; migration: `backend/alembic/versions/a55d681388ec_initial_schema.py`.

| Table | Purpose | Append-only |
|---|---|---|
| users | account, role, MFA, lockout, soft delete | no |
| user_settings | timezone, currency, contract spec, risk limits (JSON), notification prefs, horizons, weekend-risk acknowledgement | no |
| refresh_tokens | hashed rotating refresh tokens | no |
| strategies | registry state: status, threshold, validation, backtest summary, approval history, change log | history fields append-only |
| decisions | one row per persisted decision incl. setup (JSON) and evidence inspector (JSON) | yes |
| decision_outcomes | outcome after expiry, MFE/MAE; separate from decisions by design | yes |
| paper_orders / paper_positions / paper_events | paper engine persistence | events append-only |
| notifications | every notification with delivery status and dedup key (unique per user) | yes |
| push_subscriptions | hashed endpoint, subscription JSON, failure count | no |
| audit_log | hash-chained audit rows | yes |
| backtest_runs | backtest/validation jobs and results (JSON) | yes |
| economic_events | point-in-time event store with ingestion timestamps | yes |
| provider_health | health snapshots per analysis tick | yes |
| analysis_runs | tick summaries | yes |

Timescale: candles are not persisted in the MVP (the provider is the source; the mock is deterministic). For production, add a `candles` hypertable keyed by (instrument, timeframe, ts) with provider and ingestion columns per the integrity fields, and a `quotes` hypertable; both are additive migrations.
