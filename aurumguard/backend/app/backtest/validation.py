"""Validation pipeline: walk-forward, parameter stability, Monte Carlo, cost and
threshold sensitivity, benchmark comparison and a multiple-testing note.

Nothing here promotes a strategy. It produces a report for a human reviewer
and the numbers the calibration module needs (OOS buckets, Brier)."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

import numpy as np

from ..core.calibration import bucket_for
from ..core.strategies.base import Strategy
from .engine import BacktestConfig, Backtester, BacktestResult
from .metrics import TradeRecord, compute_metrics


@dataclass
class WalkForwardSplit:
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime


def walk_forward_splits(start: datetime, end: datetime, train_days: int, test_days: int, embargo_days: int = 2) -> list[WalkForwardSplit]:
    """Rolling splits with an embargo gap so trades opened in training cannot leak into the test window."""
    out = []
    t = start
    while t + timedelta(days=train_days + embargo_days + test_days) <= end:
        tr_end = t + timedelta(days=train_days)
        te_start = tr_end + timedelta(days=embargo_days)
        te_end = te_start + timedelta(days=test_days)
        out.append(WalkForwardSplit(t, tr_end, te_start, te_end))
        t = t + timedelta(days=test_days)
    return out


def monte_carlo(trades: list[TradeRecord], starting_equity: float, runs: int = 500, seed: int = 11) -> dict:
    """Bootstrap the *order* of trades to get a drawdown distribution (assumes independence)."""
    if len(trades) < 5:
        return {"runs": 0, "note": "fewer than 5 trades"}
    rng = np.random.default_rng(seed)
    pnl = np.asarray([t.pnl_usd for t in trades])
    dds = []
    finals = []
    for _ in range(runs):
        sample = rng.choice(pnl, size=len(pnl), replace=True)
        eq = starting_equity + np.cumsum(sample)
        peak = np.maximum.accumulate(np.insert(eq, 0, starting_equity))
        dds.append(float((peak[1:] - eq).max()))
        finals.append(float(eq[-1] - starting_equity))
    return {
        "runs": runs,
        "max_drawdown_p50": round(float(np.percentile(dds, 50)), 2),
        "max_drawdown_p95": round(float(np.percentile(dds, 95)), 2),
        "max_drawdown_p99": round(float(np.percentile(dds, 99)), 2),
        "final_pnl_p05": round(float(np.percentile(finals, 5)), 2),
        "final_pnl_p50": round(float(np.percentile(finals, 50)), 2),
        "probability_of_loss": round(float(np.mean(np.asarray(finals) < 0)), 3),
        "assumption": "trade outcomes independent and identically distributed; ignores regime clustering",
    }


def cost_sensitivity(bt: Backtester, strategy: Strategy, cfg: BacktestConfig, multipliers=(0.5, 1.0, 1.5, 2.0)) -> list[dict]:
    out = []
    for m in multipliers:
        r = bt.run(strategy, replace(cfg, spread_multiplier=m, slippage_multiplier=m, label=f"{cfg.label}_cost_x{m}"))
        out.append({"cost_multiplier": m, "trades": r.metrics.get("trades", 0), "expectancy_r": r.metrics.get("expectancy_r"), "net_usd": r.metrics.get("net_usd"), "max_drawdown_usd": r.metrics.get("max_drawdown_usd")})
    return out


def threshold_sensitivity(result: BacktestResult, starting_equity: float, period_days: float, thresholds=(0, 50, 55, 60, 65, 70, 75, 80)) -> list[dict]:
    """Re-slice one research run (score recorded, not filtered) by score threshold. No re-run, no leakage."""
    out = []
    for th in thresholds:
        sub = [t for t in result.trades if t.score is not None and t.score >= th]
        m = compute_metrics(sub, starting_equity, period_days, f"th>={th}") if sub else {"trades": 0}
        out.append({"threshold": th, "trades": m.get("trades", 0), "trades_per_year": m.get("trades_per_year"), "expectancy_r": m.get("expectancy_r"), "win_rate": m.get("win_rate"), "max_drawdown_r": m.get("max_drawdown_r"), "profit_factor": m.get("profit_factor")})
    return out


def parameter_stability(bt: Backtester, strategy: Strategy, cfg: BacktestConfig, param: str, values: list) -> list[dict]:
    out = []
    for v in values:
        r = bt.run(strategy, replace(cfg, params_override=cfg.params_override | {param: v}, label=f"{cfg.label}_{param}={v}"))
        out.append({"param": param, "value": v, "trades": r.metrics.get("trades", 0), "expectancy_r": r.metrics.get("expectancy_r"), "max_drawdown_r": r.metrics.get("max_drawdown_r")})
    return out


def benchmark_buy_and_hold(bt: Backtester, cfg: BacktestConfig) -> dict:
    from ..core.candles import Timeframe

    d1 = [c for c in bt.market.get_candles("XAUUSD", Timeframe.D1, cfg.start, cfg.end) if c.complete]
    if len(d1) < 2:
        return {"note": "insufficient daily data"}
    ret = d1[-1].close / d1[0].open - 1
    eq = np.asarray([c.close for c in d1]) / d1[0].open
    peak = np.maximum.accumulate(eq)
    return {"buy_and_hold_return_pct": round(ret * 100, 2), "buy_and_hold_max_drawdown_pct": round(float(((peak - eq) / peak).max() * 100), 2), "note": "unlevered spot gold over the same period; ignores financing"}


def multiple_testing_note(n_configs_tested: int, best_expectancy_ci_low: float | None) -> dict:
    return {
        "configurations_tested": n_configs_tested,
        "bonferroni_style_caution": f"With {n_configs_tested} configurations examined, a single result significant at 5% has roughly {min(1.0, 0.05 * n_configs_tested):.0%} family-wise false-positive risk.",
        "best_expectancy_ci_low": best_expectancy_ci_low,
        "verdict_hint": "Only treat the strategy as promising if the OOS expectancy CI lower bound stays above zero after this caution.",
    }


def oos_calibration_payload(oos_trades: list[TradeRecord], label: str, data_label: str) -> dict:
    """The validation dictionary consumed by core.calibration.calibrated_probability."""
    buckets: dict[str, dict] = {}
    for t in oos_trades:
        if t.score is None:
            continue
        b = buckets.setdefault(bucket_for(t.score), {"n": 0, "wins": 0})
        b["n"] += 1
        b["wins"] += int(t.win)
    n = len(oos_trades)
    rs = [t.r for t in oos_trades]
    return {"sample_size": n, "wins": sum(1 for t in oos_trades if t.win), "buckets": buckets, "expectancy_r": round(float(np.mean(rs)), 4) if rs else None, "label": label, "data_label": data_label}


def run_validation(bt: Backtester, strategy: Strategy, start: datetime, end: datetime, train_days: int = 60, test_days: int = 30, starting_equity: float = 10000.0, data_label: str = "DEMO") -> dict:
    """Full research report for one strategy. Research runs record the score without filtering so
    threshold selection can be done on OOS windows only."""
    splits = walk_forward_splits(start, end, train_days, test_days)
    is_trades: list[TradeRecord] = []
    oos_trades: list[TradeRecord] = []
    windows = []
    for i, s in enumerate(splits):
        tr = bt.run(strategy, BacktestConfig(strategy.id, s.train_start, s.train_end, starting_equity, label=f"IS_{i}", data_label=data_label))
        te = bt.run(strategy, BacktestConfig(strategy.id, s.test_start, s.test_end, starting_equity, label=f"OOS_{i}", data_label=data_label))
        is_trades += tr.trades
        oos_trades += te.trades
        windows.append({"split": i, "train": [s.train_start.isoformat(), s.train_end.isoformat()], "test": [s.test_start.isoformat(), s.test_end.isoformat()], "is_trades": len(tr.trades), "is_expectancy_r": tr.metrics.get("expectancy_r"), "oos_trades": len(te.trades), "oos_expectancy_r": te.metrics.get("expectancy_r")})
    period = (end - start).total_seconds() / 86400
    is_m = compute_metrics(is_trades, starting_equity, period, "IN_SAMPLE")
    oos_m = compute_metrics(oos_trades, starting_equity, period, "OUT_OF_SAMPLE")
    full_cfg = BacktestConfig(strategy.id, start, end, starting_equity, label="FULL_RESEARCH", data_label=data_label)
    full = bt.run(strategy, full_cfg)
    th = threshold_sensitivity(full, starting_equity, period)
    # select threshold on OOS windows only: highest threshold that keeps >= 20 OOS trades and best expectancy CI-low proxy
    oos_res = BacktestResult(full.config_hash, strategy.id, strategy.definition.version, "OOS", data_label, start, end, oos_trades, oos_m, 0, 0, {}, [], "")
    oos_th = threshold_sensitivity(oos_res, starting_equity, period)
    candidates = [r for r in oos_th if r["trades"] >= 20 and (r["expectancy_r"] or -1) > 0]
    chosen = max(candidates, key=lambda r: ((r["expectancy_r"] or 0) - 0.02 * (r["max_drawdown_r"] or 0), r["threshold"])) if candidates else None
    report = {
        "strategy_id": strategy.id,
        "strategy_version": strategy.definition.version,
        "data_label": data_label,
        "period": [start.isoformat(), end.isoformat()],
        "walk_forward": windows,
        "in_sample": is_m,
        "out_of_sample": oos_m,
        "threshold_sensitivity_full": th,
        "threshold_sensitivity_oos": oos_th,
        "proposed_threshold": chosen["threshold"] if chosen else None,
        "threshold_selection_rule": "highest OOS expectancy net of 0.02R per R of drawdown, requiring >=20 OOS trades and positive expectancy; not profit-maximising",
        "monte_carlo_oos": monte_carlo(oos_trades, starting_equity),
        "cost_sensitivity": cost_sensitivity(bt, strategy, replace(full_cfg, label="COST")),
        "benchmark": benchmark_buy_and_hold(bt, full_cfg),
        "multiple_testing": multiple_testing_note(len(th) + 4, oos_m.get("expectancy_r_ci95_bootstrap", [None])[0] if oos_m.get("trades") else None),
        "calibration_payload": oos_calibration_payload(oos_trades, "OOS", data_label),
        "full_run_hash": full.trades_hash,
        "warnings": full.warnings + (["Demo data: this report validates the pipeline, not the strategy."] if data_label == "DEMO" else []),
        "acceptance_checklist": acceptance_checklist(oos_m, is_m, chosen),
    }
    return report


def acceptance_checklist(oos: dict, is_: dict, chosen: dict | None) -> dict:
    n = oos.get("trades", 0)
    ci = oos.get("expectancy_r_ci95_bootstrap", [None, None])
    return {
        "positive_oos_expectancy": bool(n and (oos.get("expectancy_r") or 0) > 0),
        "oos_ci_low_above_zero": bool(ci and ci[0] is not None and ci[0] > 0),
        "sample_size_at_least_30": n >= 30,
        "drawdown_r_under_10": bool(n and (oos.get("max_drawdown_r") or 99) < 10),
        "is_oos_expectancy_gap_under_0_3R": bool(n and is_.get("trades") and abs((is_.get("expectancy_r") or 0) - (oos.get("expectancy_r") or 0)) < 0.3),
        "threshold_selected_on_oos": chosen is not None,
        "human_approval_required": True,
        "note": "Thresholds here are proposed defaults for review, not universal acceptance rules; see docs/17-backtesting-methodology.md.",
    }
