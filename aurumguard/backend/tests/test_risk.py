from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.core.contract_spec import MOCK_SPEC, ContractSpec
from app.core.risk import AccountState, CostModel, OpenRisk, RiskLimits, SizeStatus, compute_position_size, floor_to_step, net_reward_to_risk, risk_checks, to_usd

UTC = UTC
NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


def test_defaults_valid_and_bounds_enforced():
    lim = RiskLimits.defaults()
    assert lim.validate() == []
    bad = RiskLimits(**(lim.to_dict() | {"risk_per_trade_pct": 5.0}))
    assert any("risk_per_trade_pct" in p for p in bad.validate())


def test_position_size_floors_never_rounds_up():
    costs = CostModel(spread=0.3, slippage_entry=0.1, slippage_exit=0.1)
    r = compute_position_size(10000, 0.5, 2400.0, 2395.0, "BUY", costs, MOCK_SPEC)
    assert r.status == SizeStatus.OK
    # budget 50; eff = 5 + 0.3 + 0.2 = 5.5 -> risk/lot 550 -> raw 0.0909 -> floor 0.09
    assert r.lots == 0.09
    assert r.risk_usd == pytest.approx(49.5)
    assert r.effective_adverse_distance == pytest.approx(5.5)
    assert r.risk_usd <= r.risk_budget_usd


def test_min_contract_exceeds_risk_skip():
    costs = CostModel(spread=0.3, slippage_entry=0.1, slippage_exit=0.1)
    r = compute_position_size(500, 0.5, 2400.0, 2390.0, "BUY", costs, MOCK_SPEC)
    assert r.status == SizeStatus.SKIP_MIN_CONTRACT
    assert r.lots == 0.0
    assert "MINIMUM CONTRACT SIZE EXCEEDS RISK LIMIT" in r.status.value


def test_invalid_stop_side():
    costs = CostModel(0.3, 0.1, 0.1)
    assert compute_position_size(10000, 0.5, 2400.0, 2405.0, "BUY", costs, MOCK_SPEC).status == SizeStatus.INVALID
    assert compute_position_size(10000, 0.5, 2400.0, 2395.0, "SELL", costs, MOCK_SPEC).status == SizeStatus.INVALID


def test_incorrect_contract_spec_changes_size():
    costs = CostModel(0.3, 0.1, 0.1)
    other = ContractSpec("x", "x", "XAUUSD", 10.0, 0.1, 0.1, 100, 0.01, "USD", 0.0, None, None, False, "n/a")
    a = compute_position_size(10000, 0.5, 2400.0, 2395.0, "BUY", costs, MOCK_SPEC)
    b = compute_position_size(10000, 0.5, 2400.0, 2395.0, "BUY", costs, other)
    assert b.lots != a.lots and b.risk_usd <= b.risk_budget_usd


def test_net_rr_includes_costs():
    costs = CostModel(0.3, 0.1, 0.1)
    rr = net_reward_to_risk(2400.0, 2395.0, 2410.0, "BUY", costs, MOCK_SPEC)
    # reward (10-0.5)=9.5 ; risk (5+0.5)=5.5
    assert rr == pytest.approx(9.5 / 5.5)
    assert net_reward_to_risk(2400.0, 2395.0, 2399.0, "BUY", costs, MOCK_SPEC) is None
    with_comm = CostModel(0.3, 0.1, 0.1, commission_per_lot_usd=7.0)
    assert net_reward_to_risk(2400.0, 2395.0, 2410.0, "BUY", with_comm, MOCK_SPEC) < rr


def test_risk_checks_limits():
    lim = RiskLimits.defaults()
    acct = AccountState(10000, 0.0, 0.0, 10000)
    ok = risk_checks(lim, acct, 50.0, NOW)
    assert all(v[0] for v in ok.values())
    daily = AccountState(10000, -160.0, -160.0, 10000)
    assert not risk_checks(lim, daily, 50.0, NOW)["G10"][0]
    weekly = AccountState(10000, 0.0, -310.0, 10000)
    assert not risk_checks(lim, weekly, 50.0, NOW)["G11"][0]
    agg = AccountState(10000, 0.0, 0.0, 10000, open_risks=[OpenRisk("p1", "s", "INTRADAY", "BUY", 120.0)])
    assert not risk_checks(lim, agg, 50.0, NOW)["G12"][0]
    conc = AccountState(10000, 0.0, 0.0, 10000, open_risks=[OpenRisk("p1", "s", "I", "BUY", 10.0), OpenRisk("p2", "s", "I", "BUY", 10.0)])
    assert not risk_checks(lim, conc, 50.0, NOW)["G09"][0]
    streak = AccountState(10000, 0.0, 0.0, 10000, consecutive_losses=3)
    assert not risk_checks(lim, streak, 50.0, NOW)["G09"][0]
    over = risk_checks(lim, acct, 80.0, NOW)
    assert not over["G09"][0]
    dd = AccountState(9300, 0.0, 0.0, 10000)
    assert not risk_checks(lim, dd, 10.0, NOW)["G12"][0]
    locked = AccountState(10000, 0.0, 0.0, 10000, manual_lock_until=NOW + timedelta(hours=1))
    assert not risk_checks(lim, locked, 10.0, NOW)["G09"][0]


def test_currency_conversion_and_floor():
    assert to_usd(3672.5, "AED", 3.6725) == pytest.approx(1000.0)
    assert floor_to_step(0.0999, 0.01) == 0.09
    assert floor_to_step(0.10, 0.01) == 0.10
