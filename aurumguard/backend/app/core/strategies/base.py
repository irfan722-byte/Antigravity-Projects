"""Strategy interface and registry.

Strategy *logic* lives in code (versioned). Strategy *metadata, status,
validation results and approval history* live in the registry JSON file and
the database. A strategy can only issue setups when its registry status is
APPROVED, and only the admin approval workflow can set that status.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ...config import load_json_config
from ..candles import Candle, Quote, Timeframe
from ..evidence import Evidence
from ..regime import RegimeAssessment
from ..structure import StructureParams, StructureSnapshot


@dataclass
class StrategyContext:
    as_of: datetime
    quote: Quote
    candles: dict[Timeframe, list[Candle]]  # closed candles only, per timeframe
    structures: dict[Timeframe, StructureSnapshot]
    regime: RegimeAssessment
    session_label: str
    news_phase: str
    news_context: dict
    intermarket_evidence: list[Evidence]
    macro_evidence: list[Evidence]
    positioning_evidence: list[Evidence]
    params: dict = field(default_factory=dict)
    structure_params: StructureParams = field(default_factory=StructureParams)
    latest_event_reaction: dict | None = None


@dataclass
class StrategyProposal:
    direction: str  # BUY / SELL
    entry_type: str  # market / limit / stop
    entry_reference: float
    entry_zone_low: float
    entry_zone_high: float
    entry_trigger: str
    confirmation_required: bool
    confirmed: bool
    stop: float
    stop_rationale: str
    tp1: float
    tp1_rationale: str
    tp2: float
    tp2_rationale: str
    expiry: datetime
    max_holding_until: datetime | None
    invalidation: list[str]
    evidence: list[Evidence]
    rules_triggered: list[str]
    rules_not_triggered: list[str]
    tp3: float | None = None
    tp3_rationale: str | None = None
    developing: bool = False  # True => WAIT (setup forming, confirmation pending)
    note: str = ""


@dataclass
class StrategyDefinition:
    id: str
    name: str
    version: str
    owner: str
    status: str
    horizon: str
    hypothesis: str
    rationale: str
    required_data: list[str]
    instruments: list[str]
    timeframes: list[str]
    sessions: list[str]
    approved_regimes: list[str]
    prohibited_regimes: list[str]
    entry_setup: str
    entry_trigger: str
    confirmation_rules: list[str]
    invalidation_rules: list[str]
    stop_methodology: str
    tp1_methodology: str
    tp2_methodology: str
    sizing_methodology: str
    min_net_rr: float
    spread_limit: float
    slippage_limit: float
    news_restrictions: str
    setup_expiry_minutes: int
    max_holding_minutes: int | None
    known_failure_regimes: list[str]
    suspension_rules: dict
    retirement_rules: list[str]
    params: dict
    backtest_results: dict = field(default_factory=dict)
    validation_results: dict = field(default_factory=dict)
    paper_results: dict = field(default_factory=dict)
    approval_history: list[dict] = field(default_factory=list)
    change_log: list[dict] = field(default_factory=list)
    partial_close_at_tp1_pct: float = 50.0
    move_to_breakeven_after_tp1: bool = False
    trailing_stop: dict | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


class Strategy(ABC):
    definition: StrategyDefinition

    def __init__(self, definition: StrategyDefinition):
        self.definition = definition

    @property
    def id(self) -> str:
        return self.definition.id

    @abstractmethod
    def evaluate(self, ctx: StrategyContext) -> StrategyProposal | None:
        """Return a proposal (possibly ``developing``) or None when no setup exists."""

    def expiry_for(self, as_of: datetime) -> datetime:
        return as_of + timedelta(minutes=self.definition.setup_expiry_minutes)

    def max_hold_for(self, as_of: datetime) -> datetime | None:
        if self.definition.max_holding_minutes is None:
            return None
        return as_of + timedelta(minutes=self.definition.max_holding_minutes)


def load_definitions() -> dict[str, StrategyDefinition]:
    raw = load_json_config("strategy_registry.json")
    out: dict[str, StrategyDefinition] = {}
    for item in raw["strategies"]:
        out[item["id"]] = StrategyDefinition(**item)
    return out
