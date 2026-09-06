"""Performance metrics for a list of closed trades. Every figure is labelled by the
sample it came from (in-sample / validation / OOS / paper) by the caller; this
module never mixes samples itself."""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from ..core.calibration import brier_score, bucket_for, wilson


@dataclass
class TradeRecord:
    trade_id: str
    strategy_id: str
    strategy_version: str
    horizon: str
    direction: str
    entry_ts: datetime
    exit_ts: datetime
    entry_price: float
    exit_price: float
    lots: float
    risk_usd: float
    pnl_usd: float
    pnl_gross_usd: float  # before spread/slippage/commission
    costs_usd: float
    exit_reason: str
    session: str
    regime: str
    score: float | None
    near_event: bool
    label: str = ""  # e.g. CONSERVATIVE_SAME_BAR / GAP_THROUGH_STOP
    calibrated_p: float | None = None

    @property
    def r(self) -> float:
        return self.pnl_usd / self.risk_usd if self.risk_usd > 0 else 0.0

    @property
    def win(self) -> bool:
        return self.pnl_usd > 0

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["entry_ts"] = self.entry_ts.isoformat()
        d["exit_ts"] = self.exit_ts.isoformat()
        d["r"] = round(self.r, 4)
        return d


def _drawdowns(equity: np.ndarray) -> tuple[float, float, int]:
    """(max drawdown, average drawdown, longest recovery in steps) on an equity path."""
    if len(equity) == 0:
        return 0.0, 0.0, 0
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    max_dd = float(dd.max())
    in_dd = dd > 0
    avg_dd = float(dd[in_dd].mean()) if in_dd.any() else 0.0
    longest, cur = 0, 0
    for x in in_dd:
        cur = cur + 1 if x else 0
        longest = max(longest, cur)
    return max_dd, avg_dd, longest


def _streaks(wins: list[bool]) -> tuple[int, int]:
    mw = ml = cw = cl = 0
    for w in wins:
        if w:
            cw, cl = cw + 1, 0
        else:
            cl, cw = cl + 1, 0
        mw, ml = max(mw, cw), max(ml, cl)
    return mw, ml


def _group(trades: list[TradeRecord], key) -> dict[str, dict]:
    g: dict[str, list[TradeRecord]] = defaultdict(list)
    for t in trades:
        g[str(key(t))].append(t)
    return {k: _basic(v) for k, v in sorted(g.items())}


def _basic(trades: list[TradeRecord]) -> dict:
    n = len(trades)
    if n == 0:
        return {"trades": 0}
    rs = np.asarray([t.r for t in trades])
    wins = [t for t in trades if t.win]
    losses = [t for t in trades if not t.win]
    gp = sum(t.pnl_usd for t in wins)
    gl = -sum(t.pnl_usd for t in losses)
    return {
        "trades": n,
        "win_rate": round(len(wins) / n, 4),
        "expectancy_r": round(float(rs.mean()), 4),
        "profit_factor": round(gp / gl, 3) if gl > 0 else (None if gp == 0 else float("inf")),
        "net_usd": round(sum(t.pnl_usd for t in trades), 2),
    }


def compute_metrics(trades: list[TradeRecord], starting_equity: float, period_days: float, label: str, seed: int = 7) -> dict:
    n = len(trades)
    if n == 0:
        return {"label": label, "trades": 0, "note": "no closed trades in this sample"}
    trades = sorted(trades, key=lambda t: t.exit_ts)
    pnl = np.asarray([t.pnl_usd for t in trades])
    rs = np.asarray([t.r for t in trades])
    wins = [t for t in trades if t.win]
    losses = [t for t in trades if not t.win]
    equity = starting_equity + np.cumsum(pnl)
    max_dd, avg_dd, rec = _drawdowns(np.insert(equity, 0, starting_equity))
    mw, ml = _streaks([t.win for t in trades])
    gp = float(sum(t.pnl_usd for t in wins))
    gl = float(-sum(t.pnl_usd for t in losses))
    exposure = sum((t.exit_ts - t.entry_ts).total_seconds() for t in trades) / (period_days * 86400) if period_days > 0 else None
    trades_per_year = n / period_days * 365 if period_days > 0 else None
    r_std = float(rs.std(ddof=1)) if n > 1 else 0.0
    sharpe_like = float(rs.mean() / r_std * math.sqrt(trades_per_year)) if r_std > 0 and trades_per_year else None
    downside = rs[rs < 0]
    d_std = float(math.sqrt((downside**2).mean())) if len(downside) else 0.0
    sortino_like = float(rs.mean() / d_std * math.sqrt(trades_per_year)) if d_std > 0 and trades_per_year else None
    net = float(pnl.sum())
    # bootstrap CI for expectancy (trade-level resampling)
    rng = np.random.default_rng(seed)
    boots = np.asarray([rng.choice(rs, size=n, replace=True).mean() for _ in range(1000)])
    ci_lo, ci_hi = float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))
    wr_lo, wr_hi, _ = wilson(len(wins), n)
    gross = float(sum(t.pnl_gross_usd for t in trades))
    costs = float(sum(t.costs_usd for t in trades))
    # calibration buckets & brier
    buckets: dict[str, dict] = {}
    pairs = []
    for t in trades:
        if t.score is not None:
            b = buckets.setdefault(bucket_for(t.score), {"n": 0, "wins": 0})
            b["n"] += 1
            b["wins"] += int(t.win)
        if t.calibrated_p is not None:
            pairs.append((t.calibrated_p, int(t.win)))
    for b in buckets.values():
        b["win_rate"] = round(b["wins"] / b["n"], 3)
    return {
        "label": label,
        "trades": n,
        "period_days": round(period_days, 1),
        "trades_per_year": round(trades_per_year, 1) if trades_per_year else None,
        "win_rate": round(len(wins) / n, 4),
        "win_rate_ci95": [round(wr_lo, 3), round(wr_hi, 3)],
        "loss_rate": round(len(losses) / n, 4),
        "average_win_usd": round(gp / len(wins), 2) if wins else 0.0,
        "average_loss_usd": round(-gl / len(losses), 2) if losses else 0.0,
        "average_win_r": round(float(np.mean([t.r for t in wins])), 3) if wins else 0.0,
        "average_loss_r": round(float(np.mean([t.r for t in losses])), 3) if losses else 0.0,
        "expectancy_r": round(float(rs.mean()), 4),
        "expectancy_r_ci95_bootstrap": [round(ci_lo, 4), round(ci_hi, 4)],
        "expectancy_usd": round(net / n, 2),
        "profit_factor": round(gp / gl, 3) if gl > 0 else None,
        "net_usd": round(net, 2),
        "net_return_pct": round(net / starting_equity * 100, 3),
        "gross_before_costs_usd": round(gross, 2),
        "costs_usd": round(costs, 2),
        "cost_share_of_gross": round(costs / abs(gross), 3) if gross else None,
        "max_drawdown_usd": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd / starting_equity * 100, 3),
        "max_drawdown_r": round(float(_drawdowns(np.insert(np.cumsum(rs), 0, 0.0))[0]), 3),
        "average_drawdown_usd": round(avg_dd, 2),
        "longest_recovery_trades": rec,
        "max_consecutive_wins": mw,
        "max_consecutive_losses": ml,
        "exposure_time_fraction": round(exposure, 4) if exposure is not None else None,
        "sharpe_like_per_trade_annualised": round(sharpe_like, 3) if sharpe_like is not None else None,
        "sortino_like_per_trade_annualised": round(sortino_like, 3) if sortino_like is not None else None,
        "return_to_max_drawdown": round(net / max_dd, 3) if max_dd > 0 else None,
        "metric_limitations": "Sharpe/Sortino-like figures use per-trade R multiples annualised by trade frequency; they are not comparable to daily-return Sharpe ratios and ignore serial correlation.",
        "long": _basic([t for t in trades if t.direction == "BUY"]),
        "short": _basic([t for t in trades if t.direction == "SELL"]),
        "by_year": _group(trades, lambda t: t.exit_ts.year),
        "by_month": _group(trades, lambda t: t.exit_ts.strftime("%Y-%m")),
        "by_session": _group(trades, lambda t: t.session),
        "by_regime": _group(trades, lambda t: t.regime),
        "by_event_proximity": _group(trades, lambda t: "near_event" if t.near_event else "no_event"),
        "by_exit_reason": _group(trades, lambda t: t.exit_reason),
        "labelled_fills": _group([t for t in trades if t.label], lambda t: t.label),
        "calibration_buckets": buckets,
        "brier": round(brier_score(pairs), 4) if pairs else None,
        "equity_curve": [{"ts": t.exit_ts.isoformat(), "equity": round(float(e), 2)} for t, e in zip(trades, equity)],
    }
