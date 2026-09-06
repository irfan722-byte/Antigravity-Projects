# AurumGuard

Rule-based **XAU/USD** (spot gold) analysis, risk management, paper trading and mobile notifications. Progressive Web App + FastAPI backend.

> **Status: MVP in DEMO mode.** Runs end-to-end on synthetic data behind a provider abstraction. Not production-ready: no licensed data, no real-data validation, no legal review. Live order execution is disabled by design. Nothing here is investment advice.

## What it does
- Evaluates four horizons (scalp, intraday, swing, weekly) and returns exactly one status each: **BUY SETUP · SELL SETUP · WAIT · NO TRADE · EVENT LOCKOUT · DATA UNAVAILABLE**.
- Issues a setup only when data integrity, an approved strategy, regime approval, independent evidence, cost-adjusted reward-to-risk, position sizing and 20 hard gates all pass; every setup carries 39 mandatory fields and a 21-section Evidence Inspector.
- Enforces risk limits server-side (per trade, daily, weekly, monthly drawdown, exposure, streaks); never martingale, never stop widening.
- Paper-trades with bid/ask, slippage, conservative same-bar and gap rules; Friday weekly-position workflow; economic-event state machine; push notifications with dedup, throttling and quiet hours.
- Backtests with walk-forward validation, Monte Carlo, cost and threshold sensitivity; strategies need recorded validation **and** a human approval to go live.

## Quick start
```bash
# backend
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env && .venv/bin/python -m app.seed --quick && .venv/bin/uvicorn app.main:app --port 8000
# frontend
cd ../frontend && npm ci && cp .env.example .env.local && npm run dev
```
Open http://localhost:3000 — log in with the demo credentials printed by the seed. Or `docker compose up --build`.

## Tests
```bash
cd backend && .venv/bin/pytest -q            # 69 tests
cd frontend && npm run typecheck && npm run lint && npm test && npx playwright test
```

## Documentation
`docs/01-executive-summary.md` … `docs/36-production-readiness-assessment.md` cover assumptions, architecture, threat model, provider plan and licensing checklist, schema, API, workflows, strategy format, decision framework, risk specification, news state machine, backtesting methodology, IA and wireframes, setup, migrations, seed, tests, CI/CD, security, monitoring, deployment, runbook, user guide, model and strategy cards, limitations, pre-production checklist and readiness assessment.

## Disclosure
AurumGuard provides rule-based analysis and paper trading for education and personal research. It is not investment advice, holds no regulatory approval, and cannot guarantee any outcome. Trading gold involves risk of loss. Demo mode uses synthetic data labelled **DEMO DATA**.
