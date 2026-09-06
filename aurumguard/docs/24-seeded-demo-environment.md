# 24 Seeded demo environment

`python -m app.seed [--quick] [--no-validate] [--no-analysis]` creates an admin and a demo user, runs the validation pipeline for PBC-H1 and BRT-M15 on the synthetic path (2025-03..2026-01, or a shorter window with `--quick`), records the validation, and approves each strategy **for DEMO paper trading only** when the OOS sample is ≥ 30 trades, with an approval note that says so. It then runs one analysis pass. It refuses to run when `APP_ENV=production`. Every record produced carries the DEMO label. The seed result (OOS trade counts, proposed thresholds, acceptance checklist) is printed as JSON.

Result of the run performed in this session is recorded in `36-production-readiness-assessment.md`.
