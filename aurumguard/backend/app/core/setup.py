"""Decision and setup data model.

A TradeSetup carries every mandatory field listed in the specification. A
Decision wraps at most one setup with its status and the Evidence Inspector
payload. Both are plain dataclasses serialised to JSON for storage and API.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum


class DecisionStatus(str, Enum):
    BUY_SETUP = "BUY_SETUP"
    SELL_SETUP = "SELL_SETUP"
    WAIT = "WAIT"
    NO_TRADE = "NO_TRADE"
    EVENT_LOCKOUT = "EVENT_LOCKOUT"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class Horizon(str, Enum):
    SCALP = "SCALP"
    INTRADAY = "INTRADAY"
    SWING = "SWING"
    WEEKLY = "WEEKLY"


@dataclass
class Target:
    label: str  # TP1 / TP2 / TP3
    price: float
    rationale: str
    net_reward_to_risk: float | None


@dataclass
class TradeSetup:
    instrument: str
    bid: float
    ask: float
    spread: float
    data_provider: str
    price_timestamp: datetime
    user_timezone: str
    horizon: str
    strategy_id: str
    strategy_name: str
    strategy_version: str
    direction: str  # BUY / SELL
    entry_trigger: str
    entry_zone_low: float
    entry_zone_high: float
    entry_reference: float
    entry_confirmation_required: bool
    entry_confirmed: bool
    stop_loss: float
    stop_rationale: str
    targets: list[Target]
    estimated_spread: float
    estimated_slippage: float
    estimated_fees_usd: float
    estimated_financing_usd: float
    expiry: datetime
    max_holding_until: datetime | None
    market_regime: dict
    news_risk: dict
    supporting_evidence: list[dict]
    contradictory_evidence: list[dict]
    invalidation_conditions: list[str]
    position_size: dict
    total_account_risk_usd: float
    total_account_risk_pct: float
    aggregate_exposure_after_usd: float
    aggregate_exposure_after_pct: float
    confidence_low: float
    confidence_high: float
    confidence_method: str
    historical_sample_size: int
    backtest_approval_status: str
    data_quality_status: str
    notification_timestamp: datetime | None
    uncertainty_statement: str
    evidence_inspector_ref: str
    decision_reason: str
    conflicting_horizons: list[str] = field(default_factory=list)
    contract_spec_id: str = ""
    demo_data: bool = True

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("price_timestamp", "expiry", "max_holding_until", "notification_timestamp"):
            v = d.get(k)
            if isinstance(v, datetime):
                d[k] = v.isoformat()
        return d


@dataclass
class Decision:
    decision_id: str
    status: DecisionStatus
    horizon: str
    strategy_id: str | None
    strategy_version: str | None
    as_of: datetime
    reason: str
    setup: TradeSetup | None
    evidence_inspector: dict
    score: float | None = None
    regime: str | None = None
    demo_data: bool = True
    user_timezone: str = "UTC"

    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "status": self.status.value,
            "horizon": self.horizon,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "as_of": self.as_of.isoformat(),
            "reason": self.reason,
            "score": self.score,
            "regime": self.regime,
            "demo_data": self.demo_data,
            "user_timezone": self.user_timezone,
            "setup": self.setup.to_dict() if self.setup else None,
            "evidence_inspector": self.evidence_inspector,
        }


UNCERTAINTY_STATEMENT = (
    "This setup is uncertain. It is a rule-based analysis of past and current public data, "
    "not a prediction or a guarantee. Losses are possible, including a full loss of the risked amount."
)
