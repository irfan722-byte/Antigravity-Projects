"""Provider interfaces. Every external data dependency sits behind one of these.

Adapters must: stamp provider name, source timestamp and ingestion timestamp on
every record; raise ProviderError on failure (never return invented data); and
report health so the decision engine can gate on it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, time

from ..core.candles import Candle, Quote, Timeframe
from ..core.news_state import EconomicEvent


class ProviderError(Exception):
    pass


class RateLimited(ProviderError):
    pass


@dataclass
class ProviderHealth:
    name: str
    kind: str
    ok: bool
    is_mock: bool
    last_success: datetime | None
    last_error: str | None
    latency_ms: float | None
    consecutive_failures: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "ok": self.ok,
            "is_mock": self.is_mock,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_error": self.last_error,
            "latency_ms": self.latency_ms,
            "consecutive_failures": self.consecutive_failures,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ProviderDoc:
    """Documentation block required for every data source (see docs/08-data-provider-plan.md)."""

    fields: list[str]
    frequency: str
    latency: str
    historical_depth: str
    revision_behaviour: str
    licensing: str
    rate_limit: str
    cost_category: str
    failure_behaviour: str
    backup_options: list[str]
    suitable_for_scalping: bool


class BaseProvider(ABC):
    name: str = "base"
    kind: str = "base"
    is_mock: bool = False
    doc: ProviderDoc | None = None

    @abstractmethod
    def health(self) -> ProviderHealth: ...


class MarketDataProvider(BaseProvider):
    kind = "market_data"

    @abstractmethod
    def get_quote(self, instrument: str, now: datetime) -> Quote: ...

    @abstractmethod
    def get_candles(self, instrument: str, timeframe: Timeframe, start: datetime, end: datetime) -> list[Candle]: ...

    def median_spread(self, instrument: str, now: datetime) -> float | None:
        return None


class CalendarProvider(BaseProvider):
    kind = "economic_calendar"

    @abstractmethod
    def get_events(self, start: datetime, end: datetime, now: datetime) -> list[EconomicEvent]: ...

    def reaction_history(self) -> dict:
        return {}


@dataclass(frozen=True)
class SeriesPoint:
    ts: datetime
    value: float
    provider: str
    ingested_at: datetime
    revision_of: str | None = None


class MacroSeriesProvider(BaseProvider):
    """Official macro releases, Treasury yields, dollar index proxy, real-yield proxy."""

    kind = "macro_series"

    @abstractmethod
    def get_series(self, series_id: str, start: datetime, end: datetime, as_of: datetime) -> list[SeriesPoint]: ...

    @abstractmethod
    def available_series(self) -> dict[str, str]: ...


@dataclass(frozen=True)
class NewsItem:
    news_id: str
    ts: datetime
    headline: str
    source: str
    url: str | None
    provider: str
    ingested_at: datetime
    body_excerpt: str = ""
    verified_source: bool = False


class NewsProvider(BaseProvider):
    kind = "news"

    @abstractmethod
    def get_news(self, start: datetime, end: datetime) -> list[NewsItem]: ...


@dataclass(frozen=True)
class PositioningReport:
    report_date: date
    published_ts: datetime
    managed_money_long: float
    managed_money_short: float
    open_interest: float | None
    provider: str
    ingested_at: datetime

    @property
    def net(self) -> float:
        return self.managed_money_long - self.managed_money_short


class PositioningProvider(BaseProvider):
    kind = "futures_positioning"

    @abstractmethod
    def get_reports(self, start: date, end: date, as_of: datetime) -> list[PositioningReport]: ...


@dataclass(frozen=True)
class ETFFlow:
    flow_date: date
    published_ts: datetime
    net_flow_tonnes: float
    provider: str
    ingested_at: datetime


class ETFFlowProvider(BaseProvider):
    kind = "etf_flows"

    @abstractmethod
    def get_flows(self, start: date, end: date, as_of: datetime) -> list[ETFFlow]: ...


class TradingCalendarProvider(BaseProvider):
    kind = "trading_calendar"

    @abstractmethod
    def holidays(self, year: int) -> set[date]: ...

    @abstractmethod
    def early_closes_ny(self, year: int) -> dict[date, time]: ...

    @abstractmethod
    def verified(self) -> bool: ...


@dataclass
class PushMessage:
    title: str
    body: str
    data: dict
    priority: str = "normal"
    tag: str | None = None


@dataclass
class PushResult:
    ok: bool
    provider: str
    detail: str
    ts: datetime


class PushProvider(BaseProvider):
    kind = "push"

    @abstractmethod
    def send(self, subscription: dict, message: PushMessage) -> PushResult: ...
