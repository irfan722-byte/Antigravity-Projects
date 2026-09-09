"""Seed a demo environment: admin + demo user, validation runs on DEMO data for the two
candidate strategies, approval with an explicit DEMO caveat, and one analysis pass.

Run:  python -m app.seed
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime

from .backtest.engine import Backtester
from .backtest.validation import run_validation
from .config import get_settings, load_json_config
from .core.contract_spec import get_spec
from .core.risk import RiskLimits
from .core.strategies import build_strategies
from .db.base import Base, SessionLocal, engine
from .db.models import BacktestRun, User, UserSettings
from .providers.registry import build_providers
from .services import audit, strategy_service
from .services.analysis import AnalysisService
from .services.auth import hash_password, new_id

UTC = UTC
DEMO_USERS = [
    ("admin@aurumguard.demo", "AdminDemo-Pass-2026", "admin"),
    ("demo@aurumguard.demo", "DemoUser-Pass-2026", "user"),
]


def seed(validate: bool = True, run_analysis: bool = True, quick: bool = False) -> dict:
    s = get_settings()
    if s.app_env == "production":
        raise SystemExit("refusing to seed demo data in production")
    Base.metadata.create_all(engine)
    db = SessionLocal()
    out: dict = {"users": [], "validations": {}}
    try:
        defaults = RiskLimits.defaults().to_dict()
        for email, pw, role in DEMO_USERS:
            u = db.query(User).filter(User.email == email).first()
            if u is None:
                # Earlier seeds used a reserved ".local" domain that the login schema rejects; rename in place.
                legacy = db.query(User).filter(User.email == email.replace("@aurumguard.demo", "@aurumguard.local")).first()
                if legacy is not None:
                    legacy.email = email
                    db.commit()
                    audit.record(db, "seed", "seed.user_email_migrated", legacy.id, {"to": email})
                    u = legacy
            if u is None:
                u = User(id=new_id(), email=email, password_hash=hash_password(pw), role=role, disclosure_accepted_at=datetime.now(tz=UTC), onboarding_completed=True)
                db.add(u)
                db.flush()
                db.add(UserSettings(user_id=u.id, timezone=s.default_timezone, account_currency="USD", risk_limits=defaults, notification_prefs={"enabled": True, "quiet_start": load_json_config("risk_defaults.json")["defaults"]["quiet_hours_start_local"], "quiet_end": load_json_config("risk_defaults.json")["defaults"]["quiet_hours_end_local"], "auto_paper_trade": role == "user"}, horizons_enabled={"SCALP": False, "INTRADAY": True, "SWING": True, "WEEKLY": True}))
                db.commit()
                audit.record(db, "seed", "seed.user_created", u.id, {"role": role})
            out["users"].append({"email": email, "password": pw, "role": role})
        strategy_service.ensure_records(db)
        # Validation and the seed's analysis pass always use DEMO data: with a live provider this would
        # spend hundreds of API credits fetching months of candles, and the seed must stay reproducible.
        providers = build_providers(s.model_copy(update={"market_data_provider": "mock"}))
        if validate:
            bt = Backtester(providers.market, providers.calendar, get_spec("mock-generic-100oz"))
            strategies = build_strategies()
            start = datetime(2025, 3, 1, tzinfo=UTC) if not quick else datetime(2025, 9, 1, tzinfo=UTC)
            end = datetime(2026, 1, 31, tzinfo=UTC) if not quick else datetime(2025, 12, 1, tzinfo=UTC)
            admin = db.query(User).filter(User.role == "admin").first()
            for sid in ("PBC-H1", "BRT-M15"):
                print(f"[seed] validating {sid} on DEMO data {start.date()}..{end.date()} (this takes a few minutes)", flush=True)
                report = run_validation(bt, strategies[sid], start, end, train_days=60 if not quick else 30, test_days=30 if not quick else 15, data_label="DEMO")
                run = BacktestRun(id=new_id(), strategy_id=sid, strategy_version=strategies[sid].definition.version, kind="validation", label="SEED_VALIDATION", data_label="DEMO", config_hash="", trades_hash=report.get("full_run_hash", ""), requested_by="seed", status="DONE", started_at=datetime.now(tz=UTC), finished_at=datetime.now(tz=UTC), result=report)
                db.add(run)
                db.commit()
                strategy_service.record_validation(db, sid, report, "seed")
                payload = report["calibration_payload"]
                out["validations"][sid] = {"oos_trades": payload["sample_size"], "oos_expectancy_r": payload["expectancy_r"], "proposed_threshold": report["proposed_threshold"], "checklist": report["acceptance_checklist"]}
                th = report["proposed_threshold"] if report["proposed_threshold"] is not None else 60.0
                if payload["sample_size"] >= strategy_service.MIN_SAMPLE:
                    strategy_service.approve(db, sid, admin.id, f"DEMO SEED APPROVAL for paper trading on synthetic data only. Pipeline validation, not a market validation. Re-validate on licensed data and obtain a real approval before any real use. OOS trades={payload['sample_size']}, expectancy={payload['expectancy_r']}R.", threshold=th)
                    print(f"[seed] {sid} approved for DEMO paper trading (threshold {th})", flush=True)
                else:
                    print(f"[seed] {sid} NOT approved: OOS sample {payload['sample_size']} < {strategy_service.MIN_SAMPLE}", flush=True)
        if run_analysis:
            svc = AnalysisService(providers, s)
            out["analysis"] = svc.run_once(db)
    finally:
        db.close()
    return out


if __name__ == "__main__":
    quick = "--quick" in sys.argv
    res = seed(validate="--no-validate" not in sys.argv, run_analysis="--no-analysis" not in sys.argv, quick=quick)
    import json

    print(json.dumps(res, indent=2, default=str))
    print("\n[seed] DEMO logins (synthetic data, paper trading only):", flush=True)
    for u in res.get("users", []):
        print(f"[seed]   {u['role']:<5}  email: {u['email']:<28} password: {u['password']}", flush=True)
    print("[seed] Open http://localhost:3000 after starting uvicorn on port 8000.", flush=True)
