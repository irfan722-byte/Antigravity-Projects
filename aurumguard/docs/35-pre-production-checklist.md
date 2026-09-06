# 35 Pre-production checklist

- [x] Core tests pass (69 backend, 7 frontend unit, Playwright smoke)
- [x] Data-health lockouts work (injected provider failure → DATA UNAVAILABLE; stale/invalid data blocks)
- [x] Risk limits cannot be bypassed through normal UI actions (server-side re-check on setups and paper orders; bounds on settings)
- [x] Position sizing verified (floor, minimum-contract skip, cost inclusion, spec dependence)
- [x] Economic-event timestamps processed with verification, revision, delay and conflict handling
- [x] Timezones correct (tz-aware everywhere, DST-aware sessions, Dubai cutoff test)
- [x] Backtests reproducible (hash test)
- [x] No look-ahead identified in tests (closed-bar guard, forming-bar rebuild, as-of calendar)
- [x] Costs included in R:R and sizing
- [x] Signal evidence auditable (21-section inspector, immutable decision, separate outcome)
- [ ] Probability outputs calibrated on real data (only DEMO samples exist)
- [ ] Paper trading has sufficient recorded evaluation (none on real data)
- [ ] Critical security issues resolved (no critical findings known; cookie-session migration and external pentest pending)
- [ ] Provider licences confirmed
- [ ] Legal and compliance review completed
- [ ] User-facing performance claims supportable (none are made; all samples labelled DEMO)
- [x] Live automatic execution disabled
