"""AurumGuard API application factory."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routers import auth, decisions, market, misc, paper, risk, strategies, users
from .config import get_settings
from .db.base import Base, SessionLocal, engine
from .providers.registry import build_providers
from .services.analysis import AnalysisService
from .services.limiter import RateLimiter
from .services.strategy_service import ensure_records

log = logging.getLogger("aurumguard")


def _scheduler(app: FastAPI):
    from apscheduler.schedulers.background import BackgroundScheduler

    def tick() -> None:
        db = SessionLocal()
        try:
            app.state.analysis.run_once(db)
        except Exception as exc:  # noqa: BLE001
            log.exception("analysis tick failed: %s", exc)
        finally:
            db.close()

    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(tick, "interval", seconds=app.state.settings.analysis_interval_seconds, id="analysis", max_instances=1, coalesce=True)
    return sched


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = app.state.settings
    problems = s.validate_for_environment()
    if problems and s.app_env in ("staging", "paper", "production"):
        raise RuntimeError("configuration problems: " + "; ".join(problems))
    for p in problems:
        log.warning("config: %s", p)
    if s.database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)  # dev/test convenience; migrations are authoritative elsewhere
    db = SessionLocal()
    try:
        ensure_records(db)
    finally:
        db.close()
    app.state.scheduler_running = False
    sched = None
    if s.analysis_enabled:
        sched = _scheduler(app)
        sched.start()
        app.state.scheduler_running = True
    yield
    if sched:
        sched.shutdown(wait=False)


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    app = FastAPI(title="AurumGuard API", version="0.1.0", lifespan=lifespan, docs_url="/api/docs" if settings.app_env != "production" else None, redoc_url=None, openapi_url="/api/openapi.json" if settings.app_env != "production" else None)
    app.state.settings = settings
    app.state.providers = build_providers(settings)
    app.state.analysis = AnalysisService(app.state.providers, settings)
    app.state.limiter = RateLimiter(settings.rate_limit_per_minute)
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        try:
            app.state.limiter.check(request, "global")
        except Exception as exc:  # noqa: BLE001
            from fastapi import HTTPException

            if isinstance(exc, HTTPException):
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
            raise
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if settings.app_env == "production":
            resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        resp.headers["X-Demo-Data"] = "true" if app.state.providers.demo_mode else "false"
        return resp

    api = "/api"
    for r in (auth.router, users.router, market.router, decisions.router, risk.router, paper.router, strategies.router, misc.router):
        app.include_router(r, prefix=api)

    @app.get("/health")
    def health():
        return {"status": "ok", "env": settings.app_env, "demo_data": app.state.providers.demo_mode, "scheduler": app.state.scheduler_running}

    @app.get("/api/meta")
    def meta():
        return {"name": settings.app_name, "version": "0.1.0", "demo_data": app.state.providers.demo_mode, "market_data_provider": app.state.providers.market.name, "data_mode": app.state.providers.data_mode, "providers": app.state.providers.summary(), "live_execution": "disabled", "disclosure": "AurumGuard provides rule-based analysis and paper trading for education and personal research. It is not investment advice, has no regulatory approval, and cannot guarantee any outcome. Trading gold involves risk of loss."}

    return app


app = create_app()
