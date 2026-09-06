from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ...config import get_settings, load_json_config
from ...core.risk import RiskLimits
from ...db.base import get_db
from ...db.models import User, UserSettings
from ...services import audit
from ...services.auth import (
    create_access_token,
    hash_password,
    is_locked,
    issue_refresh_token,
    new_id,
    password_policy_problems,
    register_failed_login,
    revoke_all,
    rotate_refresh_token,
    totp_secret,
    totp_verify,
    verify_password,
)
from ..deps import current_user
from ..schemas import LoginIn, MfaVerifyIn, RefreshIn, RegisterIn, TokenOut

router = APIRouter(prefix="/auth", tags=["auth"])
UTC = UTC


def _limiter(request: Request):
    return request.app.state.limiter


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    request.app.state.limiter.check(request, "register", 5)
    if not body.accept_disclosure:
        raise HTTPException(400, "the risk disclosure must be accepted")
    problems = password_policy_problems(body.password)
    if problems:
        raise HTTPException(400, "; ".join(problems))
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(409, "email already registered")
    s = get_settings()
    user = User(id=new_id(), email=body.email.lower(), password_hash=hash_password(body.password), role="user", disclosure_accepted_at=datetime.now(tz=UTC))
    db.add(user)
    db.flush()
    defaults = RiskLimits.defaults().to_dict()
    db.add(UserSettings(user_id=user.id, timezone=s.default_timezone, account_currency=s.default_account_currency, risk_limits=defaults, notification_prefs={"enabled": True, "quiet_start": load_json_config("risk_defaults.json")["defaults"]["quiet_hours_start_local"], "quiet_end": load_json_config("risk_defaults.json")["defaults"]["quiet_hours_end_local"]}, horizons_enabled={"SCALP": False, "INTRADAY": True, "SWING": True, "WEEKLY": True}))
    db.commit()
    audit.record(db, user.id, "auth.register", user.id, {"email_domain": user.email.split("@")[-1]})
    return TokenOut(access_token=create_access_token(user), refresh_token=issue_refresh_token(db, user), role=user.role, onboarding_completed=user.onboarding_completed)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    request.app.state.limiter.check(request, "login", 10)
    user = db.query(User).filter(User.email == body.email.lower(), User.deleted_at.is_(None)).first()
    if user is None or is_locked(user) or not verify_password(body.password, user.password_hash):
        if user is not None and not is_locked(user):
            register_failed_login(user)
            db.commit()
        audit.record(db, "anonymous", "auth.login_failed", body.email.lower())
        raise HTTPException(401, "invalid credentials or account temporarily locked")
    if user.mfa_enabled:
        if not body.mfa_code or not totp_verify(user.mfa_secret or "", body.mfa_code):
            raise HTTPException(401, "MFA code required or invalid")
    user.failed_logins = 0
    db.commit()
    audit.record(db, user.id, "auth.login", user.id)
    return TokenOut(access_token=create_access_token(user), refresh_token=issue_refresh_token(db, user), role=user.role, onboarding_completed=user.onboarding_completed)


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, request: Request, db: Session = Depends(get_db)):
    request.app.state.limiter.check(request, "refresh", 30)
    res = rotate_refresh_token(db, body.refresh_token)
    if res is None:
        raise HTTPException(401, "refresh token invalid")
    user, raw = res
    return TokenOut(access_token=create_access_token(user), refresh_token=raw, role=user.role, onboarding_completed=user.onboarding_completed)


@router.post("/logout", status_code=204)
def logout(user: User = Depends(current_user), db: Session = Depends(get_db)):
    revoke_all(db, user.id)
    audit.record(db, user.id, "auth.logout", user.id)


@router.post("/mfa/setup")
def mfa_setup(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.mfa_enabled:
        raise HTTPException(400, "MFA already enabled")
    user.mfa_secret = totp_secret()
    db.commit()
    return {"secret": user.mfa_secret, "otpauth": f"otpauth://totp/AurumGuard:{user.email}?secret={user.mfa_secret}&issuer=AurumGuard"}


@router.post("/mfa/enable")
def mfa_enable(body: MfaVerifyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.mfa_secret or not totp_verify(user.mfa_secret, body.code):
        raise HTTPException(400, "invalid code")
    user.mfa_enabled = True
    db.commit()
    audit.record(db, user.id, "auth.mfa_enabled", user.id)
    return {"mfa_enabled": True}


@router.post("/mfa/disable")
def mfa_disable(body: MfaVerifyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.mfa_enabled or not totp_verify(user.mfa_secret or "", body.code):
        raise HTTPException(400, "invalid code")
    user.mfa_enabled = False
    user.mfa_secret = None
    db.commit()
    audit.record(db, user.id, "auth.mfa_disabled", user.id)
    return {"mfa_enabled": False}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "role": user.role, "mfa_enabled": user.mfa_enabled, "onboarding_completed": user.onboarding_completed, "disclosure_accepted_at": user.disclosure_accepted_at}
