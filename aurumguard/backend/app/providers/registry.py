"""Provider registry: builds the configured adapter set and aggregates health."""
from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from .base import CalendarProvider, ETFFlowProvider, MacroSeriesProvider, MarketDataProvider, NewsProvider, PositioningProvider, ProviderHealth, PushProvider, TradingCalendarProvider
from .mock.calendar import MockCalendarProvider, MockTradingCalendarProvider
from .mock.macro import MockETFFlowProvider, MockMacroProvider, MockNewsProvider, MockPositioningProvider, MockPushProvider
from .mock.market import MockMarketDataProvider
from .none import NoCalendarProvider, NoNewsProvider


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

    @property
    def data_mode(self) -> str:
        return "DEMO" if self.market.is_mock else "LIVE_PRICES"

    def summary(self) -> dict[str, dict]:
        """Per-kind provider status for the UI banner: name, whether synthetic, whether disabled."""

        def one(p) -> dict:
            return {"name": p.name, "is_mock": p.is_mock, "disabled": p.name == "none"}

        return {
            "market_data": one(self.market),
            "economic_calendar": one(self.calendar),
            "trading_calendar": one(self.trading_calendar),
            "macro_series": one(self.macro),
            "news": one(self.news),
            "positioning": one(self.positioning),
            "etf_flows": one(self.etf),
            "push": one(self.push),
        }

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

        market: MarketDataProvider = TwelveDataProvider(settings.twelvedata_api_key or "", quote_ttl_seconds=settings.twelvedata_quote_ttl_seconds, assumed_spread_usd=settings.twelvedata_assumed_spread_usd)
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
        calendar=NoCalendarProvider() if settings.calendar_provider == "none" else MockCalendarProvider(),
        trading_calendar=MockTradingCalendarProvider(),
        macro=MockMacroProvider(),
        news=NoNewsProvider() if settings.news_provider == "none" else MockNewsProvider(),
        positioning=MockPositioningProvider(),
        etf=MockETFFlowProvider(),
        push=push,
    )
