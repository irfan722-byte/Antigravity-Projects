# 21 Local development setup

Prerequisites: Python 3.11, Node 22, (optional) Docker.

Backend
```bash
cd aurumguard/backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env            # defaults: sqlite, mock providers, analysis loop on
.venv/bin/alembic upgrade head   # or let the app create tables in development
.venv/bin/python -m app.seed --quick   # demo users + DEMO validation/approval (minutes)
.venv/bin/uvicorn app.main:app --reload --port 8000
```
Demo credentials printed by the seed: `admin@aurumguard.demo / AdminDemo-Pass-2026`, `demo@aurumguard.demo / DemoUser-Pass-2026`.

Frontend
```bash
cd aurumguard/frontend
npm ci && cp .env.example .env.local
npm run dev            # http://localhost:3000 (service worker disabled in dev)
npm run build && npm start   # production mode with PWA/service worker
```

Tests
```bash
cd aurumguard/backend && .venv/bin/pytest -q          # ~2 min (backtest tests included)
cd aurumguard/frontend && npm run typecheck && npm run lint && npm test && npx playwright test
```

Docker: `docker compose up --build` (PostgreSQL + Redis + API + web, mock providers).

Expected: `GET /health` → `{"status":"ok","demo_data":true,...}`; the UI shows the red DEMO DATA banner; `/dashboard` shows four horizon decisions after the first analysis tick (≤ 60 s).
