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

Requirements: Python 3.11 or newer, Node.js 20 or newer. Use two terminals: one for the backend, one for the frontend.
Run the backend commands from `aurumguard/backend` and the frontend commands from `aurumguard/frontend`.
Running `npm` from any other folder picks up the older root `package.json` and fails with "Missing script".

### Linux / macOS
```bash
# terminal 1: backend
cd aurumguard/backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
.venv/bin/python -m app.seed --quick      # creates demo users; prints the demo credentials
.venv/bin/uvicorn app.main:app --port 8000

# terminal 2: frontend
cd aurumguard/frontend
npm ci && cp .env.example .env.local
npm run dev
```

### Windows (cmd)
```bat
:: terminal 1: backend
cd aurumguard\backend
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
copy .env.example .env
.venv\Scripts\python -m app.seed --quick
.venv\Scripts\uvicorn app.main:app --port 8000

:: terminal 2: frontend
cd aurumguard\frontend
npm ci
copy .env.example .env.local
npm run dev
```
If `python` is not found, use `py -3.11` for the first command. In PowerShell replace `copy` with `Copy-Item`.

Open http://localhost:3000 and log in with the demo accounts the seed creates (also printed at the end of its output):

| Role  | Email                    | Password            |
|-------|--------------------------|---------------------|
| admin | admin@aurumguard.demo   | AdminDemo-Pass-2026 |
| user  | demo@aurumguard.demo    | DemoUser-Pass-2026  |

These accounts exist only in your local demo database. Eight wrong passwords lock an account for 15 minutes. Or `docker compose up --build`.

## Live prices (optional)

The demo runs on synthetic data. To analyse **real XAU/USD prices** you need a Twelve Data API key
(https://twelvedata.com, the free plan is enough for a 5-minute analysis cadence). Live *execution* stays
disabled; this only changes where prices come from.

1. Seed the demo first with the mock provider (validation always runs on synthetic data).
2. In `aurumguard/backend/.env` set:
   ```
   MARKET_DATA_PROVIDER=twelvedata
   TWELVEDATA_API_KEY=<your key>
   CALENDAR_PROVIDER=none       # otherwise synthetic events would lock out real prices
   NEWS_PROVIDER=none
   ANALYSIS_INTERVAL_SECONDS=300 # free tier: ~700 credits/day; 60 needs a paid plan
   ```
3. Verify the key before starting the server: `python -m app.check_provider` (Windows: `.venv\Scripts\python -m app.check_provider`).
   It prints where HTTPS trust comes from, one quote, three candle batches and the estimated daily credit
   usage, and exits non-zero on failure. Run it again after changing `.env`.
4. Start uvicorn. The red DEMO banner is replaced by an amber banner that names the live source and every
   input that is still synthetic (macro series, positioning, ETF flows) or disabled (calendar, news).

What live mode does **not** give you: observed bid/ask (the quote endpoint is mid-only, so the spread is a
configurable cost assumption, `TWELVEDATA_ASSUMED_SPREAD_USD`), real economic-event awareness, or real
intermarket data. Treat setups produced in this mode as a plumbing test on real prices, not as validated signals.

### `CERTIFICATE_VERIFY_FAILED` when checking the provider

```
[check] quote FAILED: twelvedata request failed: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed
```

The API key is fine - the connection failed before the request was sent. Python verifies HTTPS against its
own bundled certificate list, not the Windows or macOS store, so a machine where antivirus or a company
proxy inspects TLS traffic (Kaspersky, ESET, Bitdefender, Avast, Zscaler, Netskope, ...) presents a
certificate signed by a private root that the browser trusts and Python does not. In order of preference:

1. Install the pinned OS trust bridge and restart the check - this is the default and usually all it takes:
   `.venv\Scripts\pip install -r requirements.txt` (it now includes `truststore`).
2. Export the inspecting root certificate to a `.pem` file and point `HTTPS_CA_BUNDLE` at it in `.env`.
3. Exempt `api.twelvedata.com` from HTTPS scanning in the antivirus settings.

`python -m app.check_provider` names the authority your machine is served, so you can tell which product is
doing it. Never disable certificate verification: it would expose the feed to anyone on the network path.

## Tests
```bash
cd aurumguard/backend && .venv/bin/pytest -q            # 69 tests (Windows: .venv\Scripts\pytest -q)
cd aurumguard/frontend && npm run typecheck && npm run lint && npm test && npx playwright test
```

## Documentation
`docs/01-executive-summary.md` … `docs/36-production-readiness-assessment.md` cover assumptions, architecture, threat model, provider plan and licensing checklist, schema, API, workflows, strategy format, decision framework, risk specification, news state machine, backtesting methodology, IA and wireframes, setup, migrations, seed, tests, CI/CD, security, monitoring, deployment, runbook, user guide, model and strategy cards, limitations, pre-production checklist and readiness assessment.

## Disclosure
AurumGuard provides rule-based analysis and paper trading for education and personal research. It is not investment advice, holds no regulatory approval, and cannot guarantee any outcome. Trading gold involves risk of loss. Demo mode uses synthetic data labelled **DEMO DATA**.
