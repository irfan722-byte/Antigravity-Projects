# 06 Architecture

```
┌──────────────── Frontend (Next.js 15 PWA) ────────────────┐
│ App Router pages · typed fetch client · SSE stream        │
│ Serwist service worker: precache + Web Push handlers      │
└───────────────▲──────────────────────────▲────────────────┘
                │ REST /api (JWT bearer)   │ /api/stream (SSE)
┌───────────────┴──────────────────────────┴────────────────┐
│ FastAPI app (app/main.py)                                  │
│  routers: auth users market decisions risk paper           │
│           strategies/backtests misc(calendar regime …)     │
│  middleware: rate limit, security headers, CORS            │
├────────────────────────────────────────────────────────────┤
│ Services                                                   │
│  analysis loop (APScheduler) ─► snapshot builder            │
│  ─► DecisionEngine ─► persist/notify/SSE/paper/outcomes     │
│  paper_service · strategy_service · notifications · audit  │
├────────────────────────────────────────────────────────────┤
│ Core (pure, deterministic, unit-tested)                    │
│  candles integrity indicators structure regime evidence    │
│  gates risk contract_spec calibration news_state           │
│  strategies/{base,pullback,breakout,range,post_news}       │
│  decision (orchestrator) · paper/engine · backtest/*       │
├────────────────────────────────────────────────────────────┤
│ Providers (interfaces + adapters)                          │
│  market · calendar · trading calendar · macro · news       │
│  positioning · etf · push   [mock set] [twelvedata: real]  │
├────────────────────────────────────────────────────────────┤
│ Storage: PostgreSQL (SQLite in dev) via SQLAlchemy/Alembic │
│          append-only audit (DB + JSONL), Redis optional    │
└────────────────────────────────────────────────────────────┘
```

**Service separation.** The specification asks for separate ingestion, analytics, backtesting and notification services. In the MVP they are separate Python packages inside one process (ingestion = `services/snapshot.py` + providers; analytics = `core/decision.py`; backtesting = `backtest/*` executed as background tasks; notifications = `notifications/*`). Each has no dependency on FastAPI and can be moved to its own worker behind the same interfaces; `docker-compose.yml` shows the single-process deployment. Splitting them is a deployment change, not a code change.

**Determinism and point-in-time.** All analysis functions take an explicit `as_of`; candle slices exclude bars that close after it; the calendar is queried "as of" so actuals are unknown before release; the mock provider rebuilds the forming bar only from minutes before `as_of`; the backtester replays the same code path.

**Native app readiness.** The API is stateless JSON with bearer tokens, SSE for live updates and a push-subscription endpoint; a native client needs no backend change.

**Key decisions.**
- Pure-Python core with numpy (no pandas) for reproducibility and simple pinning.
- One synthetic path cached per process for demo/backtests (vectorised, prefix-stable).
- No LLM in the decision path. The only place an LLM could be added is a news summariser behind `NewsProvider` with untrusted-input handling; not included.
