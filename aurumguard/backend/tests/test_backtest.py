from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.backtest.engine import BacktestConfig, Backtester
from app.backtest.metrics import TradeRecord, compute_metrics
from app.backtest.validation import monte_carlo, oos_calibration_payload, threshold_sensitivity, walk_forward_splits
from app.config import Settings
from app.core.contract_spec import MOCK_SPEC
from app.core.strategies import build_strategies
from app.providers.registry import build_providers

UTC = UTC


@pytest.fixture(scope="module")
def bt():
    ps = build_providers(Settings())
    return Backtester(ps.market, ps.calendar, MOCK_SPEC)


def test_backtest_runs_and_is_reproducible(bt):
    s = build_strategies()["PBC-H1"]
    cfg = BacktestConfig("PBC-H1", datetime(2025, 9, 1, tzinfo=UTC), datetime(2025, 10, 15, tzinfo=UTC), label="TEST", data_label="DEMO")
    r1 = bt.run(s, cfg)
    r2 = bt.run(s, cfg)
    assert r1.trades_hash == r2.trades_hash and r1.config_hash == r2.config_hash
    assert r1.evaluations > 100
    assert any("Demo" in w or "DEMO" in w for w in r1.warnings)
    for t in r1.trades:
        assert t.entry_ts < t.exit_ts
        assert t.risk_usd > 0
        # no fill can happen before the decision bar closed (entry is the next M1 open)
        assert t.entry_ts.minute in range(60)
    if r1.trades:
        m = r1.metrics
        assert m["trades"] == len(r1.trades)
        assert "expectancy_r" in m and "max_drawdown_usd" in m and "by_session" in m
        assert m["costs_usd"] >= 0


def test_breakout_backtest_and_threshold_slicing(bt):
    s = build_strategies()["BRT-M15"]
    cfg = BacktestConfig("BRT-M15", datetime(2025, 10, 1, tzinfo=UTC), datetime(2025, 11, 1, tzinfo=UTC), label="TEST", data_label="DEMO")
    r = bt.run(s, cfg)
    rows = threshold_sensitivity(r, 10000, 31)
    assert rows[0]["threshold"] == 0 and rows[0]["trades"] == len(r.trades)
    assert all(rows[i]["trades"] >= rows[i + 1]["trades"] for i in range(len(rows) - 1))


def test_metrics_and_monte_carlo_on_synthetic_trades():
    t0 = datetime(2026, 1, 5, tzinfo=UTC)
    trades = []
    for i in range(40):
        win = i % 3 != 0
        pnl = 80.0 if win else -50.0
        trades.append(TradeRecord(f"t{i}", "S", "1", "INTRADAY", "BUY" if i % 2 else "SELL", t0 + timedelta(days=i), t0 + timedelta(days=i, hours=3), 2400, 2405, 0.1, 50.0, pnl, pnl + 3, 3.0, "tp2" if win else "stop", "LONDON", "STRONG_TREND", 60 + (i % 4) * 5, i % 7 == 0))
    m = compute_metrics(trades, 10000, 40, "UNIT")
    assert m["trades"] == 40 and abs(m["win_rate"] - 26 / 40) < 1e-9
    assert m["profit_factor"] > 1 and m["expectancy_r"] > 0
    assert m["max_consecutive_losses"] >= 1 and m["by_year"]["2026"]["trades"] == 40
    assert m["calibration_buckets"]["60-70"]["n"] > 0
    mc = monte_carlo(trades, 10000)
    assert mc["max_drawdown_p95"] >= mc["max_drawdown_p50"] >= 0
    pay = oos_calibration_payload(trades, "OOS", "DEMO")
    assert pay["sample_size"] == 40 and pay["wins"] == 26 and "60-70" in pay["buckets"]


def test_walk_forward_has_embargo():
    s = walk_forward_splits(datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 12, 31, tzinfo=UTC), 90, 30, 3)
    assert s and all((x.test_start - x.train_end).days == 3 for x in s)
    assert all(x.test_start >= x.train_end for x in s)
