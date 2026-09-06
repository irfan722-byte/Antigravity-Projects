"""Mock economic-calendar and trading-calendar providers (DEMO DATA).

Events are scheduled on a realistic weekly pattern (first-Friday payrolls,
mid-month CPI, FOMC every ~6 weeks) with release values drawn from a seeded
generator. They are labelled provider="mock" and must never be shown as real.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, time, timedelta

import numpy as np

from ...core.news_state import EconomicEvent, Importance, Verification
from ...core.timeutil import NY, ensure_utc
from ..base import CalendarProvider, ProviderDoc, ProviderHealth, TradingCalendarProvider

UTC = UTC

TEMPLATES = [
    # (name, category, hour_ny, minute, day_rule, consensus, std, unit, higher_is_usd_positive)
    ("Nonfarm Payrolls", "employment", 8, 30, "first_friday", 180.0, 75.0, "k", True),
    ("CPI m/m", "inflation", 8, 30, "day_12", 0.3, 0.12, "%", True),
    ("FOMC Rate Decision", "fed_policy", 14, 0, "fomc", 5.25, 0.1, "%", True),
    ("ISM Manufacturing PMI", "business_survey", 10, 0, "first_business_day", 50.0, 1.5, "idx", True),
    ("Retail Sales m/m", "retail", 8, 30, "day_15", 0.3, 0.4, "%", True),
    ("Initial Jobless Claims", "employment", 8, 30, "thursday", 220.0, 12.0, "k", False),
]


def _first_friday(y: int, m: int) -> date:
    d = date(y, m, 1)
    while d.weekday() != 4:
        d += timedelta(days=1)
    return d


def _rng(salt: str) -> np.random.Generator:
    h = hashlib.sha256(f"mockcal:{salt}".encode()).digest()
    return np.random.default_rng(int.from_bytes(h[:8], "little"))


class MockCalendarProvider(CalendarProvider):
    name = "mock"
    is_mock = True
    doc = ProviderDoc(["event", "scheduled_ts", "actual", "consensus", "prior", "revised_prior"], "as scheduled", "none", "synthetic", "revisions synthetic", "none", "none", "free", "n/a", [], False)

    def __init__(self, conflict_event_ids: set[str] | None = None, delay_event_ids: set[str] | None = None):
        self.conflict_ids = conflict_event_ids or set()
        self.delay_ids = delay_event_ids or set()

    def _events_for_month(self, y: int, m: int) -> list[EconomicEvent]:
        out = []
        for name, cat, hh, mm, rule, cons, std, unit, usd_pos in TEMPLATES:
            days: list[date] = []
            if rule == "first_friday":
                days = [_first_friday(y, m)]
            elif rule == "day_12":
                days = [date(y, m, 12)]
            elif rule == "day_15":
                days = [date(y, m, 15)]
            elif rule == "first_business_day":
                d = date(y, m, 1)
                while d.weekday() >= 5:
                    d += timedelta(days=1)
                days = [d]
            elif rule == "fomc":
                if m in (1, 3, 5, 6, 7, 9, 11, 12) and m % 2 == 1 or m in (6, 12):
                    d = date(y, m, 15)
                    while d.weekday() != 2:
                        d += timedelta(days=1)
                    days = [d]
            elif rule == "thursday":
                d = date(y, m, 1)
                while d.month == m:
                    if d.weekday() == 3:
                        days.append(d)
                    d += timedelta(days=1)
            for d in days:
                if d.weekday() >= 5:
                    d += timedelta(days=(7 - d.weekday()))
                sched = datetime.combine(d, time(hh, mm), tzinfo=NY).astimezone(UTC)
                rng = _rng(f"{name}:{d.isoformat()}")
                eid = f"mock-{cat}-{d.isoformat()}"
                actual = round(cons + std * rng.standard_normal(), 2)
                prior = round(cons + std * rng.standard_normal() * 0.8, 2)
                revised = round(prior + std * 0.3 * rng.standard_normal(), 2) if rng.random() < 0.3 else None
                imp = Importance.HIGH if cat in ("employment", "inflation", "fed_policy") and name != "Initial Jobless Claims" else Importance.MEDIUM
                out.append(EconomicEvent(eid, name, "US", "USD", imp, sched, "America/New_York", cat, self.name, sched, actual=actual, consensus=cons, prior=prior, revised_prior=revised, revision_ts=sched if revised else None, official_source="mock (synthetic)", published_ts=None, verification=Verification.PENDING, higher_is_usd_positive=usd_pos, unit=unit, surprise_std=std, surprise_history_n=36))
        return out

    def get_events(self, start: datetime, end: datetime, now: datetime) -> list[EconomicEvent]:
        start, end, now = ensure_utc(start), ensure_utc(end), ensure_utc(now)
        out: list[EconomicEvent] = []
        y, m = start.year, start.month
        while (y, m) <= (end.year, end.month):
            for ev in self._events_for_month(y, m):
                if not (start <= ev.scheduled_ts <= end):
                    continue
                # point-in-time: before the release nothing is known; after it the actual is published with a small delay
                delay = timedelta(minutes=45) if ev.event_id in self.delay_ids else timedelta(seconds=20)
                if now >= ev.scheduled_ts + delay:
                    ev.published_ts = ev.scheduled_ts + delay
                    ev.ingested_ts = ev.published_ts + timedelta(seconds=5)
                    ev.verification = Verification.CONFLICT if ev.event_id in self.conflict_ids else Verification.VERIFIED
                else:
                    ev.actual = None
                    ev.revised_prior = None
                    ev.revision_ts = None
                    ev.published_ts = None
                    ev.verification = Verification.PENDING
                out.append(ev)
            m += 1
            if m > 12:
                y, m = y + 1, 1
        return sorted(out, key=lambda e: e.scheduled_ts)

    def reaction_history(self) -> dict:
        # Illustrative synthetic reaction statistics with explicit sample sizes. DEMO only.
        return {
            cat: {"source": "mock synthetic", "sample_size": 36, "stronger": {"n": 14, "gold_median_move_30m": -6.5, "gold_iqr_30m": 9.0, "reversal_rate_2h": 0.36}, "weaker": {"n": 13, "gold_median_move_30m": 7.2, "gold_iqr_30m": 8.5, "reversal_rate_2h": 0.31}, "inline": {"n": 9, "gold_median_move_30m": 0.8, "gold_iqr_30m": 6.0, "reversal_rate_2h": 0.55}}
            for cat in ("employment", "inflation", "fed_policy", "business_survey", "retail")
        }

    def health(self) -> ProviderHealth:
        return ProviderHealth(self.name, self.kind, True, True, None, None, 0.0, 0, ["DEMO DATA - synthetic calendar"])


class MockTradingCalendarProvider(TradingCalendarProvider):
    name = "mock"
    is_mock = True

    def holidays(self, year: int) -> set[date]:
        # Spot gold trades through most holidays; the widely observed closures/early closes are listed.
        return {date(year, 12, 25), date(year, 1, 1)}

    def early_closes_ny(self, year: int) -> dict[date, time]:
        return {date(year, 12, 24): time(13, 0), date(year, 12, 31): time(13, 0), date(year, 7, 3): time(13, 0)}

    def verified(self) -> bool:
        return True  # verified *as a demo calendar*; a production calendar must be sourced and reviewed

    def health(self) -> ProviderHealth:
        return ProviderHealth(self.name, self.kind, True, True, None, None, 0.0, 0, ["DEMO calendar"])
