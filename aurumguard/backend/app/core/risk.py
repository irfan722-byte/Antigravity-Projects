"""Risk management: limits, account state, position sizing and net reward-to-risk.

Design rules enforced here (and tested):
- Position size is floored to the lot step, never rounded up.
- If the minimum contract exceeds the risk budget the result is SKIP.
- Effective risk includes stop distance + spread + entry and exit slippage + commission.
- Limits are validated against configured bounds; a value outside the bounds is rejected.
- No martingale, no loss-based scaling, no stop widening: there is simply no code path for it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import load_json_config
from .contract_spec import ContractSpec


class SizeStatus(str, Enum):
    OK = "OK"
    SKIP_MIN_CONTRACT = "SKIP: MINIMUM CONTRACT SIZE EXCEEDS RISK LIMIT"
    INVALID = "INVALID"


@dataclass(frozen=True)
class RiskLimits:
    account_equity: float
    account_currency: str
    risk_per_trade_pct: float
    max_daily_loss_pct: float
    max_weekly_loss_pct: float
    max_monthly_drawdown_pct: float
    max_concurrent_positions: int
    max_aggregate_open_risk_pct: float
    max_trades_per_day: int
    max_consecutive_losses: int
    max_spread_usd: float
    max_expected_slippage_usd: float
    min_net_reward_to_risk: float
    event_risk_preference: str = "avoid"
    daily_lockout_enabled: bool = True
    weekly_lockout_enabled: bool = True
    friday_cutoff_local: str = "20:00"
    friday_auto_close_paper: bool = True

    @classmethod
    def defaults(cls) -> RiskLimits:
        d = load_json_config("risk_defaults.json")["defaults"]
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def validate(self) -> list[str]:
        bounds = load_json_config("risk_defaults.json")["bounds"]
        problems = []
        for k, (lo, hi) in bounds.items():
            v = getattr(self, k)
            if not (lo <= v <= hi):
                problems.append(f"{k}={v} outside allowed range [{lo}, {hi}]")
        if self.account_equity <= 0:
            problems.append("account_equity must be positive")
        if self.account_currency not in ("USD", "AED"):
            problems.append("account_currency must be USD or AED")
        if self.event_risk_preference not in ("avoid", "reduced", "allow_post_confirmation"):
            problems.append("event_risk_preference invalid")
        return problems

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class OpenRisk:
    position_id: str
    strategy_id: str
    horizon: str
    direction: str
    risk_usd: float


@dataclass
class AccountState:
    """Point-in-time account facts used for gate checks. All money in USD."""

    equity_usd: float
    realised_today_usd: float
    realised_week_usd: float
    month_peak_equity_usd: float
    open_risks: list[OpenRisk] = field(default_factory=list)
    trades_today: int = 0
    consecutive_losses: int = 0
    manual_lock_until: datetime | None = None

    @property
    def aggregate_open_risk_usd(self) -> float:
        return sum(r.risk_usd for r in self.open_risks)


@dataclass
class CostModel:
    spread: float
    slippage_entry: float
    slippage_exit: float
    commission_per_lot_usd: float = 0.0
    financing_estimate_usd: float = 0.0

    @property
    def total_slippage(self) -> float:
        return self.slippage_entry + self.slippage_exit


@dataclass
class PositionSizeResult:
    status: SizeStatus
    lots: float
    risk_budget_usd: float
    risk_usd: float
    risk_pct: float
    stop_distance: float
    effective_adverse_distance: float
    risk_per_lot_usd: float
    cost_breakdown: dict
    reason: str
    equity_usd: float
    spec_id: str

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "lots": self.lots,
            "risk_budget_usd": round(self.risk_budget_usd, 2),
            "risk_usd": round(self.risk_usd, 2),
            "risk_pct": round(self.risk_pct, 4),
            "stop_distance": round(self.stop_distance, 2),
            "effective_adverse_distance": round(self.effective_adverse_distance, 2),
            "risk_per_lot_usd": round(self.risk_per_lot_usd, 2),
            "cost_breakdown": self.cost_breakdown,
            "reason": self.reason,
            "equity_usd": round(self.equity_usd, 2),
            "contract_spec": self.spec_id,
        }


def to_usd(amount: float, currency: str, usd_aed_rate: float) -> float:
    if currency == "USD":
        return amount
    if currency == "AED":
        return amount / usd_aed_rate
    raise ValueError(f"unsupported currency {currency}")


def floor_to_step(x: float, step: float) -> float:
    n = math.floor(x / step + 1e-9)
    return round(n * step, 6)


def compute_position_size(
    equity_usd: float,
    risk_pct: float,
    entry: float,
    stop: float,
    direction: str,
    costs: CostModel,
    spec: ContractSpec,
) -> PositionSizeResult:
    if entry <= 0 or stop <= 0 or not math.isfinite(entry) or not math.isfinite(stop):
        return PositionSizeResult(SizeStatus.INVALID, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, {}, "invalid entry/stop", equity_usd, spec.spec_id)
    if direction == "BUY" and stop >= entry:
        return PositionSizeResult(SizeStatus.INVALID, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, {}, "BUY stop must be below entry", equity_usd, spec.spec_id)
    if direction == "SELL" and stop <= entry:
        return PositionSizeResult(SizeStatus.INVALID, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, {}, "SELL stop must be above entry", equity_usd, spec.spec_id)
    if risk_pct <= 0 or equity_usd <= 0:
        return PositionSizeResult(SizeStatus.INVALID, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, {}, "risk percentage and equity must be positive", equity_usd, spec.spec_id)
    budget = equity_usd * risk_pct / 100.0
    stop_distance = abs(entry - stop)
    # A BUY enters at the ask and stops out at the bid: the spread is paid once
    # across the round trip. Slippage is assumed on both fills.
    eff = stop_distance + costs.spread + costs.total_slippage
    risk_per_lot = eff * spec.usd_per_lot_per_1usd_move + costs.commission_per_lot_usd
    raw_lots = budget / risk_per_lot
    lots = floor_to_step(min(raw_lots, spec.max_lot), spec.lot_step)
    breakdown = {
        "stop_distance": round(stop_distance, 2),
        "spread": costs.spread,
        "slippage_entry": costs.slippage_entry,
        "slippage_exit": costs.slippage_exit,
        "commission_per_lot_usd": costs.commission_per_lot_usd,
        "financing_estimate_usd": costs.financing_estimate_usd,
        "usd_per_lot_per_1usd_move": spec.usd_per_lot_per_1usd_move,
    }
    if lots < spec.min_lot:
        min_risk = spec.min_lot * risk_per_lot
        return PositionSizeResult(
            SizeStatus.SKIP_MIN_CONTRACT, 0.0, budget, min_risk, min_risk / equity_usd * 100, stop_distance, eff, risk_per_lot, breakdown,
            f"minimum lot {spec.min_lot} would risk {min_risk:.2f} USD ({min_risk / equity_usd * 100:.2f}%) which exceeds the {budget:.2f} USD budget", equity_usd, spec.spec_id,
        )
    risk_usd = lots * risk_per_lot
    return PositionSizeResult(SizeStatus.OK, lots, budget, risk_usd, risk_usd / equity_usd * 100, stop_distance, eff, risk_per_lot, breakdown, f"{lots} lots risking {risk_usd:.2f} USD of {budget:.2f} budget", equity_usd, spec.spec_id)


def net_reward_to_risk(entry: float, stop: float, target: float, direction: str, costs: CostModel, spec: ContractSpec) -> float | None:
    """Cost-adjusted reward-to-risk for one target (per lot, so size cancels)."""
    if direction == "BUY":
        gross_reward = target - entry
    else:
        gross_reward = entry - target
    if gross_reward <= 0:
        return None
    reward = (gross_reward - costs.spread - costs.total_slippage) * spec.usd_per_lot_per_1usd_move - costs.commission_per_lot_usd - costs.financing_estimate_usd
    risk = (abs(entry - stop) + costs.spread + costs.total_slippage) * spec.usd_per_lot_per_1usd_move + costs.commission_per_lot_usd
    if risk <= 0:
        return None
    return reward / risk


def risk_checks(limits: RiskLimits, account: AccountState, proposed_risk_usd: float, now: datetime) -> dict[str, tuple[bool, str]]:
    """Return gate code -> (ok, reason) for G09..G12. Nothing here can be bypassed by the UI."""
    out: dict[str, tuple[bool, str]] = {}
    eq = account.equity_usd
    # G09: per-trade risk, concurrent positions, trades/day, consecutive losses, manual lock
    reasons = []
    ok = True
    if proposed_risk_usd > eq * limits.risk_per_trade_pct / 100.0 + 1e-6:
        ok = False
        reasons.append(f"proposed risk {proposed_risk_usd:.2f} > per-trade limit {eq * limits.risk_per_trade_pct / 100:.2f}")
    if len(account.open_risks) >= limits.max_concurrent_positions:
        ok = False
        reasons.append(f"{len(account.open_risks)} open positions >= max {limits.max_concurrent_positions}")
    if account.trades_today >= limits.max_trades_per_day:
        ok = False
        reasons.append(f"{account.trades_today} trades today >= max {limits.max_trades_per_day}")
    if account.consecutive_losses >= limits.max_consecutive_losses:
        ok = False
        reasons.append(f"{account.consecutive_losses} consecutive losses >= max {limits.max_consecutive_losses}")
    if account.manual_lock_until and now < account.manual_lock_until:
        ok = False
        reasons.append(f"manual lock active until {account.manual_lock_until.isoformat()}")
    out["G09"] = (ok, "; ".join(reasons) or "within per-trade, count and streak limits")
    # G10 daily
    daily_limit = eq * limits.max_daily_loss_pct / 100.0
    hit = limits.daily_lockout_enabled and account.realised_today_usd <= -daily_limit
    out["G10"] = (not hit, f"realised today {account.realised_today_usd:.2f} vs limit -{daily_limit:.2f}")
    # G11 weekly
    weekly_limit = eq * limits.max_weekly_loss_pct / 100.0
    hitw = limits.weekly_lockout_enabled and account.realised_week_usd <= -weekly_limit
    out["G11"] = (not hitw, f"realised this week {account.realised_week_usd:.2f} vs limit -{weekly_limit:.2f}")
    # G12 aggregate exposure + monthly drawdown
    agg = account.aggregate_open_risk_usd + proposed_risk_usd
    agg_limit = eq * limits.max_aggregate_open_risk_pct / 100.0
    dd = (account.month_peak_equity_usd - eq) / account.month_peak_equity_usd * 100 if account.month_peak_equity_usd > 0 else 0.0
    agg_ok = agg <= agg_limit + 1e-6 and dd < limits.max_monthly_drawdown_pct
    out["G12"] = (agg_ok, f"aggregate open risk after setup {agg:.2f} vs limit {agg_limit:.2f}; month drawdown {dd:.2f}% vs limit {limits.max_monthly_drawdown_pct}%")
    return out


def lock_status(limits: RiskLimits, account: AccountState, now: datetime) -> dict:
    checks = risk_checks(limits, account, 0.0, now)
    return {
        "daily_locked": not checks["G10"][0],
        "weekly_locked": not checks["G11"][0],
        "exposure_locked": not checks["G12"][0],
        "streak_or_count_locked": not checks["G09"][0],
        "details": {k: v[1] for k, v in checks.items()},
    }
