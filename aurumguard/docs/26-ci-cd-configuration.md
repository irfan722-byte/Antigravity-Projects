# 26 CI/CD configuration

`.github/workflows/aurumguard-ci.yml` (path-filtered to `aurumguard/**`): backend job (ruff, bandit, alembic upgrade on SQLite, pytest), frontend job (typecheck, eslint, vitest, next build), security job (gitleaks, pip-audit, npm audit — non-blocking today; make blocking after triage). Deployment is not automated in the MVP; images are built from the two Dockerfiles. The existing `firebase-hosting-merge.yml` belongs to the other project in this repository and is untouched.
