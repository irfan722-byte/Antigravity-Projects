# 36 Production-readiness assessment

**Verdict: NOT production-ready. Ready for internal demo and for the next stage (licensed data, real validation, security and legal review).**

## Verification record (what was actually executed in this session)
- Backend: `pytest` — 69 passed (including API, backtest reproducibility, decision engine, paper engine); `ruff check` clean; `bandit -ll` no findings; `alembic upgrade head` applied on SQLite.
- Frontend: `tsc --noEmit` clean; `next lint` clean; `vitest` 7 passed; `next build` produced 28 routes and `public/sw.js`; Playwright smoke: manifest test passed, two browser tests failed in this sandbox (see below).
- Demo seed: run with `--quick`; result recorded in this file's appendix when available (see PR description for the printed JSON).
- Not executed: real provider calls (no credentials), real push delivery, Docker image builds (Docker present but not exercised), load tests, accessibility audit, PostgreSQL run.

## Quality gates status
See `35-pre-production-checklist.md`: 11 of 17 gates met; the six open gates all depend on real data, external review or licensing, not on missing code.

## Top risks
1. Strategy edge is unproven; the seed approval is explicitly DEMO-only and must be revoked on real data until re-validated.
2. Execution-cost model is synthetic; a bid/ask feed is required before paper results mean anything.
3. Session storage in localStorage; migrate to httpOnly cookies before public exposure.
4. Single-instance scheduler; acceptable for one user, not for a service.

## Recommended next stage
Licence a bid/ask market feed and a calendar vendor → persist candles → run the validation pipeline on ≥ 2 years of real data → human review with the acceptance checklist → 8+ weeks of paper trading → security review → legal review → then reconsider "production" for personal use only.

## Appendix: demo seed run (this session, `python -m app.seed --quick`, window 2025-09-01..2025-12-01, DEMO data)
| Strategy | OOS trades | OOS expectancy | Proposed threshold | Approved for DEMO paper? |
|---|---|---|---|---|
| PBC-H1 | 3 | +0.56R | none (too few trades) | **No** — approval gate refused (sample < 30) |
| BRT-M15 | 51 | +0.19R | 50 | Yes, DEMO-only note recorded; OOS CI lower bound is below zero, so on real data this would not pass the checklist |

Analysis pass after seeding: 2 users, 8 decisions, 8 notifications recorded. These numbers validate the pipeline; they say nothing about real-market edge.
