# 29 Deployment instructions

1. Provision PostgreSQL 16, Redis 7 (optional), object storage; put secrets in the platform secret manager.
2. Set backend env from `backend/.env.example` with `APP_ENV=paper|staging|production`, a strong `SECRET_KEY`, `DATABASE_URL`, `CORS_ORIGINS`, provider keys and VAPID keys (generate with `python -c "from pywebpush import webpush"`-compatible tooling or `npx web-push generate-vapid-keys`). The app refuses to start with the dev secret or SQLite outside development.
3. Build images: `docker build backend`, `docker build frontend --build-arg NEXT_PUBLIC_API_URL=https://api.example`.
4. Run `alembic upgrade head`, then start the API (single instance while the scheduler is in-process; for multiple instances move the scheduler to one worker).
5. Serve the frontend behind HTTPS (required for service workers and push).
6. Environments: development (SQLite, mocks), staging (Postgres, mocks), paper (Postgres, licensed data, mock push or webpush), production (all real, legal sign-off). Promotion requires the pre-production checklist.
