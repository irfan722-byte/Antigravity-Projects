# 27 Security configuration

Implemented: Argon2id passwords with policy; JWT HS256 access tokens (60 min) and rotating hashed refresh tokens; optional TOTP MFA; login lockout; role-based access (user/admin); per-IP rate limits (global and per sensitive route); security headers (CSP, nosniff, frame deny, referrer, permissions policy, HSTS in production, no-store); CORS allow-list; Pydantic validation with bounds; ORM only; hash-chained audit log; secrets from environment only with production validation; `.env.example` names only; gitleaks/bandit/pip-audit/npm audit in CI; non-root containers; data minimisation, export and deletion.

Deferred (see threat model): httpOnly cookie sessions + CSRF, Redis-backed rate limiting for multiple instances, secret-manager integration, WAF, SBOM.
