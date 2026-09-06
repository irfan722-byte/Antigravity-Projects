"""Provider registry: builds the configured adapter set and aggregates health."""
from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from .base import CalendarProvider, ETFFlowProvider, MacroSeriesProvider, MarketDataProvider, NewsProvider, PositioningProvider, ProviderHealth, PushProvider, TradingCalendarProvider
from .mock.calendar import MockCalendarProvider, MockTradingCalendarProvider
from .mock.macro import MockETFFlowProvider, MockMacroProvider, MockNewsProvider, MockPositioningProvider, MockPushProvider
from .mock.market import MockMarketDataProvider


@dataclass
class ProviderSet:
    market: MarketDataProvider
    calendar: CalendarProvider
    trading_calendar: TradingCalendarProvider
    macro: MacroSeriesProvider
    news: NewsProvider
    positioning: PositioningProvider
    etf: ETFFlowProvider
    push: PushProvider

    @property
    def demo_mode(self) -> bool:
        return self.market.is_mock

    def health(self) -> list[ProviderHealth]:
        return [p.health() for p in (self.market, self.calendar, self.trading_calendar, self.macro, self.news, self.positioning, self.etf, self.push)]

    def health_ok(self) -> tuple[bool, str]:
        bad = [h for h in self.health() if not h.ok]
        if bad:
            return False, "; ".join(f"{h.kind}:{h.name} {h.last_error or 'unhealthy'}" for h in bad)
        return True, "all providers healthy"


def build_providers(settings: Settings) -> ProviderSet:
    if settings.market_data_provider == "twelvedata":
        from .twelvedata import TwelveDataProvider

        market: MarketDataProvider = TwelveDataProvider(settings.twelvedata_api_key or "")
    else:
        market = MockMarketDataProvider()
    push: PushProvider
    if settings.push_provider == "webpush":
        from ..notifications.webpush import WebPushProvider

        push = WebPushProvider(settings.vapid_public_key or "", settings.vapid_private_key or "", settings.vapid_subject)
    else:
        push = MockPushProvider()
    return ProviderSet(
        market=market,
        calendar=MockCalendarProvider(),
        trading_calendar=MockTradingCalendarProvider(),
        macro=MockMacroProvider(),
        news=MockNewsProvider(),
        positioning=MockPositioningProvider(),
        etf=MockETFFlowProvider(),
        push=push,
    )
