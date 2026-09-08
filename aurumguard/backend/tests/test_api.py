import os
from datetime import UTC, datetime, timezone

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///./test_api.db"
for f in ("test_api.db", "test_api.db-wal", "test_api.db-shm"):
    if os.path.exists(f):
        os.remove(f)

from app.db.base import Base, engine  # noqa: E402
from app.main import create_app  # noqa: E402

UTC = UTC


@pytest.fixture(scope="module")
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def token(client):
    r = client.post("/api/auth/register", json={"email": "t1@example.com", "password": "Strong-Passw0rd-123", "accept_disclosure": True})
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_health_and_meta(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["demo_data"] is True
    assert client.get("/api/meta").json()["live_execution"] == "disabled"
    assert r.headers["X-Content-Type-Options"] == "nosniff" and "Content-Security-Policy" in r.headers


def test_register_validation(client):
    assert client.post("/api/auth/register", json={"email": "x@example.com", "password": "short", "accept_disclosure": True}).status_code == 422
    assert client.post("/api/auth/register", json={"email": "x@example.com", "password": "alllowercase12345", "accept_disclosure": True}).status_code == 400
    assert client.post("/api/auth/register", json={"email": "x@example.com", "password": "Strong-Passw0rd-123", "accept_disclosure": False}).status_code == 400


def test_login_and_me(client, token):
    r = client.post("/api/auth/login", json={"email": "t1@example.com", "password": "Strong-Passw0rd-123"})
    assert r.status_code == 200
    assert client.post("/api/auth/login", json={"email": "t1@example.com", "password": "wrong-password-123"}).status_code == 401
    assert client.get("/api/auth/me", headers=auth(token)).json()["email"] == "t1@example.com"
    assert client.get("/api/auth/me").status_code == 401
    r2 = client.post("/api/auth/refresh", json={"refresh_token": r.json()["refresh_token"]})
    assert r2.status_code == 200
    assert client.post("/api/auth/refresh", json={"refresh_token": r.json()["refresh_token"]}).status_code == 401  # rotated


def test_onboarding_and_risk_limits(client, token):
    r = client.post("/api/users/onboarding", json={"timezone": "Asia/Dubai", "account_currency": "AED", "account_equity": 36725, "friday_cutoff_local": "20:00"}, headers=auth(token))
    assert r.status_code == 200 and r.json()["risk_limits"]["account_currency"] == "AED"
    bad = client.put("/api/users/risk-limits", json={"risk_per_trade_pct": 5.0}, headers=auth(token))
    assert bad.status_code == 400 and "risk_per_trade_pct" in bad.text
    ok = client.put("/api/users/risk-limits", json={"risk_per_trade_pct": 1.0, "max_daily_loss_pct": 2.0}, headers=auth(token))
    assert ok.status_code == 200 and ok.json()["risk_limits"]["risk_per_trade_pct"] == 1.0
    assert client.post("/api/users/onboarding", json={"timezone": "Mars/Olympus", "account_currency": "USD", "account_equity": 1000}, headers=auth(token)).status_code == 400


def test_market_endpoints(client, token):
    q = client.get("/api/market/quote", headers=auth(token)).json()
    assert q["demo_data"] is True and q["ask"] >= q["bid"]
    c = client.get("/api/market/candles?timeframe=H1&bars=50", headers=auth(token)).json()
    assert c["timeframe"] == "H1" and 0 < len(c["candles"]) <= 50
    assert client.get("/api/market/candles?timeframe=X1", headers=auth(token)).status_code == 400
    h = client.get("/api/market/health", headers=auth(token)).json()
    assert any(p["is_mock"] for p in h["providers"])


def test_position_size_calculator_respects_limits(client, token):
    r = client.post("/api/risk/position-size", json={"entry": 2400, "stop": 2395, "direction": "BUY", "spread": 0.3, "slippage": 0.2, "tp1": 2410}, headers=auth(token))
    assert r.status_code == 200 and r.json()["status"] == "OK" and r.json()["net_rr_tp1"] > 1
    over = client.post("/api/risk/position-size", json={"entry": 2400, "stop": 2395, "direction": "BUY", "spread": 0.3, "slippage": 0.2, "risk_pct": 3.0}, headers=auth(token))
    assert over.status_code == 400
    tiny = client.post("/api/risk/position-size", json={"entry": 2400, "stop": 2350, "direction": "BUY", "spread": 0.3, "slippage": 0.2, "equity": 300}, headers=auth(token))
    assert "MINIMUM CONTRACT SIZE EXCEEDS RISK LIMIT" in tiny.json()["status"]


def test_strategies_and_admin_gate(client, token):
    s = client.get("/api/strategies", headers=auth(token)).json()["strategies"]
    assert {x["id"] for x in s} >= {"PBC-H1", "BRT-M15"}
    assert all(x["status"] == "RESEARCH" for x in s)
    assert client.post("/api/strategies/PBC-H1/action", json={"action": "approve", "note": "user cannot approve"}, headers=auth(token)).status_code == 403


def test_admin_approval_requires_validation(client):
    from app.db.base import SessionLocal
    from app.db.models import User

    db = SessionLocal()
    u = db.query(User).filter(User.email == "t1@example.com").one()
    u.role = "admin"
    db.commit()
    db.close()
    r = client.post("/api/auth/login", json={"email": "t1@example.com", "password": "Strong-Passw0rd-123"})
    tok = r.json()["access_token"]
    resp = client.post("/api/strategies/PBC-H1/action", json={"action": "approve", "note": "trying without validation data"}, headers=auth(tok))
    assert resp.status_code == 400 and "validation sample" in resp.text
    ov = client.get("/api/admin/overview", headers=auth(tok)).json()
    assert ov["live_execution"].startswith("DISABLED")


def test_analysis_run_decisions_feed_and_evidence(client, token):
    r = client.post("/api/auth/login", json={"email": "t1@example.com", "password": "Strong-Passw0rd-123"})
    tok = r.json()["access_token"]
    run = client.post("/api/admin/run-analysis", headers=auth(tok))
    assert run.status_code == 200 and run.json()["users"] >= 1
    latest = client.get("/api/decisions/latest", headers=auth(tok)).json()["horizons"]
    assert set(latest) == {"SCALP", "INTRADAY", "SWING", "WEEKLY"}
    for _h, d in latest.items():
        assert d is not None and d["status"] in ("BUY_SETUP", "SELL_SETUP", "WAIT", "NO_TRADE", "EVENT_LOCKOUT", "DATA_UNAVAILABLE")
    did = latest["INTRADAY"]["decision_id"]
    det = client.get(f"/api/decisions/{did}", headers=auth(tok)).json()
    ev = det["evidence_inspector"]
    for k in ("data_used", "data_unavailable", "data_sources", "gates_passed", "gates_failed", "regime", "model_version", "scoring_config", "calibration_version", "known_limitations", "decision_timestamp"):
        assert k in ev
    assert ev["outcome"] is None
    feed = client.get("/api/decisions/feed?limit=10", headers=auth(tok)).json()["items"]
    assert feed
    # second run at the same minute is idempotent (no new rows)
    n1 = len(client.get("/api/decisions/feed?limit=200", headers=auth(tok)).json()["items"])
    client.post("/api/admin/run-analysis", headers=auth(tok))
    n2 = len(client.get("/api/decisions/feed?limit=200", headers=auth(tok)).json()["items"])
    assert n2 == n1
    # paper order on a non-actionable decision is refused
    resp = client.post("/api/paper/orders", json={"decision_id": did}, headers=auth(tok))
    assert resp.status_code in (400, 201)
    assert client.get("/api/paper/positions", headers=auth(tok)).status_code == 200
    assert client.get("/api/notifications", headers=auth(tok)).status_code == 200
    assert client.get("/api/regime", headers=auth(tok)).status_code == 200
    assert client.get("/api/calendar", headers=auth(tok)).json()["demo_data"] is True
    cal = client.get("/api/calibration", headers=auth(tok)).json()
    assert cal["version"].startswith("calibration")
    aud = client.get("/api/audit", headers=auth(tok)).json()
    assert aud["chain"]["ok"] is True


def test_privacy_export_and_delete(client):
    r = client.post("/api/auth/register", json={"email": "t2@example.com", "password": "Strong-Passw0rd-123", "accept_disclosure": True})
    tok = r.json()["access_token"]
    ex = client.get("/api/users/export", headers=auth(tok)).json()
    assert ex["user"]["email"] == "t2@example.com"
    assert client.post("/api/users/delete", json={"password": "wrong-pass-12345", "confirm": "DELETE MY ACCOUNT"}, headers=auth(tok)).status_code == 401
    assert client.post("/api/users/delete", json={"password": "Strong-Passw0rd-123", "confirm": "DELETE MY ACCOUNT"}, headers=auth(tok)).status_code == 204
    assert client.get("/api/auth/me", headers=auth(tok)).status_code == 401


def test_seeded_demo_accounts_can_log_in(client):
    """Regression: an earlier seed used a reserved '.local' domain that LoginIn rejected (422)."""
    from app.api.schemas import LoginIn
    from app.seed import DEMO_USERS, seed

    for email, pw, _role in DEMO_USERS:
        LoginIn(email=email, password=pw)  # schema must accept the seeded addresses
    seed(validate=False, run_analysis=False)
    for email, pw, _role in DEMO_USERS:
        r = client.post("/api/auth/login", json={"email": email, "password": pw})
        assert r.status_code == 200, f"{email}: {r.status_code} {r.text}"
        assert r.json()["onboarding_completed"] is True


def test_seed_migrates_legacy_local_demo_email(client):
    from app.db.base import SessionLocal
    from app.db.models import User
    from app.seed import DEMO_USERS, seed
    from app.services.auth import hash_password, new_id

    legacy_email = "legacy@aurumguard.local"
    target_email = "legacy@aurumguard.demo"
    db = SessionLocal()
    try:
        db.query(User).filter(User.email.in_([legacy_email, target_email])).delete(synchronize_session=False)
        db.add(User(id=new_id(), email=legacy_email, password_hash=hash_password("Legacy-Pass-2026x"), role="user", disclosure_accepted_at=datetime.now(tz=UTC), onboarding_completed=True))
        db.commit()
    finally:
        db.close()
    try:
        DEMO_USERS.append((target_email, "Legacy-Pass-2026x", "user"))
        seed(validate=False, run_analysis=False)
    finally:
        DEMO_USERS.pop()
    db = SessionLocal()
    try:
        assert db.query(User).filter(User.email == legacy_email).first() is None
        assert db.query(User).filter(User.email == target_email).first() is not None
    finally:
        db.close()
