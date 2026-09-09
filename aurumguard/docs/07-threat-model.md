# 07 Threat model

Scope: web/PWA client, FastAPI backend, database, provider integrations, push channel. Method: STRIDE per trust boundary.

| Boundary | Threat | Control in MVP | Residual / next step |
|---|---|---|---|
| Browser ↔ API | Token theft via XSS | Strict CSP on both apps (`default-src 'self'`, no inline script in API responses), React escaping, no `dangerouslySetInnerHTML` | Tokens are in `localStorage` for PWA offline convenience; move to httpOnly cookie + CSRF token before public deployment (`ag_access` cookie path already accepted by `deps.py`) |
| Browser ↔ API | Credential stuffing / brute force | Argon2id hashing, per-IP rate limits on login/register/refresh, lockout after 8 failures for 15 min, optional TOTP MFA | Add CAPTCHA and device fingerprinting for public exposure |
| Browser ↔ API | Session fixation / replay | Short access JWT (60 min), rotating single-use refresh tokens stored hashed, revoke-all on logout | Bind refresh token to client fingerprint |
| API ↔ DB | SQL injection | SQLAlchemy ORM only; no raw SQL | — |
| API | Mass assignment / invalid input | Pydantic schemas with bounds; risk limits validated against server bounds; unknown preference keys rejected | — |
| API | Authorisation bypass | `current_user` on every route, `admin_user` for admin/strategy actions, ownership checks on decisions/positions | Add object-level tests for cross-user access (partially covered) |
| Risk engine | UI bypass of risk limits | Limits re-evaluated server-side on every setup and every paper order; no endpoint can widen a stop or set limits outside bounds | — |
| Providers → API | Poisoned market data | Integrity engine (future timestamps, negative/extreme spread, outliers, duplicates, cross-provider drift); INVALID data blocks setups | Add second provider for cross-check in production |
| Providers → API | Prompt injection through news | News is untrusted data, never fed to an LLM in the MVP; mock includes an injection sample for future tests | If an LLM summariser is added: strip instructions, isolate, never let output reach numeric decisions |
| Push channel | Subscription hijack / spam | Endpoint must be https, hashed for lookup, bound to the authenticated user, deactivated after 5 failures; VAPID keys only via env | Verify payload size limits with a real push service |
| Scheduler | Duplicate processing | Idempotent per (user, horizon, as_of); notification dedup key unique constraint; `max_instances=1` | Redis lock for multi-instance deployment |
| Audit | Tampering | Hash-chained rows + JSONL mirror; chain verification endpoint | Ship JSONL to write-once object storage |
| Secrets | Leakage | `.env.example` names only; gitleaks in CI; settings validation refuses dev secret outside development | Secret manager integration in Terraform |
| Supply chain | Malicious dependency | Exact pins, `pip-audit` and `npm audit` in CI (non-blocking today) | Make audits blocking; add SBOM |
| Live trading | Accidental real orders | No broker code exists; `live_execution: disabled` surfaced in API and UI | Future boundary must add kill switch, idempotency, reconciliation, multi-step confirmation |

Assets ranked: user credentials > risk settings integrity > decision/audit integrity > availability.
