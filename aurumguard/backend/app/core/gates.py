"""Hard gates. Any failed applicable gate blocks setup generation."""
from __future__ import annotations

from dataclasses import dataclass, field

from .integrity import DataStatus


@dataclass(frozen=True)
class GateResult:
    code: str
    name: str
    passed: bool
    reason: str
    applicable: bool = True

    def to_dict(self) -> dict:
        return {"code": self.code, "name": self.name, "passed": self.passed, "applicable": self.applicable, "reason": self.reason}


@dataclass
class GateContext:
    """Everything the gate evaluator needs. Populated by the decision engine."""

    data_status: DataStatus
    data_reasons: list[str]
    event_ts_verified: bool
    spread: float | None
    max_spread: float
    expected_slippage: float | None
    max_slippage: float
    session_label: str
    allowed_sessions: list[str]
    news_phase: str
    strategy_status: str  # APPROVED / RESEARCH / SUSPENDED / RETIRED
    regime_primary: str
    regime_tags: list[str]
    approved_regimes: list[str]
    prohibited_regimes: list[str]
    risk_checks: dict[str, tuple[bool, str]]  # from RiskManager: code -> (ok, reason)
    net_rr_tp1: float | None
    min_net_rr: float
    position_size_ok: bool
    position_size_reason: str
    econ_conflict_unresolved: bool
    provider_health_ok: bool
    provider_health_reason: str
    probability_in_range: bool
    probability_reason: str
    calendar_verified: bool
    timezone_verified: bool
    price_confirmation_required: bool
    price_confirmed: bool
    market_open: bool = True
    extra: dict = field(default_factory=dict)


def evaluate_gates(ctx: GateContext) -> list[GateResult]:
    g: list[GateResult] = []

    g.append(GateResult("G01", "Required data fresh and present", ctx.data_status != DataStatus.INVALID, "; ".join(ctx.data_reasons) or "ok"))
    g.append(GateResult("G02", "Event timestamps verified", ctx.event_ts_verified, "ok" if ctx.event_ts_verified else "an economic event in scope has unverified timestamps"))
    if ctx.spread is None:
        g.append(GateResult("G03", "Spread within limit", False, "spread unknown"))
    else:
        g.append(GateResult("G03", "Spread within limit", ctx.spread <= ctx.max_spread, f"spread {ctx.spread:.2f} vs limit {ctx.max_spread:.2f}"))
    if ctx.expected_slippage is None:
        g.append(GateResult("G04", "Expected slippage within limit", False, "slippage estimate unavailable"))
    else:
        g.append(GateResult("G04", "Expected slippage within limit", ctx.expected_slippage <= ctx.max_slippage, f"slippage {ctx.expected_slippage:.2f} vs limit {ctx.max_slippage:.2f}"))
    sess_ok = (not ctx.allowed_sessions) or ctx.session_label in ctx.allowed_sessions or any(s in ctx.session_label for s in ctx.allowed_sessions)
    g.append(GateResult("G05", "Session permitted", sess_ok and ctx.market_open, f"session {ctx.session_label}, market_open={ctx.market_open}, allowed={ctx.allowed_sessions or 'any'}"))
    lock = ctx.news_phase in ("RELEASE_LOCKOUT", "PRE_EVENT_LOCKOUT")
    g.append(GateResult("G06", "No event lockout", not lock, f"news phase {ctx.news_phase}"))
    g.append(GateResult("G07", "Strategy approved", ctx.strategy_status == "APPROVED", f"strategy status {ctx.strategy_status}"))
    regime_set = {ctx.regime_primary, *ctx.regime_tags}
    prohibited_hit = sorted(regime_set & set(ctx.prohibited_regimes))
    approved_hit = (not ctx.approved_regimes) or (ctx.regime_primary in ctx.approved_regimes)
    reg_ok = approved_hit and not prohibited_hit and ctx.regime_primary != "UNKNOWN"
    g.append(GateResult("G08", "Regime approved for strategy", reg_ok, f"regime {ctx.regime_primary} tags {ctx.regime_tags}; prohibited hit {prohibited_hit}"))
    for code, name in (
        ("G09", "Per-trade risk limit"),
        ("G10", "Daily loss limit not reached"),
        ("G11", "Weekly loss limit not reached"),
        ("G12", "Aggregate exposure within limit"),
    ):
        ok, reason = ctx.risk_checks.get(code, (False, "risk check missing"))
        g.append(GateResult(code, name, ok, reason))
    if ctx.net_rr_tp1 is None:
        g.append(GateResult("G13", "Minimum cost-adjusted reward-to-risk", False, "reward-to-risk not computable"))
    else:
        g.append(GateResult("G13", "Minimum cost-adjusted reward-to-risk", ctx.net_rr_tp1 >= ctx.min_net_rr, f"net R:R to TP1 {ctx.net_rr_tp1:.2f} vs min {ctx.min_net_rr:.2f}"))
    g.append(GateResult("G14", "Position size complies with risk limit", ctx.position_size_ok, ctx.position_size_reason))
    g.append(GateResult("G15", "No unresolved economic-data conflict", not ctx.econ_conflict_unresolved, "ok" if not ctx.econ_conflict_unresolved else "providers disagree on a released figure"))
    g.append(GateResult("G16", "Provider health acceptable", ctx.provider_health_ok, ctx.provider_health_reason))
    g.append(GateResult("G17", "Probability model in validated range", ctx.probability_in_range, ctx.probability_reason))
    g.append(GateResult("G18", "Strategy not suspended", ctx.strategy_status != "SUSPENDED", f"status {ctx.strategy_status}"))
    g.append(GateResult("G19", "Timezone and market calendar verified", ctx.calendar_verified and ctx.timezone_verified, f"calendar={ctx.calendar_verified} timezone={ctx.timezone_verified}"))
    if ctx.price_confirmation_required:
        g.append(GateResult("G20", "Required price confirmation occurred", ctx.price_confirmed, "confirmed" if ctx.price_confirmed else "waiting for trigger confirmation"))
    else:
        g.append(GateResult("G20", "Required price confirmation occurred", True, "not required by strategy", applicable=False))
    return g


def all_passed(results: list[GateResult]) -> bool:
    return all(r.passed for r in results if r.applicable)


def failed_codes(results: list[GateResult]) -> list[str]:
    return [r.code for r in results if r.applicable and not r.passed]
