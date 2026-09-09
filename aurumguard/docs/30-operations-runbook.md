# 30 Operations runbook

- **DATA UNAVAILABLE for all users**: check `/api/market/health`; provider failures → verify keys/rate limits; stale candles → provider outage; the system is safe (no setups are issued). Do not "fill" data.
- **Provider disagreement (XPROV_DISAGREE)**: setups blocked; compare mids manually; switch primary provider via `MARKET_DATA_PROVIDER` only after confirming the other feed.
- **Scheduler stopped** (`scheduler_running=false`): restart the API; check logs for the tick exception; decisions resume automatically.
- **Strategy suspended**: read `suspension_reason`; a human must run re-validation and use `reactivate` with a note; two suspensions on the same version retire it.
- **Audit chain broken**: treat as an incident; export JSONL mirror from `AUDIT_DIR`; compare row hashes; do not truncate.
- **Push failures**: subscriptions deactivate after 5 failures; users re-enable from the Notification centre; check VAPID keys and push-service reachability.
- **Backups**: nightly PostgreSQL dumps + audit JSONL to versioned storage; monthly restore test into staging (`alembic current` must equal head).
- **Disaster recovery**: RPO 24 h (dumps), RTO 4 h (rebuild from images + restore); decisions are reproducible from provider data and registry versions.
- **Incident response**: contain (rotate `SECRET_KEY` → all sessions invalid, revoke refresh tokens), assess audit log, notify affected users, post-mortem within 5 working days.
