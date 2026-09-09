"""Explicit "no data" providers for the economic calendar and the news feed.

Use these when running with real prices but without a licensed calendar or
news source. They return nothing, report healthy, and say so in their health
notes so the UI can show that event awareness is disabled. Unlike the mock
providers they never invent events, so real prices are not locked out by
synthetic releases. The trade-off is real: with no calendar the event gate
(G06) cannot protect you around genuine releases such as CPI or NFP.
"""
from __future__ import annotations

from datetime import datetime

from ..core.news_state import EconomicEvent
from .base import CalendarProvider, NewsItem, NewsProvider, ProviderDoc, ProviderHealth

_NO_DATA_DOC = ProviderDoc(
    fields=[],
    frequency="n/a",
    latency="n/a",
    historical_depth="none",
    revision_behaviour="none",
    licensing="none",
    rate_limit="none",
    cost_category="free",
    failure_behaviour="always returns an empty list",
    backup_options=["licensed economic calendar API", "manual event entry (not implemented)"],
    suitable_for_scalping=False,
)


class NoCalendarProvider(CalendarProvider):
    name = "none"
    is_mock = False
    doc = _NO_DATA_DOC

    def get_events(self, start: datetime, end: datetime, now: datetime) -> list[EconomicEvent]:
        return []

    def health(self) -> ProviderHealth:
        return ProviderHealth(self.name, self.kind, True, False, None, None, 0.0, 0, ["EVENT AWARENESS DISABLED - no economic calendar configured; event lockouts will not trigger around real releases"])


class NoNewsProvider(NewsProvider):
    name = "none"
    is_mock = False
    doc = _NO_DATA_DOC

    def get_news(self, start: datetime, end: datetime) -> list[NewsItem]:
        return []

    def health(self) -> ProviderHealth:
        return ProviderHealth(self.name, self.kind, True, False, None, None, 0.0, 0, ["NEWS DISABLED - no news feed configured"])
