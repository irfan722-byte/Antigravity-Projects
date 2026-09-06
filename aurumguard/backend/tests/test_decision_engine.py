from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.core.candles import Timeframe
from app.core.contract_spec import MOCK_SPEC
from app.core.decision import DecisionEngine, StrategyRuntimeState, UserContext, estimate_slippage
from app.core.integrity import DataStatus
from app.core.risk import AccountState, RiskLimits
from app.core.setup import DecisionStatus, Horizon
from app.core.strategies import build_strategies
from app.providers.registry import build_providers
from app.services.snapshot import build_snapshot

UTC = UTC


@pytest.fixture(scope="module")
def providers():
    return build_providers(Settings())


@pytest.fixture(scope="module")
def strategies():
    return build_strategies()


def user(equity=10000.0):
    return UserContext("u1", "Asia/Dubai", RiskLimits.defaults(), AccountState(equity, 0, 0, equity), MOCK_SPEC)


def by_horizon(strats):
    out = {}
    for s in strats.values():
        out.setdefault(Horizon(s.definition.horizon), []).append(s)
    return out


def approved_states(strats, n=60, wins=33):
    return {sid: StrategyRuntimeState("APPROVED", {"sample_size": n, "wins": wins, "expectancy_r": 0.25, "label": "OOS", "data_label": "DEMO"}, production_threshold=60.0, approval_note="demo seed approval") for sid in strats}


def test_snapshot_builds_and_is_point_in_time(providers):
    now = datetime(2026, 3, 10, 14, 0, tzinfo=UTC)
    snap = build_snapshot(providers, now, "Asia/Dubai")
    assert snap.demo_data is True
    assert snap.quote is not None and snap.quote_report.status != DataStatus.INVALID
    for tf, cs in snap.candles.items():
        assert all(c.end_ts <= now for c in cs), tf
        assert snap.candle_reports[tf].status != DataStatus.INVALID, (tf, snap.candle_reports[tf].codes())
    assert snap.session_label == "LONDON_NY_OVERLAP"
    assert snap.intermarket is not None and len(snap.intermarket.gold) > 60
    assert snap.data_sources["market_data"] == "mock"


def test_all_horizons_produce_exactly_one_status(providers, strategies):
    now = datetime(2026, 3, 10, 14, 0, tzinfo=UTC)
    snap = build_snapshot(providers, now, "Asia/Dubai")
    eng = DecisionEngine()
    decisions = eng.evaluate_all(snap, user(), by_horizon(strategies), approved_states(strategies))
    assert set(decisions) == set(Horizon)
    for _h, d in decisions.items():
        assert d.status in DecisionStatus
        assert d.reason
        insp = d.evidence_inspector
        for key in ("data_used", "data_unavailable", "data_sources", "timestamps", "model_version", "scoring_config", "calibration_version", "known_limitations", "decision_timestamp"):
            assert key in insp
        assert insp["outcome"] is None
        if d.setup:
            s = d.setup.to_dict()
            for k in ("bid", "ask", "spread", "stop_loss", "targets", "expiry", "position_size", "confidence_low", "confidence_high", "historical_sample_size", "uncertainty_statement", "decision_reason"):
                assert k in s
            assert len(s["targets"]) >= 2
    assert decisions[Horizon.SCALP].status == DecisionStatus.NO_TRADE
    assert "scalping" in decisions[Horizon.SCALP].reason.lower() or "no strategy" in decisions[Horizon.SCALP].reason.lower()


def test_no_approved_strategy_means_no_trade(providers, strategies):
    now = datetime(2026, 3, 10, 14, 0, tzinfo=UTC)
    snap = build_snapshot(providers, now, "Asia/Dubai")
    d = DecisionEngine().evaluate_horizon(snap, user(), Horizon.INTRADAY, by_horizon(strategies)[Horizon.INTRADAY], {})
    assert d.status == DecisionStatus.NO_TRADE and "APPROVED" in d.reason


def test_weekend_and_stale_data_paths(providers, strategies):
    sat = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    snap = build_snapshot(providers, sat, "Asia/Dubai")
    d = DecisionEngine().evaluate_horizon(snap, user(), Horizon.INTRADAY, by_horizon(strategies)[Horizon.INTRADAY], approved_states(strategies))
    # Saturday: the last candles are Friday's; stale check is suppressed when market closed, so we get NO_TRADE (closed)
    assert d.status in (DecisionStatus.NO_TRADE, DecisionStatus.DATA_UNAVAILABLE)
    # inject provider failure -> quote missing -> DATA_UNAVAILABLE
    now = datetime(2026, 3, 10, 14, 0, tzinfo=UTC)
    providers.market.fail_next = True
    snap2 = build_snapshot(providers, now, "Asia/Dubai")
    d2 = DecisionEngine().evaluate_horizon(snap2, user(), Horizon.INTRADAY, by_horizon(strategies)[Horizon.INTRADAY], approved_states(strategies))
    assert d2.status == DecisionStatus.DATA_UNAVAILABLE


def test_event_lockout_path(providers, strategies):
    # NFP mock on first Friday of March 2026 = 2026-03-06 13:30 UTC; 10 minutes before => lockout
    now = datetime(2026, 3, 6, 13, 20, tzinfo=UTC)
    snap = build_snapshot(providers, now, "Asia/Dubai")
    d = DecisionEngine().evaluate_horizon(snap, user(), Horizon.INTRADAY, by_horizon(strategies)[Horizon.INTRADAY], approved_states(strategies))
    assert d.status == DecisionStatus.EVENT_LOCKOUT
    assert "Nonfarm" in d.reason


def test_risk_lock_blocks_setups_across_days(providers, strategies):
    """Scan several days; whenever a setup would be produced, a daily-loss-locked account must not get one."""
    eng = DecisionEngine()
    found_setup = False
    for day in range(2, 20):
        for hour in (9, 11, 14, 16):
            now = datetime(2026, 3, day, hour, 0, tzinfo=UTC)
            if now.weekday() >= 5:
                continue
            snap = build_snapshot(providers, now, "Asia/Dubai")
            d = eng.evaluate_horizon(snap, user(), Horizon.INTRADAY, by_horizon(strategies)[Horizon.INTRADAY], approved_states(strategies))
            if d.status in (DecisionStatus.BUY_SETUP, DecisionStatus.SELL_SETUP):
                found_setup = True
                locked = UserContext("u1", "Asia/Dubai", RiskLimits.defaults(), AccountState(10000, -200, -200, 10000), MOCK_SPEC)
                d2 = eng.evaluate_horizon(snap, locked, Horizon.INTRADAY, by_horizon(strategies)[Horizon.INTRADAY], approved_states(strategies))
                assert d2.status == DecisionStatus.NO_TRADE and "G10" in d2.reason
                # setup content checks
                s = d.setup
                assert s.total_account_risk_pct <= RiskLimits.defaults().risk_per_trade_pct + 1e-6
                assert s.targets[0].net_reward_to_risk >= 1.5
                assert (s.direction == "BUY" and s.stop_loss < s.entry_reference < s.targets[0].price < s.targets[1].price) or (s.direction == "SELL" and s.stop_loss > s.entry_reference > s.targets[0].price > s.targets[1].price)
                assert s.confidence_low < s.confidence_high and s.historical_sample_size == 60
                assert "uncertain" in s.uncertainty_statement
                return
    # Synthetic data may not produce a confirmed setup in this window; that is acceptable but recorded.
    pytest.skip("no confirmed setup in scanned demo window (NO_TRADE bias is acceptable)") if not found_setup else None


def test_slippage_model_monotonic():
    assert estimate_slippage(0.3, "OFF_HOURS", "NORMAL") > estimate_slippage(0.3, "LONDON", "NORMAL")
    assert estimate_slippage(0.6, "LONDON", "NORMAL") > estimate_slippage(0.3, "LONDON", "NORMAL")
    assert estimate_slippage(0.3, "LONDON", "EXPANSION") > estimate_slippage(0.3, "LONDON", "NORMAL")
