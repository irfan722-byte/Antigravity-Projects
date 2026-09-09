"""Authentication: Argon2 password hashing, short-lived JWT access tokens, rotating
refresh tokens stored hashed, optional TOTP MFA, login lockout."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.models import RefreshToken, User

_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
UTC = UTC
MAX_FAILED = 8
LOCK_MINUTES = 15


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, h: str) -> bool:
    try:
        return _ph.verify(h, pw)
    except VerifyMismatchError:
        return False


def password_policy_problems(pw: str) -> list[str]:
    p = []
    if len(pw) < 12:
        p.append("password must be at least 12 characters")
    if pw.lower() == pw or pw.upper() == pw:
        p.append("password must mix upper and lower case")
    if not any(ch.isdigit() for ch in pw):
        p.append("password must include a digit")
    return p


def new_id() -> str:
    return uuid.uuid4().hex[:24]


def create_access_token(user: User) -> str:
    s = get_settings()
    now = datetime.now(tz=UTC)
    payload = {"sub": user.id, "role": user.role, "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=s.access_token_minutes)).timestamp()), "typ": "access"}
    return jwt.encode(payload, s.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    s = get_settings()
    return jwt.decode(token, s.secret_key, algorithms=["HS256"], options={"require": ["exp", "sub"]})


def issue_refresh_token(db: Session, user: User) -> str:
    s = get_settings()
    raw = secrets.token_urlsafe(48)
    rec = RefreshToken(id=new_id(), user_id=user.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(), expires_at=datetime.now(tz=UTC) + timedelta(days=s.refresh_token_days))
    db.add(rec)
    db.commit()
    return raw


def rotate_refresh_token(db: Session, raw: str) -> tuple[User, str] | None:
    h = hashlib.sha256(raw.encode()).hexdigest()
    rec = db.query(RefreshToken).filter(RefreshToken.token_hash == h).one_or_none()
    now = datetime.now(tz=UTC)
    if rec is None or rec.revoked_at is not None or rec.expires_at.replace(tzinfo=UTC) < now:
        return None
    rec.revoked_at = now
    user = db.get(User, rec.user_id)
    if user is None or user.deleted_at is not None:
        return None
    new_raw = issue_refresh_token(db, user)
    return user, new_raw


def revoke_all(db: Session, user_id: str) -> None:
    now = datetime.now(tz=UTC)
    for rec in db.query(RefreshToken).filter(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)).all():
        rec.revoked_at = now
    db.commit()


# ---- TOTP (RFC 6238) without extra dependencies ----

def totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_code(secret: str, for_time: float | None = None, step: int = 30, digits: int = 6) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    counter = int((for_time or time.time()) // step)
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    off = h[-1] & 0x0F
    code = (struct.unpack(">I", h[off : off + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(code).zfill(digits)


def totp_verify(secret: str, code: str, window: int = 1) -> bool:
    now = time.time()
    return any(hmac.compare_digest(totp_code(secret, now + i * 30), code) for i in range(-window, window + 1))


def register_failed_login(user: User) -> None:
    user.failed_logins += 1
    if user.failed_logins >= MAX_FAILED:
        user.locked_until = datetime.now(tz=UTC) + timedelta(minutes=LOCK_MINUTES)
        user.failed_logins = 0


def is_locked(user: User) -> bool:
    return bool(user.locked_until and user.locked_until.replace(tzinfo=UTC) > datetime.now(tz=UTC))
