"""Stored timestamps stay UTC-aware on SQLite.

SQLite has no timestamp type: it stores what SQLAlchemy writes and returns a naive
datetime, so ``DateTime(timezone=True)`` silently loses the offset. FastAPI then
serialises "2026-09-09T08:21:00" with no zone, the browser reads it as local time,
and every timestamp in the UI is wrong by the viewer's UTC offset (4 hours in
Asia/Dubai). UtcDateTime normalises both directions.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import DecisionRecord, User


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_decision_timestamps_come_back_utc_aware():
    db = _session()
    as_of = datetime(2026, 9, 9, 8, 21, 3, tzinfo=UTC)
    db.add(User(id="u1", email="a@b.demo", password_hash="x", role="user"))
    db.add(DecisionRecord(id="d1", user_id="u1", horizon="INTRADAY", status="DATA_UNAVAILABLE", as_of=as_of, reason="r"))
    db.commit()
    db.expunge_all()

    row = db.query(DecisionRecord).one()
    assert row.as_of.tzinfo is not None, "naive datetime would serialise without an offset"
    assert row.as_of == as_of
    assert row.as_of.isoformat().endswith("+00:00")


def test_non_utc_input_is_normalised_not_truncated():
    db = _session()
    dubai = timezone(timedelta(hours=4))
    local = datetime(2026, 9, 9, 12, 21, 3, tzinfo=dubai)  # same instant as 08:21:03Z
    db.add(User(id="u1", email="a@b.demo", password_hash="x", role="user"))
    db.add(DecisionRecord(id="d1", user_id="u1", horizon="SCALP", status="WAIT", as_of=local, reason="r"))
    db.commit()
    db.expunge_all()

    row = db.query(DecisionRecord).one()
    assert row.as_of == local
    assert row.as_of.hour == 8 and row.as_of.tzinfo is UTC


def test_null_timestamps_stay_null():
    db = _session()
    db.add(User(id="u1", email="a@b.demo", password_hash="x", role="user", disclosure_accepted_at=None))
    db.commit()
    db.expunge_all()
    assert db.query(User).one().disclosure_accepted_at is None
