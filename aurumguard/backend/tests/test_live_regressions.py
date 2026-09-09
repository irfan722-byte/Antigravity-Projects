"""Regressions from the first live-price session on real Twelve Data.

Both failures below were invisible to the existing suite because they only appear when the
evaluation timestamp and the fetch are separated in time, or when a metric is undefined.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta

import pytest

from app.backtest.metrics import TradeRecord, compute_metrics
from app.core.candles import Quote
from app.core.integrity import DataStatus, validate_quote
from app.main import SafeJSONResponse, _json_safe


def _trade(pnl: float, r: float, ts: datetime, i: int = 0) -> TradeRecord:
    return TradeRecord(
        trade_id=f"t{i}", strategy_id="X", strategy_version="1.0.0", horizon="INTRADAY", direction="BUY",
        entry_ts=ts + timedelta(hours=i), exit_ts=ts + timedelta(hours=i + 1), entry_price=2400.0,
        exit_price=2400.0 + pnl, lots=0.1, risk_usd=100.0, pnl_usd=pnl, pnl_gross_usd=pnl + 2.0,
        costs_usd=2.0, exit_reason="tp", session="LONDON", regime="STRONG_TREND", score=70.0, near_event=False,
    )


def _finite(value) -> bool:
    """No number anywhere in the payload may be non-finite: json.dumps refuses those."""
    if isinstance(value, dict):
        return all(_finite(v) for v in value.values())
    if isinstance(value, list):
        return all(_finite(v) for v in value)
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def test_profit_factor_is_undefined_not_infinite_without_losses():
    """A breakdown bucket whose trades all won stored inf, which is not valid JSON.

    The whole-run metrics were already guarded; the per-session, per-regime and long/short
    breakdowns were not, and those are what the strategy card and backtest detail return. One
    such bucket made GET /api/strategies and GET /api/backtests/{id} fail with a 500.
    """
    ts = datetime(2026, 3, 10, tzinfo=UTC)
    winners_only = [_trade(100.0, 1.0, ts, 0), _trade(50.0, 0.5, ts, 1)]
    m = compute_metrics(winners_only, 10000.0, 30.0, "OOS")
    assert m["profit_factor"] is None
    assert m["long"]["profit_factor"] is None  # the bucket that used to be inf
    assert _finite(m), "a non-finite number anywhere in the payload breaks the response"
    assert json.dumps(m, allow_nan=False, default=str)  # what starlette does to a response

    mixed = winners_only + [_trade(-40.0, -0.4, ts, 2)]
    assert compute_metrics(mixed, 10000.0, 30.0, "OOS")["profit_factor"] == pytest.approx(3.75)


def test_a_quote_fetched_after_the_evaluation_started_is_not_in_the_future():
    """build_snapshot takes `now`, then fetches; validating against `now` flagged QUOTE_FUTURE_TS."""
    started = datetime.now(tz=UTC)
    fetched = started + timedelta(seconds=9)  # slow call, longer than the 5 s tolerance
    q = Quote("XAUUSD", 4400.0, 4400.3, fetched, "twelvedata", fetched)
    assert "QUOTE_FUTURE_TS" in validate_quote(q, started).codes()  # the old comparison
    at_use = max(started, fetched)
    rep = validate_quote(q, at_use)
    assert rep.codes() == [] and rep.status == DataStatus.VALID
    assert rep.freshness_seconds == pytest.approx(0.0, abs=0.5)


def test_a_genuinely_future_stamped_quote_is_still_rejected():
    now = datetime.now(tz=UTC)
    q = Quote("XAUUSD", 4400.0, 4400.3, now + timedelta(minutes=5), "twelvedata", now)
    assert "QUOTE_FUTURE_TS" in validate_quote(q, max(now, datetime.now(tz=UTC))).codes()


def test_responses_render_a_non_finite_number_as_null():
    """Rows written by an older build still hold inf; a response must not fail because of one."""
    with pytest.raises(ValueError):
        json.dumps({"profit_factor": float("inf")}, allow_nan=False)  # what starlette's default did

    payload = {"buckets": [{"profit_factor": float("inf")}, {"profit_factor": 1.5}], "brier": float("nan"), "id": "a1"}
    assert _json_safe(payload) == {"buckets": [{"profit_factor": None}, {"profit_factor": 1.5}], "brier": None, "id": "a1"}
    body = SafeJSONResponse(payload).render(payload)
    assert b'"profit_factor":null' in body.replace(b", ", b",") and json.loads(body)["buckets"][1]["profit_factor"] == 1.5


def test_minute_candles_are_fetched_only_when_something_can_move():
    """An idle account fetched M1 every run: ~288 credits a day that the budget never counted."""
    from app.core.contract_spec import MOCK_SPEC
    from app.paper.engine import OrderStatus, PaperEngine
    from app.services.analysis import needs_m1

    eng = PaperEngine(MOCK_SPEC, 10000.0)
    assert needs_m1(eng, []) is False  # nothing open, nothing resting, nothing to score
    assert needs_m1(eng, [object()]) is True  # an expired setup still needs its outcome

    order = next(iter(eng.orders.values()), None)
    assert order is None
    eng.orders["o1"] = type("O", (), {"status": OrderStatus.PENDING})()
    assert needs_m1(eng, []) is True  # a resting order can fill on a minute bar
    eng.orders["o1"].status = OrderStatus.CANCELLED
    assert needs_m1(eng, []) is False
