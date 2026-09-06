# 11 API specification

OpenAPI is generated at `/api/openapi.json` (docs at `/api/docs` outside production). All routes are prefixed `/api`, JSON only, bearer JWT unless noted.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | /auth/register, /auth/login, /auth/refresh | none | account, tokens (rate-limited) |
| POST | /auth/logout, /auth/mfa/setup, /auth/mfa/enable, /auth/mfa/disable | user | session and TOTP |
| GET | /auth/me | user | identity |
| POST | /users/onboarding | user | timezone, currency, equity, cutoff, horizons |
| GET/PUT | /users/settings | user | preferences, weekend-risk acknowledgement |
| PUT | /users/risk-limits | user | limits validated against bounds |
| GET | /users/export · POST /users/delete | user | privacy |
| GET | /market/quote, /market/candles, /market/structure, /market/snapshot, /market/health | user | data and integrity |
| GET | /decisions/latest, /decisions/feed, /decisions/{id} · POST /decisions/evaluate-now | user | decisions and Evidence Inspector |
| GET | /risk/status, /risk/contract-specs · POST /risk/position-size | user | risk and sizing |
| GET | /paper/positions, /paper/journal, /paper/performance, /paper/export.csv · POST /paper/orders, /paper/close | user | paper trading (server-side risk checks) |
| GET | /strategies, /strategies/{id} · POST /strategies/{id}/action | user / admin | registry and approval workflow |
| POST/GET | /backtests, /backtests/{id} | user | background backtest/validation jobs |
| GET | /performance/strategies, /calibration | user | separated performance samples, calibration |
| GET | /calendar, /calendar/{id}, /regime | user | context |
| GET/POST | /notifications, /notifications/{id}/read, /push/subscribe, /push/vapid-public-key | user | notification centre and push |
| GET | /stream | user | Server-Sent Events (decisions, notifications, analysis runs) |
| GET | /audit | user (own) / admin (all + chain check) | audit |
| GET/POST | /admin/overview, /admin/run-analysis | admin | operations |
| GET | /health, /api/meta | none | liveness, demo flag, disclosure |

Error format: `{"detail": "..."}` with 400/401/403/404/409/422/429/503. Every payload that derives from market data carries `demo_data`.
