from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...config import load_json_config
from ...core.contract_spec import SPECS
from ...core.risk import RiskLimits
from ...core.timeutil import resolve_tz
from ...db.base import get_db
from ...db.models import DecisionRecord, NotificationRecord, PaperEventRecord, PaperOrderRecord, PaperPositionRecord, PushSubscription, RefreshToken, User, UserSettings
from ...services import audit
from ...services.auth import verify_password
from ..deps import current_user
from ..schemas import DeleteAccountIn, OnboardingIn, RiskLimitsIn, SettingsIn

router = APIRouter(prefix="/users", tags=["users"])
UTC = UTC


def _settings_out(us: UserSettings) -> dict:
    return {"timezone": us.timezone, "account_currency": us.account_currency, "contract_spec": SPECS[us.contract_spec_id].to_dict(), "risk_limits": us.risk_limits, "risk_bounds": load_json_config("risk_defaults.json")["bounds"], "notification_prefs": us.notification_prefs, "horizons_enabled": us.horizons_enabled, "locale": us.locale, "theme": us.theme, "weekend_risk_ack_at": us.weekend_risk_ack_at, "updated_at": us.updated_at}


@router.post("/onboarding")
def onboarding(body: OnboardingIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        resolve_tz(body.timezone)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    us = user.settings
    us.timezone = body.timezone
    us.account_currency = body.account_currency
    limits = RiskLimits.defaults().to_dict() | {"account_equity": body.account_equity, "account_currency": body.account_currency, "friday_cutoff_local": body.friday_cutoff_local}
    if body.risk_per_trade_pct is not None:
        limits["risk_per_trade_pct"] = body.risk_per_trade_pct
    problems = RiskLimits(**limits).validate()
    if problems:
        raise HTTPException(400, "; ".join(problems))
    us.risk_limits = limits
    us.horizons_enabled = {h: (h in body.horizons) for h in ("SCALP", "INTRADAY", "SWING", "WEEKLY")}
    user.onboarding_completed = True
    db.commit()
    audit.record(db, user.id, "user.onboarding_completed", user.id, {"timezone": body.timezone, "currency": body.account_currency})
    return _settings_out(us)


@router.get("/settings")
def get_settings_(user: User = Depends(current_user)):
    return _settings_out(user.settings)


@router.put("/settings")
def put_settings(body: SettingsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    us = user.settings
    if body.timezone:
        try:
            resolve_tz(body.timezone)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        us.timezone = body.timezone
    if body.locale:
        us.locale = body.locale
    if body.theme:
        us.theme = body.theme
    if body.notification_prefs is not None:
        us.notification_prefs = {**(us.notification_prefs or {}), **body.notification_prefs}
    if body.horizons_enabled is not None:
        us.horizons_enabled = {**(us.horizons_enabled or {}), **{k: bool(v) for k, v in body.horizons_enabled.items() if k in ("SCALP", "INTRADAY", "SWING", "WEEKLY")}}
    if body.weekend_risk_acknowledged is not None:
        us.weekend_risk_ack_at = datetime.now(tz=UTC) if body.weekend_risk_acknowledged else None
        audit.record(db, user.id, "user.weekend_risk_override", user.id, {"acknowledged": body.weekend_risk_acknowledged, "statement": "User explicitly acknowledged weekend gap risk and disabled automatic Friday paper closure." if body.weekend_risk_acknowledged else "override removed"})
    db.commit()
    audit.record(db, user.id, "user.settings_updated", user.id, body.model_dump(exclude_none=True))
    return _settings_out(us)


@router.put("/risk-limits")
def put_risk_limits(body: RiskLimitsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    us = user.settings
    merged = RiskLimits.defaults().to_dict() | (us.risk_limits or {}) | body.model_dump(exclude_none=True)
    limits = RiskLimits(**{k: v for k, v in merged.items() if k in RiskLimits.__dataclass_fields__})
    problems = limits.validate()
    if problems:
        raise HTTPException(400, "; ".join(problems))
    before = dict(us.risk_limits or {})
    us.risk_limits = limits.to_dict()
    db.commit()
    audit.record(db, user.id, "user.risk_limits_updated", user.id, {"before": before, "after": us.risk_limits})
    return _settings_out(us)


@router.get("/export")
def export_data(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Data-portability export of everything stored about the user."""
    def rows(model):
        return [{c.name: getattr(r, c.name) for c in model.__table__.columns} for r in db.query(model).filter(model.user_id == user.id).all()]

    audit.record(db, user.id, "user.export", user.id)
    return {"user": {"id": user.id, "email": user.email, "created_at": user.created_at}, "settings": _settings_out(user.settings), "decisions": rows(DecisionRecord), "paper_orders": rows(PaperOrderRecord), "paper_positions": rows(PaperPositionRecord), "paper_events": rows(PaperEventRecord), "notifications": rows(NotificationRecord)}


@router.post("/delete", status_code=204)
def delete_account(body: DeleteAccountIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "password incorrect")
    now = datetime.now(tz=UTC)
    for model in (PushSubscription, NotificationRecord, PaperEventRecord):
        db.query(model).filter(model.user_id == user.id).delete()
    for rec in db.query(RefreshToken).filter(RefreshToken.user_id == user.id).all():
        rec.revoked_at = now
    user.email = f"deleted-{user.id}@example.invalid"
    user.password_hash = "deleted"
    user.mfa_secret = None
    user.mfa_enabled = False
    user.deleted_at = now
    user.onboarding_completed = False
    db.commit()
    audit.record(db, user.id, "user.deleted", user.id, {"note": "personal data removed; decision and paper records retained pseudonymously for audit"})
